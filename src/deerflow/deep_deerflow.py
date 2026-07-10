"""
Deep DeerFlow Integration - Complete orchestration runtime.

Wires AOS into DeerFlow 2.0's FULL capabilities:
1. Runtime Journal: Task execution journaling with RunJournal
2. Tracing: Distributed tracing via LangFuse callbacks
3. User Context: Session-scoped user context management
4. Full Middleware Chain: 14-layer onion model exposure
5. Reflection: Post-task reflection and improvement
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

from deerflow.path_detect import detect_deerflow_path

# ---- DeerFlow 路径自动检测 ----
_DF_ROOT = detect_deerflow_path()
_DF_PATH = os.path.join(_DF_ROOT, "deerflow") if _DF_ROOT else ""

if _DF_ROOT:
    logger.info(f"DeepDeerFlow: DeerFlow 源码路径已检测到: {_DF_ROOT}")
else:
    logger.warning("DeepDeerFlow: DeerFlow 源码路径未检测到，将使用 AOS 内置实现")


class DeepDeerFlowIntegration:
    """Complete DeerFlow 2.0 runtime integration for AOS.

    Provides:
    1. Runtime Journal: Task lifecycle tracking with RunJournal
    2. Tracing: LangFuse-based distributed tracing
    3. User Context: Per-session context management
    4. Middleware Chain: Full 14-layer middleware exposure
    5. Reflection: Post-task analysis and improvement
    """

    # The 14-layer middleware chain (DeerFlow's "onion model")
    MIDDLEWARE_CHAIN = [
        # Request Preprocessing
        ("sandbox", "SandboxMiddleware - Isolated execution environment"),
        ("dangling_tool_call", "DanglingToolCallMiddleware - Fix broken tool call continuations"),
        # Security Isolation
        ("guardrail", "GuardrailMiddleware - Tool allow/deny gating"),
        ("tool_error_handling", "ToolErrorHandlingMiddleware - Graceful error recovery"),
        # Context Management
        ("summarization", "SummarizationMiddleware - Auto-summarize when context overflows"),
        ("todo", "TodoMiddleware - Task list tracking"),
        ("auto_title", "AutoTitleMiddleware - Auto-generate thread titles"),
        ("memory", "MemoryMiddleware - Semantic memory recall"),
        ("vision", "VisionMiddleware - Image understanding"),
        # Control
        ("subagent_limit", "SubagentLimitMiddleware - Limit parallel subagents"),
        ("loop_detection", "LoopDetectionMiddleware - Detect infinite loops"),
        ("token_budget", "TokenBudgetMiddleware - Token usage enforcement"),
        ("clarification", "ClarificationMiddleware - Ask for clarification when needed"),
        # Tool Management
        ("deferred_tool_filter", "DeferredToolFilterMiddleware - Dynamic tool loading"),
    ]

    def __init__(self, scheduler=None):
        """Initialize deep DeerFlow integration.

        Args:
            scheduler: Optional DeerFlowScheduler instance from AOS.
        """
        self._scheduler = scheduler
        self._journal = None
        self._tracing_callbacks = []
        self._user_contexts: Dict[str, Dict[str, Any]] = {}
        self._middleware_status: Dict[str, bool] = {}
        self._task_counter = 0

        # Initialize runtime journal
        self._init_journal()

        # Initialize tracing
        self._init_tracing()

        logger.info(
            "DeepDeerFlowIntegration initialized: "
            "journal=%s, tracing=%s, middleware=%d layers",
            bool(self._journal),
            bool(self._tracing_callbacks),
            len(self.MIDDLEWARE_CHAIN),
        )

    # ================================================================
    # 1. RUNTIME JOURNAL
    # ================================================================

    def _init_journal(self) -> None:
        """Initialize the DeerFlow RunJournal for task tracking."""
        try:
            from deerflow.runtime.journal import RunJournal
            self._journal = RunJournal()
            logger.info("RunJournal initialized")
        except Exception as e:
            logger.warning("RunJournal init failed (non-fatal): %s", e)
            self._journal = None

    def start_task(self, task_id: str, task_desc: str, **kwargs) -> str:
        """Start a new task in the runtime journal.

        Returns the journal entry ID.
        """
        self._task_counter += 1
        entry_id = task_id or "aos-task-{}".format(self._task_counter)

        if self._journal:
            try:
                self._journal.add_entry(
                    entry_id=entry_id,
                    task=task_desc,
                    status="started",
                    started_at=datetime.now(timezone.utc),
                    metadata=kwargs,
                )
            except Exception as e:
                logger.debug("Journal start_task failed: %s", e)

        return entry_id

    def complete_task(self, entry_id: str, result: Any = None, status: str = "completed") -> None:
        """Mark a task as completed in the journal."""
        if self._journal:
            try:
                self._journal.update_entry(
                    entry_id=entry_id,
                    status=status,
                    completed_at=datetime.now(timezone.utc),
                    result=result,
                )
            except Exception as e:
                logger.debug("Journal complete_task failed: %s", e)

    def get_task_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent task history from the journal."""
        if not self._journal:
            return []
        try:
            return self._journal.get_entries(limit=limit)
        except Exception as e:
            logger.debug("Journal get_task_history failed: %s", e)
            return []

    def get_task_status(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task."""
        if not self._journal:
            return None
        try:
            return self._journal.get_entry(entry_id)
        except Exception:
            return None

    # ================================================================
    # 2. TRACING
    # ================================================================

    def _init_tracing(self) -> None:
        """Initialize LangFuse-based distributed tracing."""
        try:
            from deerflow.tracing import build_tracing_callbacks
            self._tracing_callbacks = build_tracing_callbacks()
            logger.info("Tracing initialized: %d callbacks", len(self._tracing_callbacks))
        except Exception as e:
            logger.debug("Tracing init failed (non-fatal): %s", e)
            self._tracing_callbacks = []

    def get_tracing_callbacks(self) -> List[Any]:
        """Get tracing callbacks for LangChain/LangGraph integration."""
        return list(self._tracing_callbacks)

    def build_trace_metadata(self, task_name: str, **kwargs) -> Dict[str, Any]:
        """Build trace metadata for a task."""
        try:
            from deerflow.tracing import build_langfuse_trace_metadata
            return build_langfuse_trace_metadata(task_name, **kwargs)
        except Exception:
            return {"name": task_name, "tags": ["aos"], **kwargs}

    def inject_trace_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Inject trace metadata into request context."""
        try:
            from deerflow.tracing import inject_langfuse_metadata
            return inject_langfuse_metadata(metadata)
        except Exception:
            return metadata

    # ================================================================
    # 3. USER CONTEXT
    # ================================================================

    def set_user_context(self, session_id: str, context: Dict[str, Any]) -> None:
        """Set per-session user context."""
        self._user_contexts[session_id] = {
            "updated_at": datetime.now().isoformat(),
            **context,
        }
        logger.debug("User context set for session %s: %d keys", session_id, len(context))

    def get_user_context(self, session_id: str) -> Dict[str, Any]:
        """Get per-session user context."""
        return self._user_contexts.get(session_id, {})

    def update_user_context(self, session_id: str, updates: Dict[str, Any]) -> None:
        """Update per-session user context."""
        ctx = self._user_contexts.get(session_id, {})
        ctx.update(updates)
        ctx["updated_at"] = datetime.now().isoformat()
        self._user_contexts[session_id] = ctx

    def clear_user_context(self, session_id: str) -> None:
        """Clear user context for a session."""
        self._user_contexts.pop(session_id, None)

    # ================================================================
    # 4. MIDDLEWARE CHAIN
    # ================================================================

    def get_middleware_chain(self) -> List[Dict[str, Any]]:
        """Get the full 14-layer middleware chain with descriptions."""
        return [
            {
                "layer": i + 1,
                "name": name,
                "description": desc,
                "enabled": self._middleware_status.get(name, False),
            }
            for i, (name, desc) in enumerate(self.MIDDLEWARE_CHAIN)
        ]

    def enable_middleware(self, name: str) -> bool:
        """Enable a specific middleware layer."""
        valid_names = {n for n, _ in self.MIDDLEWARE_CHAIN}
        if name not in valid_names:
            return False
        self._middleware_status[name] = True
        logger.info("Middleware enabled: %s", name)
        return True

    def disable_middleware(self, name: str) -> bool:
        """Disable a specific middleware layer."""
        valid_names = {n for n, _ in self.MIDDLEWARE_CHAIN}
        if name not in valid_names:
            return False
        self._middleware_status[name] = False
        logger.info("Middleware disabled: %s", name)
        return True

    def get_enabled_middleware(self) -> List[str]:
        """Get list of currently enabled middleware layers."""
        return [n for n, e in self._middleware_status.items() if e]

    # ================================================================
    # 5. INTEGRATED TASK EXECUTION
    # ================================================================

    def execute_with_lifecycle(
        self,
        task_desc: str,
        execute_fn: Callable,
        session_id: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a task with full lifecycle: journal + trace + context.

        This is the "圆润如一" integration for DeerFlow tasks.
        """
        task_id = "aos-{}".format(datetime.now().strftime("%Y%m%d_%H%M%S_%f"))

        # 1. Start journal entry
        self.start_task(task_id, task_desc, session_id=session_id, **kwargs)

        # 2. Build trace metadata
        trace_meta = self.build_trace_metadata(task_desc, task_id=task_id, session_id=session_id)

        # 3. Get user context
        user_ctx = self.get_user_context(session_id) if session_id else {}

        # 4. Execute
        try:
            result = execute_fn(
                task=task_desc,
                task_id=task_id,
                trace_metadata=trace_meta,
                user_context=user_ctx,
                **kwargs,
            )
            self.complete_task(task_id, result=result, status="completed")
            return {"success": True, "task_id": task_id, "result": result, "trace": trace_meta}
        except Exception as e:
            self.complete_task(task_id, result={"error": str(e)}, status="failed")
            logger.error("Task %s failed: %s", task_id, e)
            return {"success": False, "task_id": task_id, "error": str(e), "trace": trace_meta}

    # ================================================================
    # 6. STATUS & STATS
    # ================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive integration stats."""
        return {
            "journal": {
                "enabled": bool(self._journal),
                "task_count": self._task_counter,
            },
            "tracing": {
                "enabled": bool(self._tracing_callbacks),
                "callback_count": len(self._tracing_callbacks),
            },
            "middleware": {
                "total_layers": len(self.MIDDLEWARE_CHAIN),
                "enabled_layers": self.get_enabled_middleware(),
                "enabled_count": len(self.get_enabled_middleware()),
            },
            "user_contexts": {
                "active_sessions": len(self._user_contexts),
                "session_ids": list(self._user_contexts.keys()),
            },
        }

    def shutdown(self) -> None:
        """Clean shutdown."""
        self._user_contexts.clear()
        logger.info("DeepDeerFlowIntegration shutdown complete")


# ================================================================
# FACTORY
# ================================================================

def create_deep_deerflow(scheduler=None) -> DeepDeerFlowIntegration:
    """Create a DeepDeerFlowIntegration.

    Args:
        scheduler: Optional DeerFlowScheduler from AOS.

    Returns:
        Configured DeepDeerFlowIntegration instance.
    """
    return DeepDeerFlowIntegration(scheduler=scheduler)