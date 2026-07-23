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
from typing import Any, Iterator

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

# LiteLLM 模型配置：支持多供应商，通过环境变量切换，不绑死智谱。
# - LITELLM_MODEL: provider/model 格式（默认 zhipu/glm-4-flash）
# - LITELLM_API_BASE: OpenAI-compatible 端点（覆盖供应商默认值）
# - LITELLM_API_KEY_ENV: 指定读取哪个 API key 环境变量（默认 ZHIPU_API_KEY）
#   如需走 SiliconFlow: LITELLM_MODEL=openai/Qwen/Qwen2.5-7B-Instruct
#                        LITELLM_API_BASE=https://api.siliconflow.cn/v1
#                        LITELLM_API_KEY_ENV=SILICONFLOW_API_KEY
LITELLM_CONFIG: dict[str, Any] = {
    "default_model": os.environ.get("LITELLM_MODEL", "zhipu/glm-4-flash"),
    "api_base": os.environ.get("LITELLM_API_BASE", ""),
    "api_key_env": os.environ.get("LITELLM_API_KEY_ENV", "ZHIPU_API_KEY"),
}


def _import_litellm():
    """Lazy + 超时守卫导入，避免 import 卡死拖垮调用方。

    超时取 resilience._MODULE_TIMEOUTS["litellm"]=30s，覆盖该包在沙箱负载下
    偶发 >8s 的导入抖动（实测 6-22s），不再被一刀切 dead。
    """
    from ..resilience import guarded_import
    mod = guarded_import("litellm", timeout=30)
    if mod is None:
        raise ImportError("litellm unavailable (import hung or missing)")
    return mod


def _get_llm_override() -> "dict | None":
    """读取请求级 BYOK LLM 覆盖负载（无则 None）。见 utils.llm_override。"""
    try:
        from utils.llm_override import get_llm_override

        return get_llm_override()
    except Exception:  # 模块缺失/异常绝不阻断主流程
        return None


def _resolve_key() -> str | None:
    """Resolve the real API key from process env（多供应商动态配置）。"""
    # 1) explicit per-call payload（由调用方传入）
    # 2) LITELLM_API_KEY_ENV 指定的环境变量（默认 ZHIPU_API_KEY）
    key_env = LITELLM_CONFIG["api_key_env"]
    if key_env:
        v = os.environ.get(key_env)
        if v:
            return v
    # 3) 通用兜底
    for name in ("ZHIPU_API_KEY", "AOS_ZHIPU_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v
    return None


def _build_kwargs(req: InvokeRequest) -> dict[str, Any]:
    """Translate an AOS request into a real litellm.completion() call.

    BYOK 注入（请求级 LLM 覆盖，见 utils.llm_override）：若当前请求上下文带有
    租户 BYOK 默认供应商负载、且本次 payload 未显式带 api_key，则把租户的
    model/api_base/api_key/opts 合并进调用——使 chat / run_task / autopilot 等
    所有 LLM_GATEWAY 调用自动走租户自己填的 key。复用下方既有路由逻辑。

      * model "zhipu/<name>" -> strip prefix, call Zhipu via its OpenAI-
        compatible endpoint (api_base + custom_llm_provider="openai"). This is
        what actually works here (litellm's native zhipu module is unmapped in
        this sandbox, but the OpenAI passthrough is).
      * any other "provider/model" -> hand straight to litellm for native
        routing (openai/anthropic/... when those keys are present).

    Robustness: when this step was fed the *previous* step's whole output dict
    (OrchestrationChiplet passes context through), that dict may carry a
    `model` field belonging to a different plane (e.g. agnes-image-2.1-flash
    from a media step) and a `content` field but no `prompt`. We must NOT let
    an image/video model name poison the text completion, and we must surface
    `content` as the prompt.
    """
    payload = dict(req.payload or {})

    # —— BYOK 请求级覆盖：仅在 payload 未显式带 api_key 时合并租户 key ——
    _ov = _get_llm_override()
    if _ov and not payload.get("api_key"):
        payload["api_key"] = _ov.get("api_key")
        if _ov.get("api_base"):
            payload["api_base"] = _ov["api_base"]
        if _ov.get("model"):
            payload["model"] = _ov["model"]
        if _ov.get("opts"):
            payload.setdefault("opts", {}).update(_ov["opts"])

    model = payload.get("model", LITELLM_CONFIG["default_model"])
    # 防御：上游串味的模型名不能拿来做文本补全，否则 litellm 报
    # "LLM Provider NOT provided"。退回文本默认模型。
    # 拦截：image/video 媒体模型 + agnes 文本模型（agnes 不是 litellm 认的 provider）
    if model and ("image" in model or "video" in model or "agnes" in model):
        model = LITELLM_CONFIG["default_model"]
    messages = payload.get("messages")
    if not messages:
        prompt = payload.get("prompt") or payload.get("content") or payload.get("task") or ""
        messages = [{"role": "user", "content": prompt}]
    kwargs: dict[str, Any] = {"messages": messages}

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

    def advertise_capabilities(self) -> list[Capability]:
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
            logger.warning("litellm invoke failed: %s", e)
            return InvokeResult(ok=False, error=str(e))

    def stream_invoke(self, req: InvokeRequest) -> "Iterator[str]":
        """流式 LLM 调用：逐 token yield delta.content。

        复用 _build_kwargs 的模型路由逻辑（zhipu 兼容 / 串味防御），
        加 stream=True 后遍历 litellm completion 的 chunk 生成器。
        调用方负责 try/except 包裹以捕获密钥/网络/供应商错误。
        """
        litellm = _import_litellm()
        kwargs = _build_kwargs(req)
        kwargs["stream"] = True
        response = litellm.completion(**kwargs)
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def health(self) -> bool:
        # A library plane is "live" when the real package is importable.
        try:
            _import_litellm()
            return True
        except Exception as e:
            logger.debug("litellm health check failed: %s", e)
            return False

    def supported_protocols(self) -> list[str]:
        # LiteLLM is an OpenAI-compatible proxy; the four engines can point
        # their LLM base_url at it to share one inference plane.
        return ["OpenAI"]
