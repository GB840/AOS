"""
DeerFlow Subagent Executor Bridge -- exposes the REAL DeerFlow SubagentExecutor to AOS.

Wraps:
  - deerflow.subagents.executor.SubagentExecutor (965 lines)
  - deerflow.subagents.executor.SubagentResult
  - deerflow.subagents.executor.SubagentStatus
  - deerflow.subagents.config.SubagentConfig
  - Background task management (execute_async, get_background_task_result, etc.)

This gives AOS access to DeerFlow's full subagent system:
  - Async/sync/background execution
  - Thread pool + persistent event loop
  - Token collection & cost tracking
  - Timeout + cooperative cancellation
  - Langfuse tracing
  - Skill-aware tool filtering
"""

from __future__ import annotations

import sys
import os
import logging
import threading
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

try:
    from deerflow.path_detect import setup_deerflow_env
except ImportError:
    # 真实 DeerFlow 发行包没有 path_detect（那是 dev 模式辅助）；
    # 这里回退为：直接用已可导入的 deerflow 包所在目录作为源码根。
    def setup_deerflow_env():
        import deerflow as _df
        return os.path.dirname(_df.__file__)

_DEERFLOW_SRC = setup_deerflow_env()

# SubagentConfig 是纯 dataclass，零运行时依赖 —— 注册永远需要它。
# 解析策略：优先从已安装的 deerflow 包正常导入；若完整依赖栈未装（仅要注册），
# 则直接从 deerflow 源目录加载 subagents/config.py（该文件只依赖标准库，可独立加载），
# 绕开会拉起 langgraph/langchain 等重型依赖的 __init__ 链。
def _resolve_subagent_config():
    try:
        from deerflow.subagents.config import SubagentConfig  # type: ignore
        return SubagentConfig
    except ImportError:
        import importlib.util as _ilu
        from pathlib import Path as _P
        import deerflow as _df
        cfg_path = _P(_df.__file__).parent / "subagents" / "config.py"
        spec = _ilu.spec_from_file_location("_df_subagent_config", str(cfg_path))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.SubagentConfig


try:
    SubagentConfig = _resolve_subagent_config()
except Exception as e:  # noqa: BLE001
    logger.error("❌ DeerFlow SubagentConfig 不可导入，注册无法进行: %s", e)
    SubagentConfig = None

# 重型执行栈（langgraph/langchain…）仅执行时需要；注册只需上面的 SubagentConfig。
# 占位符：执行栈未加载时这些符号为 None，运行时由 _EXEC_OK 守卫拦截。
_DeerFlowSubagentExecutor = None
SubagentResult = None
SubagentStatus = None
get_background_task_result = None
list_background_tasks = None
cleanup_background_task = None
request_cancel_background_task = None
MAX_CONCURRENT_SUBAGENTS = None
_EXEC_OK = False
if _DEERFLOW_SRC:
    try:
        from deerflow.subagents.executor import (
            SubagentExecutor as _DeerFlowSubagentExecutor,
            SubagentResult,
            SubagentStatus,
            get_background_task_result,
            list_background_tasks,
            cleanup_background_task,
            request_cancel_background_task,
            MAX_CONCURRENT_SUBAGENTS,
        )
        logger.info("✅ DeerFlow SubagentExecutor 加载成功")
        _EXEC_OK = True
    except ImportError as e:
        logger.warning("⚠️ DeerFlow 执行栈未加载（仅注册可用，执行需补全依赖）: %s", e)
else:
    logger.warning("⚠️ DeerFlow 源码路径未检测到")


class AOSSubagentBridge:
    """AOS bridge over DeerFlow's SubagentExecutor.

    Provides a simplified, Pythonic interface for:
    - Defining subagent configurations (name, description, tools, skills, model)
    - Executing subagent tasks (sync, async, background)
    - Monitoring execution status and results
    - Cancelling running tasks
    - Token usage tracking

    Each subagent runs as a LangGraph agent with its own middleware chain,
    sandbox, and skill set -- fully isolated from the parent agent.
    """

    def __init__(self, tools: List[Any] = None):
        """
        Args:
            tools: List of LangChain tools available to subagents.
        """
        self._tools = tools or []
        self._executors: Dict[str, _DeerFlowSubagentExecutor] = {}
        self._configs: Dict[str, SubagentConfig] = {}
        self._results: Dict[str, SubagentResult] = {}
        self._lock = threading.Lock()

    # ---- Configuration ----

    def register_subagent(
        self,
        name: str,
        description: str,
        *,
        system_prompt: str = None,
        tools: List[str] = None,
        disallowed_tools: List[str] = None,
        skills: List[str] = None,
        model: str = "inherit",
        max_turns: int = 50,
        timeout_seconds: int = 900,
    ) -> SubagentConfig:
        """Register a subagent configuration.

        Args:
            name: Unique identifier (e.g. "code-reviewer", "web-researcher").
            description: Natural language description of when to delegate.
            system_prompt: Guiding prompt for the subagent's behavior.
            tools: Optional tool name allowlist. None = inherit all.
            disallowed_tools: Tool names to deny. Default: ["task"].
            skills: Skill names to load. None = inherit all enabled.
            model: Model name or "inherit" for parent's model.
            max_turns: Maximum agent turns before auto-stop.
            timeout_seconds: Execution timeout.

        Returns:
            SubagentConfig that can be used to create an executor.
        """
        if SubagentConfig is None:
            raise RuntimeError("DeerFlow SubagentConfig 不可用，无法注册（请确认 deerflow 包可导入）")
        config = SubagentConfig(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools,
            disallowed_tools=disallowed_tools if disallowed_tools is not None else ["task"],
            skills=skills,
            model=model,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
        )

        with self._lock:
            self._configs[name] = config
            # Invalidate existing executor
            self._executors.pop(name, None)

        logger.info("Subagent registered: %s (tools=%s, skills=%s, max_turns=%d)",
                     name, tools, skills, max_turns)
        return config

    def unregister_subagent(self, name: str):
        """Remove a subagent configuration."""
        with self._lock:
            self._configs.pop(name, None)
            self._executors.pop(name, None)
        logger.info("Subagent unregistered: %s", name)

    def list_subagents(self) -> List[Dict[str, Any]]:
        """List all registered subagents with their configs."""
        return [
            {
                "name": cfg.name,
                "description": cfg.description,
                "model": cfg.model,
                "max_turns": cfg.max_turns,
                "timeout_seconds": cfg.timeout_seconds,
                "tools": cfg.tools,
                "skills": cfg.skills,
            }
            for cfg in self._configs.values()
        ]

    # ---- Execution ----

    def _get_executor(self, name: str,
                      parent_model: str = None,
                      thread_id: str = None,
                      user_id: str = None) -> _DeerFlowSubagentExecutor:
        """Get or create a SubagentExecutor for the named subagent."""
        if not _EXEC_OK:
            raise RuntimeError("DeerFlow 执行栈未加载，无法执行子智能体（需补全依赖后执行）")
        if name not in self._configs:
            raise ValueError(f"Subagent '{name}' not registered. Call register_subagent() first.")

        config = self._configs[name]

        # Create executor
        executor = _DeerFlowSubagentExecutor(
            config=config,
            tools=self._tools,
            parent_model=parent_model,
            thread_id=thread_id,
            user_id=user_id,
        )

        with self._lock:
            self._executors[name] = executor

        return executor

    def execute(self, subagent_name: str, task: str, *,
                parent_model: str = None,
                thread_id: str = None,
                user_id: str = None) -> Dict[str, Any]:
        """Execute a task synchronously on a named subagent.

        Blocks until completion or timeout.

        Returns:
            Dict with task_id, status, result, error, ai_messages, token_usage.
        """
        executor = self._get_executor(subagent_name,
                                       parent_model=parent_model,
                                       thread_id=thread_id,
                                       user_id=user_id)

        logger.info("Executing subagent '%s': task='%s'", subagent_name, task[:100])
        result: SubagentResult = executor.execute(task)

        task_dict = self._result_to_dict(result)
        self._results[result.task_id] = result
        return task_dict

    def execute_async(self, subagent_name: str, task: str, *,
                      task_id: str = None,
                      parent_model: str = None,
                      thread_id: str = None,
                      user_id: str = None) -> str:
        """Start a background subagent execution. Returns task_id immediately.

        Use get_task_result(task_id) to poll for completion.
        """
        executor = self._get_executor(subagent_name,
                                       parent_model=parent_model,
                                       thread_id=thread_id,
                                       user_id=user_id)

        task_id = executor.execute_async(task, task_id=task_id)
        logger.info("Async subagent '%s': task_id=%s", subagent_name, task_id)
        return task_id

    # ---- Status & Results ----

    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Poll for a background task's result."""
        result = get_background_task_result(task_id)
        if result is None:
            # Check local cache too
            result = self._results.get(task_id)
        if result is None:
            return None
        return self._result_to_dict(result)

    def cancel_task(self, task_id: str) -> bool:
        """Request cancellation of a running background task."""
        request_cancel_background_task(task_id)
        logger.info("Cancellation requested for task: %s", task_id)
        return True

    def list_tasks(self) -> List[Dict[str, Any]]:
        """List all background tasks."""
        tasks = list_background_tasks()
        return [self._result_to_dict(r) for r in tasks]

    def cleanup_task(self, task_id: str):
        """Remove a completed task from memory."""
        cleanup_background_task(task_id)
        self._results.pop(task_id, None)

    # ---- Stats ----

    def get_stats(self) -> Dict[str, Any]:
        """Get subagent system statistics."""
        tasks = list_background_tasks()
        statuses = {}
        for t in tasks:
            s = t.status.value if hasattr(t.status, "value") else str(t.status)
            statuses[s] = statuses.get(s, 0) + 1

        return {
            "registered_subagents": len(self._configs),
            "configured_subagents": list(self._configs.keys()),
            "max_concurrent": MAX_CONCURRENT_SUBAGENTS,
            "active_tasks": len(tasks),
            "task_statuses": statuses,
        }

    # ---- Helpers ----

    @staticmethod
    def _result_to_dict(result: SubagentResult) -> Dict[str, Any]:
        """Convert SubagentResult to a JSON-safe dict."""
        status = result.status
        if hasattr(status, "value"):
            status = status.value

        d = {
            "task_id": result.task_id,
            "trace_id": result.trace_id,
            "status": status,
            "result": result.result,
            "error": result.error,
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "ai_messages_count": len(result.ai_messages) if result.ai_messages else 0,
            "token_usage_records": result.token_usage_records,
        }
        return d

    def shutdown(self):
        """Clean up all executors."""
        with self._lock:
            self._executors.clear()
            self._configs.clear()
            self._results.clear()
        logger.info("AOSSubagentBridge shutdown complete")


# ---- Module-level default ----

_default_subagent_bridge: Optional[AOSSubagentBridge] = None


def get_subagent_bridge(tools: List[Any] = None) -> AOSSubagentBridge:
    """Get or create the default AOS subagent bridge."""
    global _default_subagent_bridge
    if _default_subagent_bridge is None:
        _default_subagent_bridge = AOSSubagentBridge(tools=tools)
    elif tools:
        _default_subagent_bridge._tools = tools
    return _default_subagent_bridge
