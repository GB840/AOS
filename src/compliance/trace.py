"""
Operation Tracer -- end-to-end operation traceability.

Creates trace spans for every operation flowing through AOS:
  User Request -> Intent Analysis -> Tool Call -> Sub-agent -> Response

Each span records:
- Span ID + parent span ID (tree structure)
- Start/end timestamps
- Operation type and details
- Input/output snapshots (optional)
- Error information (if failed)

Integrates with:
- AuditLogger (structured audit trail)
- Langfuse tracing (via DeerFlow)
"""

import uuid
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class TraceSpan:
    """A single trace span within an operation trace."""

    def __init__(self, name: str, span_type: str,
                 parent_span_id: str = None,
                 trace_id: str = None):
        self.span_id = str(uuid.uuid4())[:16]
        self.parent_span_id = parent_span_id
        self.trace_id = trace_id or str(uuid.uuid4())[:16]
        self.name = name
        self.span_type = span_type
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.status = SpanStatus.OK
        self.input_data: Optional[Dict] = None
        self.output_data: Optional[Dict] = None
        self.error: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self._children: List[TraceSpan] = []

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def add_child(self, child: 'TraceSpan'):
        """Add a child span."""
        child.parent_span_id = self.span_id
        child.trace_id = self.trace_id
        self._children.append(child)

    def finish(self, status: SpanStatus = None, error: str = None,
               output: Dict = None):
        """Mark the span as complete."""
        self.end_time = time.time()
        if status:
            self.status = status
        if error:
            self.error = error
        if output:
            self.output_data = output

    def to_dict(self, include_children: bool = True) -> dict:
        """Export span as JSON-safe dict."""
        d = {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "type": self.span_type,
            "status": self.status.value,
            "duration_ms": round(self.duration_ms, 2),
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "error": self.error,
            "metadata": self.metadata,
        }
        if include_children and self._children:
            d["children"] = [c.to_dict() for c in self._children]
        return d


class OperationTracer:
    """End-to-end operation trace manager.

    Tracks operation trees: each user request creates a new trace
    with child spans for intent analysis, tool calls, sub-agents, etc.
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: Dict[str, TraceSpan] = {}  # trace_id -> root span
        self._max_traces = max_traces
        self._lock = threading.Lock()
        self._total_traces = 0
        self._audit = None

    @property
    def audit(self):
        if self._audit is None:
            from compliance.audit import get_audit_logger
            self._audit = get_audit_logger()
        return self._audit

    def start_trace(self, name: str, span_type: str = "request",
                    trace_id: str = None) -> TraceSpan:
        """Start a new trace (root span). Returns the root span."""
        span = TraceSpan(name=name, span_type=span_type, trace_id=trace_id)

        with self._lock:
            self._traces[span.trace_id] = span
            self._total_traces += 1

            # Evict old traces if exceeding limit
            if len(self._traces) > self._max_traces:
                oldest = min(self._traces.keys(),
                             key=lambda k: self._traces[k].start_time,
                             default=None)
                if oldest:
                    del self._traces[oldest]

        logger.debug("Trace started: %s (id=%s)", name, span.trace_id)
        self.audit.log(
            event="trace.start",
            details={"trace_id": span.trace_id, "name": name, "type": span_type},
        )
        return span

    @contextmanager
    def span(self, name: str, span_type: str = "operation",
             parent: TraceSpan = None, trace_id: str = None):
        """Context manager for creating a child span.

        Usage:
            with tracer.span("analyze_intent", parent=root_span) as span:
                result = do_analysis()
                span.finish(output={"intent": result})
        """
        span = TraceSpan(
            name=name, span_type=span_type,
            parent_span_id=parent.span_id if parent else None,
            trace_id=trace_id or (parent.trace_id if parent else None),
        )
        if parent:
            parent.add_child(span)

        try:
            yield span
        except Exception as e:
            span.finish(status=SpanStatus.ERROR, error=str(e))
            raise
        else:
            if span.end_time is None:
                span.finish()

    def get_trace(self, trace_id: str) -> Optional[TraceSpan]:
        """Get a trace by ID."""
        return self._traces.get(trace_id)

    def list_traces(self, limit: int = 50) -> List[dict]:
        """List recent traces."""
        with self._lock:
            traces = sorted(
                self._traces.values(),
                key=lambda t: t.start_time,
                reverse=True,
            )[:limit]
        return [t.to_dict(include_children=False) for t in traces]

    def get_stats(self) -> dict:
        """Get tracer statistics."""
        with self._lock:
            return {
                "total_traces": self._total_traces,
                "active_traces": len(self._traces),
                "recent_traces": [
                    {"trace_id": t.trace_id, "name": t.name,
                     "duration_ms": round(t.duration_ms, 2),
                     "children": len(t._children)}
                    for t in sorted(self._traces.values(),
                                    key=lambda x: x.start_time, reverse=True)[:10]
                ],
            }

    def shutdown(self):
        """Clean up."""
        self._traces.clear()
        logger.info("OperationTracer shutdown: %d total traces", self._total_traces)


# Default instance
_default_tracer: Optional[OperationTracer] = None


def get_tracer() -> OperationTracer:
    global _default_tracer
    if _default_tracer is None:
        _default_tracer = OperationTracer()
    return _default_tracer
