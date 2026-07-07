"""
Audit Logger -- GB/Z 185-2026 compliant audit trail.

Records every significant operation:
- User interactions (chat, commands)
- Agent decisions (tool calls, reasoning)
- System events (startup, shutdown, errors)
- Sub-agent invocations
- Model API calls (provider, tokens, cost)

Audit entries are JSON-structured, timestamped, and queryable.
"""

import logging
import json
import uuid
import threading
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditEvent(Enum):
    """GB/Z 185 audit event types."""
    # System lifecycle
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_CONFIG_CHANGE = "system.config_change"

    # User interactions
    USER_CHAT = "user.chat"
    USER_COMMAND = "user.command"
    USER_FEEDBACK = "user.feedback"

    # Agent operations
    AGENT_DECISION = "agent.decision"
    AGENT_TOOL_CALL = "agent.tool_call"
    AGENT_REASONING = "agent.reasoning"
    AGENT_ERROR = "agent.error"

    # Sub-agent operations
    SUBAGENT_INVOKE = "subagent.invoke"
    SUBAGENT_RESULT = "subagent.result"
    SUBAGENT_ERROR = "subagent.error"
    SUBAGENT_CANCEL = "subagent.cancel"

    # Model API
    MODEL_REQUEST = "model.request"
    MODEL_RESPONSE = "model.response"
    MODEL_TOKEN_USAGE = "model.token_usage"

    # Data operations
    DATA_READ = "data.read"
    DATA_WRITE = "data.write"
    DATA_DELETE = "data.delete"

    # Security
    SECURITY_ACCESS = "security.access"
    SECURITY_DENIED = "security.denied"
    SECURITY_GUARDRAIL = "security.guardrail"


class AuditLogger:
    """GB/Z 185-2026 compliant audit logger.

    Features:
    - Structured JSON audit entries
    - SQLite persistence (via AOSPersistenceBridge)
    - In-memory buffer for high-throughput
    - Event type filtering
    - Retention policy support
    """

    def __init__(self, persistence=None, buffer_size: int = 100):
        """
        Args:
            persistence: AOSPersistenceBridge instance (auto-created if None).
            buffer_size: Max in-memory entries before flush.
        """
        self._persistence = persistence
        self._buffer: List[Dict] = []
        self._buffer_size = buffer_size
        self._lock = threading.Lock()
        self._flush_count = 0
        self._total_events = 0

    def _ensure_persistence(self):
        if self._persistence is None:
            from deerflow.persistence_bridge import get_persistence
            self._persistence = get_persistence()

    def log(self, event: AuditEvent, user_id: str = "system",
            agent_id: str = "", details: Dict[str, Any] = None,
            flush: bool = False):
        """Record an audit event.

        Args:
            event: Event type from AuditEvent enum.
            user_id: Originating user identifier.
            agent_id: Agent identifier (AID).
            details: Event-specific structured data.
            flush: Force immediate write to database.
        """
        entry = {
            "id": str(uuid.uuid4())[:12],
            "event_type": event.value if isinstance(event, AuditEvent) else event,
            "user_id": user_id,
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
        }

        with self._lock:
            self._buffer.append(entry)
            self._total_events += 1

            if flush or len(self._buffer) >= self._buffer_size:
                self._flush()

        logger.debug("Audit: %s by %s", event.value if hasattr(event, 'value') else event, user_id)

    def _flush(self):
        """Write buffered entries to database."""
        if not self._buffer:
            return
        self._ensure_persistence()
        for entry in self._buffer:
            try:
                self._persistence.audit(
                    event_type=entry["event_type"],
                    user_id=entry["user_id"],
                    agent_id=entry["agent_id"],
                    details=entry["details"],
                )
            except Exception as e:
                logger.error("Failed to write audit entry: %s", e)
        count = len(self._buffer)
        self._buffer.clear()
        self._flush_count += 1
        logger.debug("Flushed %d audit entries (total: %d)", count, self._total_events)

    def query(self, event_type: str = None, user_id: str = None,
              limit: int = 100) -> List[Dict[str, Any]]:
        """Query audit log with optional filters."""
        self._ensure_persistence()
        entries = self._persistence.get_audit_log(event_type=event_type, limit=limit)
        if user_id:
            entries = [e for e in entries if e.get("user_id") == user_id]
        return entries

    def get_stats(self) -> dict:
        """Get audit statistics."""
        self._ensure_persistence()
        db_stats = self._persistence.get_stats()
        return {
            "total_events": self._total_events,
            "buffered": len(self._buffer),
            "flushed_batches": self._flush_count,
            "db_entries": db_stats.get("audit_entries", 0),
        }

    def flush(self):
        """Force flush all buffered entries."""
        with self._lock:
            self._flush()

    def shutdown(self):
        """Flush and close."""
        self.flush()
        logger.info("Audit logger shutdown: %d total events", self._total_events)


# Default instance
_default_audit: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _default_audit
    if _default_audit is None:
        _default_audit = AuditLogger()
    return _default_audit
