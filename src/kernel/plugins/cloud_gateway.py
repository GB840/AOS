"""插件：CloudModelGateway — DeepRoute 云端统一 API 网关。

对账表 L4 要求"mistralrs → litellm → 云"三级回退链。
本网关实现第三级（云）：直接走 UNIFIED_API_KEY / UNIFIED_BASE_URL 的
OpenAI 兼容 API，不经过 LiteLLM 中间层。

支持的模型（从 config.yaml / .env）：
- qwen-qwen3.6-27b（默认）
- minimaxai-minimax-m2.5
- doubao-seed-2-0-lite-260428

内核零依赖；本文件位于 plugins/，允许 import 具体实现。
"""

from __future__ import annotations

import time as _time
from typing import Any, AsyncIterator, Dict, List

from ..interfaces import ModelGateway
from ..types import (
    ChatChunk,
    ChatResponse,
    GatewayHealth,
    Message,
    ModelCapabilities,
    ModelInfo,
)

try:
    from openai import OpenAI
    _OPENAI_OK = True
except Exception:
    OpenAI = None  # type: ignore
    _OPENAI_OK = False


class CloudModelGateway(ModelGateway):
    """DeepRoute 云端统一 API 网关（三级回退链的第三级）。

    直接走 OpenAI 兼容的 /v1/chat/completions，作为 mistralrs（本地）
    和 litellm（网关）之后的最后兜底。
    """

    def __init__(self, config: Any = None) -> None:
        if config is None:
            from utils.config import config as _cfg
            config = _cfg
        self._cfg = config
        self._api_key = (
            getattr(config, "UNIFIED_API_KEY", "")
            or __import__("os").environ.get("UNIFIED_API_KEY", "")
        )
        self._base_url = (
            getattr(config, "UNIFIED_BASE_URL", "")
            or __import__("os").environ.get("UNIFIED_BASE_URL", "")
        )
        self._client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        if not _OPENAI_OK or not self._api_key or not self._base_url:
            self._client = None
            return
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=30.0,
            max_retries=1,
        )

    # ---- ModelGateway 接口 ----

    def health(self) -> GatewayHealth:
        if self._client is None:
            return GatewayHealth(
                healthy=False, provider="cloud",
                error="API key or base URL not configured",
            )
        t0 = _time.time()
        try:
            models = self._client.models.list()
            latency = (_time.time() - t0) * 1000
            return GatewayHealth(
                healthy=True, provider="cloud",
                latency_ms=round(latency, 1),
                model_count=len(models.data) if models else 0,
            )
        except Exception as e:
            return GatewayHealth(
                healthy=False, provider="cloud",
                error=str(e), latency_ms=(_time.time() - t0) * 1000,
            )

    def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(model_id="qwen-qwen3.6-27b", provider="cloud",
                      display_name="Qwen 3.6 27B (云端)"),
            ModelInfo(model_id="minimaxai-minimax-m2.5", provider="cloud",
                      display_name="MiniMax M2.5 (云端)"),
            ModelInfo(model_id="doubao-seed-2-0-lite-260428", provider="cloud",
                      display_name="Doubao Seed 2.0 Lite (云端)"),
        ]

    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        if self._client is None:
            return ChatResponse(content="", model=model_id,
                                raw={"error": "cloud gateway not configured"})
        oai_msgs = _to_oai(messages, kwargs)
        model = model_id or "qwen-qwen3.6-27b"
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=oai_msgs,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
                timeout=kwargs.get("timeout", 30.0),
            )
            content = resp.choices[0].message.content or ""
            return ChatResponse(
                content=content, model=model,
                raw={"backend": "cloud", "usage": _usage_dict(resp)},
            )
        except Exception as e:
            return ChatResponse(content="", model=model,
                                raw={"error": f"cloud call failed: {e}"})

    async def stream_chat(self, model_id: str, messages: List[Message],
                          **kwargs: Any) -> AsyncIterator[ChatChunk]:
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content,
                        finish_reason="stop" if resp.content else "error")

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=131072,
            supports_tools=True,
            supports_vision=True,
            supports_streaming=True,
            extra={"backend": "cloud", "provider": "deeproute"},
        )


def _to_oai(messages: List[Message], kwargs: Dict[str, Any]) -> List[Dict[str, str]]:
    if messages:
        out: List[Dict[str, str]] = []
        for m in messages:
            role = m.sender or "user"
            if role not in ("system", "user", "assistant"):
                role = "user"
            out.append({"role": role, "content": _content(m.payload)})
        return out
    prompt = kwargs.get("prompt", "")
    return [{"role": "user", "content": prompt}]


def _content(payload: Any) -> str:
    if isinstance(payload, dict):
        return (payload.get("prompt") or payload.get("message")
                or payload.get("content") or str(payload))
    return str(payload)


def _usage_dict(resp: Any) -> Dict[str, Any]:
    try:
        u = resp.usage
        return {
            "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens,
            "total_tokens": u.total_tokens,
        }
    except Exception:
        return {}


__all__ = ["CloudModelGateway"]