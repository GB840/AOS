"""插件：把现有 LiteLLMAdapter（推理平面）登记为 ModelGateway。

内核只认 ModelGateway(ABC)。本文件把已有的 LiteLLMAdapter 薄封装成
ModelGateway，从而使 100+ 模型（OpenAI/Anthropic/Zhipu/...）作为内核插件
挂入，内核一行不改。内核零依赖，本文件才允许 import 具体实现。
"""

from __future__ import annotations

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

# 延迟导入具体实现
from core.fabric.adapters.litellm_adapter import LiteLLMAdapter


class LiteLLMModelGateway(ModelGateway):
    """把 LiteLLMAdapter 的能力翻译为 ModelGateway 接口。"""

    def __init__(self, adapter: LiteLLMAdapter | None = None) -> None:
        self._adapter = adapter or LiteLLMAdapter()

    def health(self) -> GatewayHealth:
        import time
        t0 = time.time()
        try:
            models = self._adapter.list_models() if hasattr(self._adapter, 'list_models') else []
            latency = (time.time() - t0) * 1000
            return GatewayHealth(
                healthy=True, provider="litellm",
                latency_ms=round(latency, 1),
                model_count=len(models) if models else 1,
            )
        except Exception as e:
            return GatewayHealth(healthy=False, provider="litellm",
                                error=str(e), latency_ms=(time.time() - t0) * 1000)

    def list_models(self) -> List[ModelInfo]:
        # LiteLLM 网关覆盖 100+ 模型；此处暴露默认模型作为代表，
        # 真实枚举可经 litellm.get_supported_models() 扩展（不阻塞内核）。
        return [
            ModelInfo(model_id="zhipu/glm-4-flash", provider="litellm",
                      display_name="智谱 GLM-4-Flash"),
        ]

    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        payload: Dict[str, Any] = {"model": model_id}
        if messages:
            payload["messages"] = [
                {"role": m.sender if m.sender else "user", "content": _content(m.payload)}
                for m in messages
            ]
        else:
            payload["prompt"] = kwargs.get("prompt", "")
        payload.update(kwargs)

        req = _to_invoke_request(payload)
        res = self._adapter.invoke(req)
        if res.ok:
            return ChatResponse(
                content=res.data.get("content", ""),
                model=res.data.get("model", model_id),
                raw=res.data,
            )
        # 无 key / 网络错误时优雅返回空响应（内核不崩）
        return ChatResponse(content="", model=model_id, raw={"error": res.error})

    async def stream_chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> AsyncIterator[ChatChunk]:
        # 现有适配器未实现原生流；退化为单次完整结果作为一个分片。
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content)

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=0,
            supports_tools=True,
            supports_vision=False,
            supports_streaming=True,
        )


def _content(payload: Dict[str, Any]) -> str:
    if isinstance(payload, dict):
        return payload.get("prompt") or payload.get("message") or payload.get("content") or str(payload)
    return str(payload)


def _to_invoke_request(payload: Dict[str, Any]):
    from core.fabric.adapter import InvokeRequest
    from core.fabric.capability import Capability
    return InvokeRequest(capability=Capability.LLM_GATEWAY, payload=payload)
