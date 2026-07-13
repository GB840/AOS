"""成本/延迟/质量感知路由（借 Auriko 内核）真验证。

验证 FabricRegistry 的 route_strategy 能按 cost/latency/quality 排序 live 供给方，
且保留既有「云端用不了就本地」运行时故障转移。这是把 Auriko 的成本套利策略
原生借进 AOS、不依赖其托管网关。
"""
from __future__ import annotations

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from core.fabric.registry import FabricRegistry


class _Fake(BaseAgentAdapter):
    def __init__(self, eid: str, caps, ok: bool = True, result: str = "ok"):
        self._eid = eid
        self._caps = caps
        self._ok = ok
        self._result = result

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return self._caps

    def health(self):
        return True

    def invoke(self, req):
        return InvokeResult(ok=self._ok, data={"served_by": self._eid, "text": self._result})


def _reg(strategy, cost=None, latency=None, quality=None):
    r = FabricRegistry(strategy=strategy, provider_cost=cost,
                       provider_latency=latency, provider_quality=quality)
    r.register(_Fake("cheap", [Capability.LLM_GATEWAY]))
    r.register(_Fake("pricey", [Capability.LLM_GATEWAY]))
    r.register(_Fake("fast", [Capability.LLM_GATEWAY]))
    r.register(_Fake("slow", [Capability.LLM_GATEWAY]))
    r.register(_Fake("good", [Capability.LLM_GATEWAY]))
    r.register(_Fake("bad", [Capability.LLM_GATEWAY]))
    return r


def test_cost_strategy_orders_cheapest_first():
    reg = _reg("cost", cost={"cheap": 10, "pricey": 90})
    order = [a.engine_id for a in reg.providers_for(Capability.LLM_GATEWAY)]
    assert order.index("cheap") < order.index("pricey")


def test_latency_strategy_orders_fastest_first():
    reg = _reg("latency", latency={"fast": 5, "slow": 80})
    order = [a.engine_id for a in reg.providers_for(Capability.LLM_GATEWAY)]
    assert order.index("fast") < order.index("slow")


def test_quality_strategy_orders_best_first():
    reg = _reg("quality", quality={"good": 95, "bad": 20})
    order = [a.engine_id for a in reg.providers_for(Capability.LLM_GATEWAY)]
    assert order.index("good") < order.index("bad")


def test_cost_strategy_with_failover_falls_to_next_best():
    """成本优先 + 最便宜的失败 → 自动 fallback 到次便宜（Auriko 语义）。"""
    reg = FabricRegistry(strategy="cost",
                         provider_cost={"cheap": 10, "mid": 50, "pricey": 90})
    reg.register(_Fake("cheap", [Capability.LLM_GATEWAY], ok=False))
    reg.register(_Fake("mid", [Capability.LLM_GATEWAY], result="mid-served"))
    reg.register(_Fake("pricey", [Capability.LLM_GATEWAY], result="pricey-served"))
    res = reg.route(InvokeRequest(capability=Capability.LLM_GATEWAY, payload={}))
    assert res.ok is True
    # 最便宜 cheap 失败，应落到次便宜 mid
    assert res.data["served_by"] == "mid"
