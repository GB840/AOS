"""Real LiteLLM adapter for the AOS open fabric - the INFERENCE PLANE.

LiteLLM (BerriAI, MIT - github.com/BerriAI/litellm) is the unified LLM
gateway: one OpenAI-format call reaches 100+ providers (OpenAI / Anthropic
/ Gemini / Bedrock / Azure ...) with load-balancing, fallbacks and cost
tracking. It is the INFERENCE PLANE that the four behaviour-plane engines
(OpenClaw, Hermes, DeerFlow, AG2) all depend on but none of them
provide.

This adapter is THIN: it translates AOS's `inference.llm` capability into a
real `litellm.completion()` call. AOS still does NOT re-implement an LLM
brain - it delegates to the real OSS. That honours the user's hard rule:
real OSS engines + AOS improves on top, never self-builds the brain.

How the plane is "turned on" in production:
  * Library mode (default here): each engine calls `litellm.completion()`
    directly; AOS routes `inference.llm` through this adapter.
  * Proxy mode (recommended for the 4 engines): run `litellm --model ...`
    as a proxy on :4000 and point OpenClaw/Hermes/DeerFlow `base_url` at it,
    so every engine shares ONE inference gateway with billing + fallbacks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

# Pinned config: a change is a one-line edit. Default targets the LiteLLM
# proxy port; override per-call via payload["model"] / payload["api_base"].
LITELLM_CONFIG: Dict[str, Any] = {
    "api_base": "http://localhost:4000",  # LiteLLM proxy default port
    "default_model": "gpt-4o-mini",       # any provider/model LiteLLM supports
}


def _import_litellm():
    """Lazy import so the adapter is valid code even before `pip install`."""
    import litellm  # type: ignore
    return litellm


class LiteLLMAdapter(BaseAgentAdapter):
    """Thin wrapper over the real LiteLLM gateway (the "fuel" plane)."""

    def __init__(
        self,
        api_base: str = LITELLM_CONFIG["api_base"],
        default_model: str = LITELLM_CONFIG["default_model"],
    ) -> None:
        self._api_base = api_base
        self._default_model = default_model

    @property
    def engine_id(self) -> str:
        return "litellm"

    def advertise_capabilities(self) -> List[Capability]:
        return [Capability.LLM_GATEWAY]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        try:
            litellm = _import_litellm()
            model = req.payload.get("model", self._default_model)
            messages = req.payload.get("messages") or [
                {"role": "user", "content": req.payload.get("prompt", "")}
            ]
            resp = litellm.completion(
                model=model,
                messages=messages,
                api_base=self._api_base,
                **dict(req.payload.get("opts", {})),
            )
            return InvokeResult(
                ok=True,
                data={
                    "content": resp.choices[0].message.content,
                    "model": model,
                },
            )
        except Exception as e:  # missing key / network / provider error
            return InvokeResult(ok=False, error=str(e))

    def health(self) -> bool:
        # A library plane is "live" when the real package is importable.
        try:
            _import_litellm()
            return True
        except Exception:
            return False

    def supported_protocols(self) -> List[str]:
        # LiteLLM is an OpenAI-compatible proxy; the four engines can point
        # their LLM base_url at it to share one inference plane.
        return ["OpenAI"]
