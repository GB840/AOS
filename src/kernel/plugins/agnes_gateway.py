"""插件：把 AgnesAdapter（多模态平面）登记为 ModelGateway。

内核只认 ModelGateway(ABC)。本文件把 AgnesAdapter 薄封装成 ModelGateway，
使 Agnes 的 agnes-2.0-flash 可作为内核聊天后端挂入（与 litellm 平级）。
内核零依赖，本文件才 import 具体实现。

注意：Agnes 现为纯 LLM Gateway（仅 chat/inference.llm），图像/视频已退出 fabric 能力路由、改由 media-gen（国产）/comfyui（本地）服务；
本网关只覆盖 chat 平面（inference.llm）。
"""
from __future__ import annotations

import time
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
from core.fabric.adapters.agnes_adapter import AgnesAdapter, AGNES_DEFAULTS


class AgnesModelGateway(ModelGateway):
    """把 Agnes 的聊天能力翻译为 ModelGateway 接口。"""

    def __init__(self, adapter: AgnesAdapter | None = None) -> None:
        self._adapter = adapter or AgnesAdapter()

    def health(self) -> GatewayHealth:
        t0 = time.time()
        try:
            ok = self._adapter.health()
            latency = (time.time() - t0) * 1000
            return GatewayHealth(
                healthy=ok, provider="agnes",
                latency_ms=round(latency, 1),
                model_count=1,
                error=None if ok else "AGNES_API_KEY 未配置 / Base URL 不可达",
            )
        except Exception as e:
            return GatewayHealth(healthy=False, provider="agnes",
                                error=str(e), latency_ms=(time.time() - t0) * 1000)

    def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(model_id="agnes/agnes-2.0-flash", provider="agnes",
                      display_name="Agnes 2.0 Flash (512K)"),
        ]

    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        payload: Dict[str, Any] = {"model": AGNES_DEFAULTS["text_model"]}
        if messages:
            payload["messages"] = [
                {"role": m.sender if m.sender else "user", "content": _content(m.payload)}
                for m in messages
            ]
        else:
            payload["prompt"] = kwargs.get("prompt", "")
        payload.update(kwargs)

        from core.fabric.adapter import InvokeRequest
        from core.fabric.capability import Capability
        req = InvokeRequest(capability=Capability.LLM_GATEWAY, payload=payload)
        res = self._adapter.invoke(req)
        if res.ok:
            return ChatResponse(
                content=res.data.get("content", ""),
                model=res.data.get("model", model_id),
                raw=res.data,
            )
        return ChatResponse(content="", model=model_id, raw={"error": res.error})

    async def stream_chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> AsyncIterator[ChatChunk]:
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content)

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=512_000,     # agnes-2.0-flash 上下文窗口 512K
            supports_tools=True,
            supports_vision=True,       # Agnes 套件含图像/视频多模态
            supports_streaming=True,
        )


def _content(payload: Dict[str, Any]) -> str:
    if isinstance(payload, dict):
        return payload.get("prompt") or payload.get("message") or payload.get("content") or str(payload)
    return str(payload)
