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

import os
from typing import Any, Dict, List, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

# Pinned config: a change is a one-line edit. Library mode (default) calls
# `litellm.completion()` directly; override per-call via payload["model"] /
# payload["api_key"] / payload["api_base"]. The default model reuses the
# Zhipu key already present in the process environment (see config.py).
LITELLM_CONFIG: Dict[str, Any] = {
    "api_base": "https://open.bigmodel.cn/api/paas/v4",  # Zhipu OpenAI-compat
    "default_model": "zhipu/glm-4-flash",                # provider/model form
}


def _import_litellm():
    """Lazy import so the adapter is valid code even before `pip install`."""
    import litellm  # type: ignore
    return litellm


def _resolve_key() -> Optional[str]:
    """Resolve the real API key from process env (set by start_all.sh / .env)."""
    # 1) explicit per-call payload
    # 2) env var named in config.LITELLM_API_KEY_ENV (e.g. ZHIPU_API_KEY)
    # 3) generic fallbacks
    for name in ("ZHIPU_API_KEY", "AOS_ZHIPU_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v
    return None


def _build_kwargs(req: "InvokeRequest") -> Dict[str, Any]:
    """Translate an AOS request into a real litellm.completion() call.

    UNIFIED routing (the inference plane):
      * model "zhipu/<name>" -> strip prefix, call Zhipu via its OpenAI-
        compatible endpoint (api_base + custom_llm_provider="openai"). This is
        what actually works here (litellm's native zhipu module is unmapped in
        this sandbox, but the OpenAI passthrough is).
      * any other "provider/model" -> hand straight to litellm for native
        routing (openai/anthropic/... when those keys are present).
    """
    payload = req.payload or {}
    model = payload.get("model", LITELLM_CONFIG["default_model"])
    messages = payload.get("messages") or [
        {"role": "user", "content": payload.get("prompt", "")}
    ]
    kwargs: Dict[str, Any] = {"messages": messages}

    if model.startswith("zhipu/"):
        kwargs["model"] = model.split("/", 1)[1]
        kwargs["custom_llm_provider"] = "openai"
        kwargs["api_base"] = payload.get("api_base") or LITELLM_CONFIG["api_base"]
    else:
        kwargs["model"] = model
        api_base = payload.get("api_base") or LITELLM_CONFIG["api_base"]
        if api_base:
            kwargs["api_base"] = api_base

    kwargs["api_key"] = payload.get("api_key") or _resolve_key()
    kwargs.update(dict(payload.get("opts", {})))
    return kwargs


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
            kwargs = _build_kwargs(req)
            resp = litellm.completion(**kwargs)
            return InvokeResult(
                ok=True,
                data={
                    "content": resp.choices[0].message.content,
                    "model": req.payload.get("model", self._default_model),
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
