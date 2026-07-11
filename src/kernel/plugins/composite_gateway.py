"""插件：组合多个 ModelGateway，按优先级做网关级降级。

对账表要求"mistralrs 主、Ollama/云 兜底"。内核只有一个 `_model_gateway` 槽，
而 FallbackChain 只在单个 gateway 内部按 model_id 降级，无法跨 gateway 降级。
本组合网关把 [mistralrs, litellm, cloud] 串成一条链：mistralrs 空/异常 → 落 litellm → 落 cloud。

v2 升级：加入健康检查，不可达的网关自动跳过，避免"单点模型即单点故障"。
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, List

from ..interfaces import ModelGateway
from ..types import ChatChunk, ChatResponse, GatewayHealth, Message, ModelCapabilities, ModelInfo


class CompositeModelGateway(ModelGateway):
    """按顺序尝试多个 ModelGateway，第一个给出非空内容者胜出。

    gateways[0] 为首选（mistralrs），其后为兜底（litellm→cloud）。
    model_id 命中某网关时优先用该网关；未命中则从链首依次尝试。
    不可达的网关（health()=False）自动跳过。
    """

    def __init__(self, gateways: List[ModelGateway]) -> None:
        if not gateways:
            raise ValueError("CompositeModelGateway 需要至少一个 gateway")
        self._gateways = gateways
        self._health_cache: Dict[str, GatewayHealth] = {}
        self._last_health_check: float = 0.0
        # 建立 model_id → gateway 索引，命中即直达
        self._index: Dict[str, ModelGateway] = {}
        for gw in gateways:
            try:
                for m in gw.list_models():
                    self._index.setdefault(m.model_id, gw)
            except Exception:
                continue

    # ---- 健康检查 ----

    def health(self) -> GatewayHealth:
        """返回首个健康网关的状态，或首个不健康网关的错误。"""
        for gw in self._gateways:
            h = gw.health()
            if h.healthy:
                return h
        return GatewayHealth(healthy=False, provider="composite",
                            error="all gateways unhealthy")

    def check_all_health(self) -> List[GatewayHealth]:
        """检查所有网关健康状态，缓存 30 秒。"""
        now = time.time()
        if now - self._last_health_check < 30 and self._health_cache:
            return list(self._health_cache.values())
        results = []
        for gw in self._gateways:
            h = gw.health()
            self._health_cache[h.provider] = h
            results.append(h)
        self._last_health_check = now
        return results

    def _healthy_gateways(self) -> List[ModelGateway]:
        """返回当前健康的网关列表（按优先级排序）。"""
        healthy = []
        for gw in self._gateways:
            h = self._health_cache.get(self._gw_provider(gw))
            if h is None:
                h = gw.health()
                self._health_cache[self._gw_provider(gw)] = h
            if h.healthy:
                healthy.append(gw)
        return healthy or self._gateways  # 全挂时仍尝试所有网关

    def _gw_provider(self, gw: ModelGateway) -> str:
        try:
            return gw.health().provider
        except Exception:
            return str(id(gw))

    # ---- ModelGateway 接口 ----

    def list_models(self) -> List[ModelInfo]:
        out: List[ModelInfo] = []
        seen: set = set()
        for gw in self._healthy_gateways():
            try:
                for m in gw.list_models():
                    if m.model_id not in seen:
                        seen.add(m.model_id)
                        out.append(m)
            except Exception:
                continue
        return out

    def _ordered(self, model_id: str) -> List[ModelGateway]:
        """命中的网关排最前，其余按原优先级兜底。仅返回健康网关。"""
        primary = self._index.get(model_id)
        healthy = self._healthy_gateways()
        if primary is not None and primary in healthy:
            return [primary] + [g for g in healthy if g is not primary]
        return healthy

    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        last: ChatResponse | None = None
        for gw in self._ordered(model_id):
            use_id = model_id if model_id in _safe_ids(gw) else _default_id(gw, model_id)
            resp = gw.chat(use_id, messages, **kwargs)
            last = resp
            if resp.content:
                return resp
        return last or ChatResponse(content="", model=model_id,
                                    raw={"error": "all gateways failed"})

    async def stream_chat(self, model_id: str, messages: List[Message],
                          **kwargs: Any) -> AsyncIterator[ChatChunk]:
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content,
                        finish_reason="stop" if resp.content else "error")

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        gw = self._index.get(model_id)
        if gw is not None:
            return gw.get_capabilities(model_id)
        for gw in self._healthy_gateways():
            return gw.get_capabilities(model_id)
        return ModelCapabilities()


def _safe_ids(gw: ModelGateway) -> set:
    try:
        return {m.model_id for m in gw.list_models()}
    except Exception:
        return set()


def _default_id(gw: ModelGateway, fallback: str) -> str:
    ids = _safe_ids(gw)
    return next(iter(ids)) if ids else fallback


__all__ = ["CompositeModelGateway"]
