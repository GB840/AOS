"""Real Langfuse adapter for the AOS open fabric - the OBSERVABILITY PLANE.

Langfuse (langfuse, MIT - github.com/langfuse/langfuse) is the open-source
LLM engineering platform: tracing, evals, prompt management and guardrails.
In 2026 "agent observability" became its own discipline; without it an agent
system is a black box that fails silently. Langfuse self-hosts or runs as a
cloud service and speaks OpenTelemetry.

This is the OBSERVABILITY plane - the four behaviour engines log nothing
useful on their own. AOS centralizes tracing through this thin adapter.

Thin adapter: translates AOS `system.observability` into real Langfuse
trace / span calls. AOS does NOT build its own telemetry - it delegates to
the real OSS.
"""
from __future__ import annotations

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability


def _import_langfuse():
    """Lazy import so the adapter is valid code even before `pip install`."""
    from langfuse import Langfuse  # type: ignore
    return Langfuse


class LangfuseAdapter(BaseAgentAdapter):
    """Thin wrapper over the real Langfuse observability platform."""

    def __init__(
        self,
        public_key: str = "",
        secret_key: str = "",
        host: str = "https://cloud.langfuse.com",
    ) -> None:
        self._public_key = public_key
        self._secret_key = secret_key
        self._host = host

    @property
    def engine_id(self) -> str:
        return "langfuse"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.OBSERVABILITY]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        try:
            Langfuse = _import_langfuse()
            lf = Langfuse(
                public_key=self._public_key,
                secret_key=self._secret_key,
                host=self._host,
            )
            action = req.payload.get("action", "trace")
            if action == "trace":
                trace = lf.trace(
                    name=req.payload.get("name", "aos-trace"),
                    input=req.payload.get("input"),
                    metadata=req.payload.get("metadata"),
                )
                if "output" in req.payload:
                    trace.update(output=req.payload["output"])
                lf.flush()
                return InvokeResult(ok=True, data={"trace_id": trace.id})
            if action == "span":
                trace = lf.trace(name=req.payload.get("trace_name", "aos"))
                span = trace.span(name=req.payload.get("name", "step"))
                if "output" in req.payload:
                    span.end(output=req.payload["output"])
                lf.flush()
                return InvokeResult(ok=True, data={"span_id": span.id})
            return InvokeResult(ok=False, error=f"unknown action {action}")
        except Exception as e:  # not configured / offline
            return InvokeResult(ok=False, error=str(e))

    def health(self) -> bool:
        try:
            _import_langfuse()
            return True
        except Exception:
            return False

    def supported_protocols(self) -> list[str]:
        return ["OpenTelemetry"]
