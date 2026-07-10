"""
DeerFlow Guardrails Bridge -- exposes the REAL DeerFlow guardrails subsystem to AOS.

Wraps:
  - deerflow.guardrails.builtin.AllowlistProvider (tool allow/deny)
  - deerflow.guardrails.provider (GuardrailRequest, GuardrailDecision, GuardrailReason)
  - deerflow.guardrails.middleware.GuardrailMiddleware

Provides AOS with tool-level safety gating, integrated with config.
"""

import logging
from typing import Optional, List, Set

logger = logging.getLogger(__name__)

from deerflow.path_detect import setup_deerflow_env

_DEERFLOW_SRC = setup_deerflow_env()

if _DEERFLOW_SRC:
    try:
        # REAL DeerFlow guardrails
        from deerflow.guardrails.provider import (
            GuardrailDecision,
            GuardrailReason,
            GuardrailRequest,
        )
        from deerflow.guardrails.builtin import AllowlistProvider
        logger.info("✅ DeerFlow Guardrails Bridge 加载成功")
    except ImportError as e:
        logger.warning(f"❌ DeerFlow Guardrails Bridge 导入失败: {e}")
        _DEERFLOW_SRC = None
else:
    logger.warning("⚠️ DeerFlow 源码路径未检测到")


class AOSGuardrails:
    """AOS guardrails -- tool-level safety gating powered by DeerFlow.

    Features:
    - Allowlist mode: only listed tools can execute
    - Denylist mode: listed tools are blocked
    - Audit logging for every guardrail decision
    - Integration with AOS config for dynamic updates
    """

    def __init__(self, mode: str = "denylist"):
        """
        Args:
            mode: "allowlist" (only allowed tools run) or "denylist" (block listed tools)
        """
        self.mode = mode
        self._allowed_tools: Optional[Set[str]] = None
        self._denied_tools: Set[str] = set()
        self._provider: Optional[AllowlistProvider] = None
        self._decision_log: List[dict] = []
        self._rebuild()

    def _rebuild(self):
        """Rebuild the AllowlistProvider from current settings."""
        if self.mode == "allowlist":
            self._provider = AllowlistProvider(
                allowed_tools=list(self._allowed_tools or []),
                denied_tools=list(self._denied_tools),
            )
        else:
            self._provider = AllowlistProvider(
                allowed_tools=None,
                denied_tools=list(self._denied_tools),
            )

    # ---- Configuration ----

    def set_mode(self, mode: str):
        """Switch between 'allowlist' and 'denylist' mode."""
        if mode not in ("allowlist", "denylist"):
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode
        self._rebuild()
        logger.info("Guardrails mode set to: %s", mode)

    def allow_tools(self, *tool_names: str):
        """Add tools to the allowlist."""
        if self._allowed_tools is None:
            self._allowed_tools = set()
        self._allowed_tools.update(tool_names)
        self._rebuild()

    def deny_tools(self, *tool_names: str):
        """Add tools to the denylist."""
        self._denied_tools.update(tool_names)
        self._rebuild()

    def remove_denial(self, *tool_names: str):
        """Remove tools from the denylist."""
        self._denied_tools.difference_update(tool_names)
        self._rebuild()

    def get_allowed_tools(self) -> List[str]:
        return sorted(self._allowed_tools) if self._allowed_tools else ["* (all)"]

    def get_denied_tools(self) -> List[str]:
        return sorted(self._denied_tools)

    # ---- Evaluation ----

    def evaluate(self, tool_name: str, tool_input: dict = None,
                 user_id: str = None) -> GuardrailDecision:
        """Evaluate whether a tool call should be allowed.

        Args:
            tool_name: Name of the tool being called.
            tool_input: Optional tool input for context-aware decisions.
            user_id: Optional user ID for per-user policies.

        Returns:
            GuardrailDecision with allow/reject and reasons.
        """
        request = GuardrailRequest(
            tool_name=tool_name,
            tool_input=tool_input or {},
            user_id=user_id,
        )
        decision = self._provider.evaluate(request)

        # Audit log
        self._decision_log.append({
            "tool_name": tool_name,
            "allowed": decision.allow,
            "reasons": [r.code for r in decision.reasons],
            "user_id": user_id,
        })
        # Keep log bounded
        if len(self._decision_log) > 10000:
            self._decision_log = self._decision_log[-5000:]

        if not decision.allow:
            logger.warning("Guardrail BLOCKED: tool=%s reasons=%s",
                           tool_name, [r.code for r in decision.reasons])
        return decision

    def is_allowed(self, tool_name: str, tool_input: dict = None,
                   user_id: str = None) -> bool:
        """Quick check: is this tool call allowed?"""
        return self.evaluate(tool_name, tool_input, user_id).allow

    # ---- Audit ----

    def get_decision_log(self, limit: int = 100) -> List[dict]:
        """Get recent guardrail decisions for audit."""
        return self._decision_log[-limit:]

    def get_stats(self) -> dict:
        """Get guardrail statistics."""
        total = len(self._decision_log)
        allowed = sum(1 for d in self._decision_log if d["allowed"])
        blocked = total - allowed
        return {
            "mode": self.mode,
            "total_decisions": total,
            "allowed": allowed,
            "blocked": blocked,
            "allowed_tools_count": len(self._allowed_tools) if self._allowed_tools else -1,
            "denied_tools_count": len(self._denied_tools),
        }


# ---- Default AOS guardrails (safe defaults) ----

DEFAULT_DENIED_TOOLS = [
    # Dangerous system operations
    "execute_bash", "shell", "system",
]

# Create a module-level default instance
_default_guardrails: Optional[AOSGuardrails] = None


def get_guardrails() -> AOSGuardrails:
    """Get or create the default AOS guardrails instance."""
    global _default_guardrails
    if _default_guardrails is None:
        _default_guardrails = AOSGuardrails(mode="denylist")
        _default_guardrails.deny_tools(*DEFAULT_DENIED_TOOLS)
    return _default_guardrails
