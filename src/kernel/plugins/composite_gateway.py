"""插件：组合多个 ModelGateway，按优先级做网关级降级。

对账表要求"mistralrs 主、Ollama/云 兜底"。内核只有一个 `_model_gateway` 槽，
而 FallbackChain 只在单个 gateway 内部按 model_id 降级，无法跨 gateway 降级。
本组合网关把 [mistralrs, litellm] 串成一条链：mistralrs 空/异常 → 落 litellm。

内核零依赖不变；本文件位于 plugins/，只依赖内核接口与其它插件。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, List

from ..interfaces import ModelGateway
from ..types import ChatChunk, ChatResponse, Message, ModelCapabilities, ModelInfo


class CompositeModelGateway(ModelGateway):
    """按顺序尝试多个 ModelGateway，第一个给出非空内容者胜出。

    gateways[0] 为首选（mistralrs），其后为兜底（litellm→云）。
    model_id 命中某网关时优先用该网关；未命中则从链首依次尝试。
    """

    def __init__(self, gateways: List[ModelGateway]) -> None:
        if not gateways:
            raise ValueError("CompositeModelGateway 需要至少一个 gateway")
        self._gateways = gateways
        # 建立 model_id → gateway 索引，命中即直达
        self._index = {}
        for gw in gateways:
            try:
                for m in gw.list_models():
                    self._index.setdefault(m.model_id, gw)
            except Exception:
                continue

    def list_models(self) -> List[ModelInfo]:
        out: List[ModelInfo] = []
        seen = set()
        for gw in self._gateways:
            try:
                for m in gw.list_models():
                    if m.model_id not in seen:
                        seen.add(m.model_id)
                        out.append(m)
            except Exception:
                continue
        return out

    def _ordered(self, model_id: str) -> List[ModelGateway]:
        """命中的网关排最前，其余按原优先级兜底。"""
        primary = self._index.get(model_id)
        if primary is None:
            return list(self._gateways)
        return [primary] + [g for g in self._gateways if g is not primary]

    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        last: ChatResponse | None = None
        for gw in self._ordered(model_id):
            # 兜底网关不认这个 model_id 时，让其用自己的默认模型
            use_id = model_id if model_id in _safe_ids(gw) else _default_id(gw, model_id)
            resp = gw.chat(use_id, messages, **kwargs)
            last = resp
            if resp.content:  # 非空即成功
                return resp
        return last or ChatResponse(content="", model=model_id,
                                    raw={"error": "all gateways failed"})

    async def stream_chat(self, model_id: str, messages: List[Message],
                          **kwargs: Any) -> AsyncIterator[ChatChunk]:
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content,
                        finish_reason="stop" if resp.content else "error")

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        gw = self._index.get(model_id, self._gateways[0])
        return gw.get_capabilities(model_id)


def _safe_ids(gw: ModelGateway) -> set:
    try:
        return {m.model_id for m in gw.list_models()}
    except Exception:
        return set()


def _default_id(gw: ModelGateway, fallback: str) -> str:
    ids = _safe_ids(gw)
    return next(iter(ids)) if ids else fallback


__all__ = ["CompositeModelGateway"]
