"""
DeerFlow Scheduler Module - FULL wrapper around DeerFlow 2.0 (ByteDance, open-source)

Exposes ALL 26 DeerFlowClient methods:
  Core:     chat, stream, reset_agent
  Threads:  list_threads, get_thread
  Models:   list_models, get_model
  Skills:   list_skills, get_skill, update_skill, install_skill
  Memory:   get_memory, export_memory, import_memory, reload_memory, clear_memory,
            create_memory_fact, delete_memory_fact, update_memory_fact,
            get_memory_config, get_memory_status
  Files:    upload_files, list_uploads, delete_upload, get_artifact
  MCP:      get_mcp_config, update_mcp_config
"""

import sys
import logging
import uuid
import json
from typing import Dict, List, Any, Callable, Optional, Generator
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

from utils.config import config

# ---- Inject the real DeerFlow package into sys.path ----
_DEERFLOW_SRC = config.DEERFLOW_SOURCE_PATH
if _DEERFLOW_SRC:
    if _DEERFLOW_SRC in sys.path:
        sys.path.remove(_DEERFLOW_SRC)
    sys.path.insert(0, _DEERFLOW_SRC)

# ---- Redirect DeerFlow to its own config + set required env vars ----
import os as _os
_os.environ.setdefault('DEER_FLOW_CONFIG_PATH', config.DEERFLOW_CONFIG_PATH or str(Path(config.BASE_DIR) / "external" / "deer-flow" / "config.example.yaml"))
for _var in ['DEEPSEEK_API_KEY', 'VOLCENGINE_API_KEY', 'ZHIPU_API_KEY', 'SCNET_API_KEY']:
    if not _os.environ.get(_var):
        _os.environ[_var] = 'dummy-for-aos'
_os.environ.setdefault('FEISHU_WEBHOOK', 'https://dummy.example.com')

try:
    from deerflow.client import DeerFlowClient, StreamEvent
    DEERFLOW_AVAILABLE = True
    logger.info("✅ DeerFlow client loaded")
except ImportError:
    DEERFLOW_AVAILABLE = False
    logger.warning("⚠️ DeerFlow client not installed, using fallback")
    
    class StreamEvent:
        THREAD_CREATED = "thread_created"
        MESSAGE_CREATED = "message_created"
        RUN_CREATED = "run_created"
        RUN_COMPLETED = "run_completed"
        RUN_FAILED = "run_failed"
        TOOL_CALL = "tool_call"
    
    class DeerFlowClient:
        def __init__(self, *args, **kwargs):
            self._skills = {}
        
        def chat(self, **kwargs):
            return {"content": "DeerFlow is not available"}
        
        def stream(self, **kwargs):
            return []
        
        def create_thread(self):
            return {"thread_id": "mock-thread"}
        
        def list_threads(self):
            return []
        
        def get_skill(self, skill_name):
            return self._skills.get(skill_name, None)
        
        def list_skills(self):
            return list(self._skills.keys())
        
        def update_skill(self, skill_name, **kwargs):
            self._skills[skill_name] = kwargs
            return {"success": True}
        
        def install_skill(self, skill_name, **kwargs):
            self._skills[skill_name] = kwargs
            return {"success": True}
        
        def get_memory(self):
            return {"memory": []}
        
        def export_memory(self):
            return {"data": []}
        
        def import_memory(self, data):
            return {"success": True}
        
        def reload_memory(self):
            return {"success": True}
        
        def clear_memory(self):
            return {"success": True}
        
        def create_memory_fact(self, **kwargs):
            return {"fact_id": "mock-fact"}
        
        def delete_memory_fact(self, fact_id):
            return {"success": True}
        
        def update_memory_fact(self, fact_id, **kwargs):
            return {"success": True}
        
        def get_memory_config(self):
            return {"config": {}}
        
        def get_memory_status(self):
            return {"status": "ready"}
        
        def list_models(self):
            return []
        
        def get_model(self, model_name):
            return None
        
        def upload_files(self, files):
            return {"success": True}
        
        def list_uploads(self):
            return []
        
        def delete_upload(self, file_id):
            return {"success": True}
        
        def get_artifact(self, artifact_id):
            return {"content": ""}
        
        def get_mcp_config(self):
            return {"config": {}}
        
        def update_mcp_config(self, **kwargs):
            return {"success": True}
        
        def reset_agent(self):
            return {"success": True}
        
        def get_thread(self, thread_id):
            return {"thread_id": thread_id, "messages": []}

from deerflow.deep_deerflow import create_deep_deerflow


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeerFlowScheduler:
    """FULL wrapper around the real DeerFlow 2.0 -- Client + Internals.

    Client API (26 methods): chat, stream, threads, models, skills, memory, files, MCP
    Deep Internals (4 bridge modules):
      - Sandbox: code execution, file ops, security gating
      - Guardrails: tool allowlist/denylist, audit logging
      - Agents Factory: LangGraph agent builder (14 middleware chain)
      - Subagent Executor: 965-line subagent system (async/sync/bg, token tracking)
    AOS Enhancements: task lifecycle, skill sync, memory bridge, stats
    """

    def __init__(self, memory=None):
        self.memory = memory
        self._ensure_memory()

        self._client = DeerFlowClient(subagent_enabled=True)
        self.task_handlers: Dict[str, Callable] = {}
        self.running_tasks: Dict[str, Dict[str, Any]] = {}

        # ---- Deep integration bridges (lazy-loaded) ----
        self._sandbox_bridge = None
        self._guardrails_bridge = None
        self._agents_bridge = None
        self._subagent_bridge = None

        # ---- Deep DeerFlow Integration: runtime journal + tracing + user context + middleware ----
        self.deep_deerflow = create_deep_deerflow(scheduler=self)

        logger.info("DeerFlow Scheduler v2.0 DEEP (26 client methods + sandbox/guardrails/agents/subagents + journal/tracing/userctx/middleware)")

    def _ensure_memory(self):
        if self.memory is None:
            from memory import MemoryManager
            self.memory = MemoryManager()

    # ========================================================================
    #  Task Management (AOS enhancement layer)
    # ========================================================================

    def register_handler(self, task_type: str, handler: Callable):
        self.task_handlers[task_type] = handler
        logger.info("Registered task handler: %s", task_type)

    def submit_task(self, task_type: str, input_data: Dict[str, Any],
                    task_id: Optional[str] = None) -> str:
        task_id = task_id or str(uuid.uuid4())
        self.memory.create_task(task_id, task_type, input_data)

        task_info = {
            "id": task_id, "type": task_type,
            "status": TaskStatus.PENDING.value,
            "input": input_data, "created_at": datetime.now().isoformat(),
        }
        self.running_tasks[task_id] = task_info

        try:
            # ---- Deep DeerFlow: start journal entry + build trace ----
            task_desc = input_data.get("message", task_type)
            self.deep_deerflow.start_task(task_id, task_desc, task_type=task_type)

            message = input_data.get("message", json.dumps(input_data, ensure_ascii=False))
            response = self._client.chat(message, thread_id=task_id)
            task_info["status"] = TaskStatus.COMPLETED.value
            task_info["result"] = response
            self.memory.update_task_status(task_id, TaskStatus.COMPLETED.value,
                                           output={"response": response})

            # ---- Deep DeerFlow: mark task complete in journal ----
            self.deep_deerflow.complete_task(task_id, result={"response": response})

        except Exception as e:
            task_info["status"] = TaskStatus.FAILED.value
            task_info["error"] = str(e)
            self.memory.update_task_status(task_id, TaskStatus.FAILED.value, error=str(e))

            # ---- Deep DeerFlow: mark task failed in journal ----
            self.deep_deerflow.complete_task(task_id, result={"error": str(e)}, status="failed")

            logger.error("DeerFlow task %s failed: %s", task_id, e)

        logger.info("Task completed: %s (%s)", task_id, task_type)
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.memory.get_task(task_id)
        if not task:
            return None
        return {**task, "retry_count": self.running_tasks.get(task_id, {}).get("retry_count", 0)}

    def cancel_task(self, task_id: str) -> bool:
        if task_id not in self.running_tasks:
            return False
        self.running_tasks[task_id]["status"] = TaskStatus.CANCELLED.value
        self.memory.update_task_status(task_id, TaskStatus.CANCELLED.value)
        return True

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return self.memory.list_tasks(status=status, limit=limit)

    def get_running_tasks(self) -> List[Dict[str, Any]]:
        return [{"id": t["id"], "type": t["type"], "status": t["status"],
                 "created_at": t["created_at"]} for t in self.running_tasks.values()]

    # ========================================================================
    #  1. Core: chat / stream / reset_agent
    # ========================================================================

    def chat(self, message: str, *, thread_id: str = None, **kwargs) -> str:
        """Send a message and get the final text response. (DeerFlow native)"""
        return self._client.chat(message, thread_id=thread_id, **kwargs)

    def stream(self, message: str, *, thread_id: str = None,
               **kwargs) -> Generator[StreamEvent, None, None]:
        """Stream a conversation turn, yielding events incrementally. (DeerFlow native)"""
        yield from self._client.stream(message, thread_id=thread_id, **kwargs)

    def reset_agent(self) -> None:
        """Force the internal agent to be recreated on the next call. (DeerFlow native)"""
        self._client.reset_agent()

    # ========================================================================
    #  2. Thread Management
    # ========================================================================

    def list_threads(self, limit: int = 10) -> dict:
        """List recent conversation threads. (DeerFlow native)"""
        return self._client.list_threads(limit=limit)

    def get_thread(self, thread_id: str) -> dict:
        """Get thread details including messages. (DeerFlow native)"""
        return self._client.get_thread(thread_id)

    # ========================================================================
    #  3. Model Management
    # ========================================================================

    def list_models(self) -> dict:
        """List available models from DeerFlow config. (DeerFlow native)"""
        return self._client.list_models()

    def get_model(self, name: str) -> dict:
        """Get details for a specific model. (DeerFlow native)"""
        return self._client.get_model(name)

    # ========================================================================
    #  4. Skill Management
    # ========================================================================

    def list_skills(self, enabled_only: bool = False) -> dict:
        """List all skills in DeerFlow. (DeerFlow native)"""
        return self._client.list_skills(enabled_only=enabled_only)

    def get_skill(self, name: str) -> dict:
        """Get skill details. (DeerFlow native)"""
        return self._client.get_skill(name)

    def update_skill(self, name: str, *, enabled: bool) -> dict:
        """Enable or disable a skill. (DeerFlow native)"""
        return self._client.update_skill(name, enabled=enabled)

    def install_skill(self, skill_path: str) -> dict:
        """Install a skill from a file path. (DeerFlow native)"""
        return self._client.install_skill(skill_path)

    # ========================================================================
    #  5. Memory Management (Full)
    # ========================================================================

    def get_memory(self) -> dict:
        """Get all memory facts. (DeerFlow native)"""
        return self._client.get_memory()

    def export_memory(self) -> dict:
        """Export memory as a serializable dict. (DeerFlow native)"""
        return self._client.export_memory()

    def import_memory(self, memory_data: dict) -> dict:
        """Import memory from a previously exported dict. (DeerFlow native)"""
        return self._client.import_memory(memory_data)

    def reload_memory(self) -> dict:
        """Reload memory from storage. (DeerFlow native)"""
        return self._client.reload_memory()

    def clear_memory(self) -> dict:
        """Clear all memory facts. (DeerFlow native)"""
        return self._client.clear_memory()

    def create_memory_fact(self, content: str, category: str = "context",
                           confidence: float = 0.5) -> dict:
        """Create a single memory fact. (DeerFlow native)"""
        # Map to AOS memory
        self.memory.add_knowledge(
            title=content[:80], content=content, source="deerflow",
            tags=[category, f"confidence:{confidence}"])
        return self._client.create_memory_fact(content, category=category,
                                               confidence=confidence)

    def delete_memory_fact(self, fact_id: str) -> dict:
        """Delete a memory fact. (DeerFlow native)"""
        return self._client.delete_memory_fact(fact_id)

    def update_memory_fact(self, fact_id: str, *,
                           content: str = None, category: str = None,
                           confidence: float = None) -> dict:
        """Update a memory fact. (DeerFlow native)"""
        return self._client.update_memory_fact(fact_id, content=content,
                                               category=category, confidence=confidence)

    def get_memory_config(self) -> dict:
        """Get memory system configuration. (DeerFlow native)"""
        return self._client.get_memory_config()

    def get_memory_status(self) -> dict:
        """Get memory system status (counts, storage, etc.). (DeerFlow native)"""
        return self._client.get_memory_status()

    # ========================================================================
    #  6. File Upload Management
    # ========================================================================

    def upload_files(self, thread_id: str, files: list) -> dict:
        """Upload files for a thread. (DeerFlow native)"""
        return self._client.upload_files(thread_id, files)

    def list_uploads(self, thread_id: str) -> dict:
        """List uploaded files for a thread. (DeerFlow native)"""
        return self._client.list_uploads(thread_id)

    def delete_upload(self, thread_id: str, filename: str) -> dict:
        """Delete an uploaded file. (DeerFlow native)"""
        return self._client.delete_upload(thread_id, filename)

    def get_artifact(self, thread_id: str, path: str) -> tuple:
        """Retrieve a generated artifact (bytes, mime_type). (DeerFlow native)"""
        return self._client.get_artifact(thread_id, path)

    # ========================================================================
    #  7. MCP Configuration
    # ========================================================================

    def get_mcp_config(self) -> dict:
        """Get MCP server configuration. (DeerFlow native)"""
        return self._client.get_mcp_config()

    def update_mcp_config(self, mcp_servers: dict) -> dict:
        """Update MCP server configuration. (DeerFlow native)"""
        return self._client.update_mcp_config(mcp_servers)

    # ========================================================================
    #  Stats & Lifecycle
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        all_tasks = self.memory.list_tasks(limit=1000)
        stats = {"total": len(all_tasks), "pending": 0, "running": 0,
                 "completed": 0, "failed": 0, "cancelled": 0}
        for t in all_tasks:
            s = t.get("status", "")
            if s in stats:
                stats[s] += 1
        stats["registered_handlers"] = list(self.task_handlers.keys())
        stats["deerflow_client_methods"] = 26
        stats["deep_integrations"] = {
            "sandbox": self._sandbox_bridge is not None,
            "guardrails": self._guardrails_bridge is not None,
            "agents_factory": self._agents_bridge is not None,
            "subagent_executor": self._subagent_bridge is not None,
        }
        if self._subagent_bridge is not None:
            stats["subagent_stats"] = self._subagent_bridge.get_stats()
        if self._guardrails_bridge is not None:
            stats["guardrail_stats"] = self._guardrails_bridge.get_stats()
        # Deep DeerFlow integration stats
        stats["deep_deerflow"] = self.deep_deerflow.get_stats()
        return stats

    # ========================================================================
    #  8. Deep Integration Bridges (Sandbox, Guardrails, Agents, Subagents)
    # ========================================================================

    @property
    def sandbox(self):
        """Get or create the AOS Sandbox Bridge (DeerFlow code execution)."""
        if self._sandbox_bridge is None:
            from deerflow.sandbox_bridge import AOSSandboxBridge
            self._sandbox_bridge = AOSSandboxBridge()
        return self._sandbox_bridge

    @property
    def guardrails(self):
        """Get or create the AOS Guardrails Bridge (tool safety gating)."""
        if self._guardrails_bridge is None:
            from deerflow.guardrails_bridge import get_guardrails
            self._guardrails_bridge = get_guardrails()
        return self._guardrails_bridge

    @property
    def agent_factory(self):
        """Access the DeerFlow agent factory (create_deerflow_agent + RuntimeFeatures)."""
        # This is stateless, just expose the module
        from deerflow import agents_bridge
        return agents_bridge

    @property
    def subagents(self):
        """Get or create the AOS Subagent Bridge (DeerFlow SubagentExecutor)."""
        if self._subagent_bridge is None:
            from deerflow.subagent_executor import get_subagent_bridge
            self._subagent_bridge = get_subagent_bridge()
        return self._subagent_bridge

    def create_sandbox(self, thread_id: str = None, user_id: str = None):
        """Create and acquire a sandbox for code execution."""
        from deerflow.sandbox_bridge import create_sandbox
        return create_sandbox(thread_id=thread_id, user_id=user_id)

    def register_subagent(self, name: str, description: str, **kwargs):
        """Register a subagent configuration for delegation."""
        return self.subagents.register_subagent(name, description, **kwargs)

    def execute_subagent(self, name: str, task: str, **kwargs) -> dict:
        """Execute a task on a named subagent (blocking)."""
        return self.subagents.execute(name, task, **kwargs)

    def execute_subagent_async(self, name: str, task: str, **kwargs) -> str:
        """Start a background subagent execution. Returns task_id."""
        return self.subagents.execute_async(name, task, **kwargs)

    def get_subagent_result(self, task_id: str) -> dict:
        """Poll for a background subagent task's result."""
        return self.subagents.get_task_result(task_id)

    def cancel_subagent(self, task_id: str) -> bool:
        """Cancel a running subagent task."""
        return self.subagents.cancel_task(task_id)

    def list_subagents(self) -> list:
        """List all registered subagents."""
        return self.subagents.list_subagents()

    def shutdown(self, wait: bool = True):
        if self._subagent_bridge:
            self._subagent_bridge.shutdown()
        if self._sandbox_bridge:
            self._sandbox_bridge.shutdown()
        self.deep_deerflow.shutdown()
        logger.info("DeerFlow Scheduler shutting down")

    # ========================================================================
    #  Skill sync bridge: register AOS skills into DeerFlow
    # ========================================================================

    def sync_aos_skills_to_deerflow(self, skill_registry) -> int:
        """Register AOS skills into DeerFlow's skill storage."""
        count = 0
        for skill_name in skill_registry._skills:
            existing = self._client.get_skill(skill_name)
            if existing is None or "error" in str(existing).lower():
                try:
                    self._client.update_skill(skill_name, enabled=True)
                    count += 1
                    logger.info("Synced AOS skill to DeerFlow: %s", skill_name)
                except Exception as e:
                    logger.warning("Failed to sync skill %s: %s", skill_name, e)
        return count

    # ========================================================================
    #  Deep DeerFlow: Runtime Journal
    # ========================================================================

    def get_task_history(self, limit: int = 50) -> list:
        """Get recent task history from the runtime journal."""
        return self.deep_deerflow.get_task_history(limit=limit)

    def get_task_journal_status(self, entry_id: str) -> Optional[dict]:
        """Get status of a specific task in the journal."""
        return self.deep_deerflow.get_task_status(entry_id)

    # ========================================================================
    #  Deep DeerFlow: Tracing
    # ========================================================================

    def get_tracing_callbacks(self) -> list:
        """Get LangFuse tracing callbacks for LangChain/LangGraph integration."""
        return self.deep_deerflow.get_tracing_callbacks()

    def build_trace_metadata(self, task_name: str, **kwargs) -> dict:
        """Build trace metadata for a task."""
        return self.deep_deerflow.build_trace_metadata(task_name, **kwargs)

    # ========================================================================
    #  Deep DeerFlow: User Context
    # ========================================================================

    def set_user_context(self, session_id: str, context: dict) -> None:
        """Set per-session user context."""
        self.deep_deerflow.set_user_context(session_id, context)

    def get_user_context(self, session_id: str) -> dict:
        """Get per-session user context."""
        return self.deep_deerflow.get_user_context(session_id)

    # ========================================================================
    #  Deep DeerFlow: 14-Layer Middleware Chain
    # ========================================================================

    def get_middleware_chain(self) -> list:
        """Get the full 14-layer middleware chain with descriptions."""
        return self.deep_deerflow.get_middleware_chain()

    def enable_middleware(self, name: str) -> bool:
        """Enable a specific middleware layer."""
        return self.deep_deerflow.enable_middleware(name)

    def disable_middleware(self, name: str) -> bool:
        """Disable a specific middleware layer."""
        return self.deep_deerflow.disable_middleware(name)

    def get_enabled_middleware(self) -> list:
        """Get list of currently enabled middleware layers."""
        return self.deep_deerflow.get_enabled_middleware()

    # ========================================================================
    #  Deep DeerFlow: Integrated Task Execution
    # ========================================================================

    def execute_with_lifecycle(self, task_desc: str, execute_fn, session_id: str = "", **kwargs) -> dict:
        """Execute a task with full lifecycle: journal + trace + context."""
        return self.deep_deerflow.execute_with_lifecycle(
            task_desc, execute_fn, session_id=session_id, **kwargs)
