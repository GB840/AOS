"""全局高中低三级动态路由真验证（用户铁律：不要写死单档）。

验证四件事：
1. 档位是路由第一维度：高档引擎排在低档之前（auto 从高档起）。
2. 向下级联：高档失败自动落到中/低档（端云合作 / 云端用不了就本地）。
3. 请求可指定起始档（high/medium/low），只从该档向低档尝试。
4. 能力分级：capability_tiers() / tiers_for() 给出某能力可达档位。
"""
from __future__ import annotations

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import (
    Capability,
    TIER_HIGH,
    TIER_MEDIUM,
    TIER_LOW,
    TIER_AUTO,
    ENGINE_TIER,
    capability_tiers,
)
from core.fabric.registry import FabricRegistry


class _Fake(BaseAgentAdapter):
    def __init__(self, eid, caps, tier, result=InvokeResult(ok=True, data={}), health=True):
        self._eid = eid
        self._caps = caps
        self._tier = tier
        self._result = result
        self._health = health

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return list(self._caps)

    def tier(self):
        return self._tier

    def health(self):
        return self._health

    def invoke(self, req):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _ok(eid):
    return InvokeResult(ok=True, data={"served_by": eid})


def _reg():
    r = FabricRegistry()
    r.register(_Fake("local_heavy", [Capability.LLM_GATEWAY], TIER_HIGH, _ok("local_heavy")))
    r.register(_Fake("cloud_good", [Capability.LLM_GATEWAY], TIER_MEDIUM, _ok("cloud_good")))
    r.register(_Fake("free_fallback", [Capability.LLM_GATEWAY], TIER_LOW, _ok("free_fallback")))
    return r


def test_tier_is_primary_dimension_auto():
    """auto：高档排在最前，低档最后（档位优先于偏好）。"""
    r = _reg()
    order = [a.engine_id for a in r.providers_for(Capability.LLM_GATEWAY)]
    assert order.index("local_heavy") < order.index("cloud_good") < order.index("free_fallback")


def test_cascade_high_to_low_on_failure():
    """高档失败 → 级联到中档 → 低档（端云合作核心路径）。"""
    r = FabricRegistry()
    r.register(_Fake("local_heavy", [Capability.LLM_GATEWAY], TIER_HIGH,
                     InvokeResult(ok=False, error="gpu oom")))
    r.register(_Fake("cloud_good", [Capability.LLM_GATEWAY], TIER_MEDIUM, _ok("cloud_good")))
    r.register(_Fake("free_fallback", [Capability.LLM_GATEWAY], TIER_LOW, _ok("free_fallback")))
    res = r.route(InvokeRequest(capability=Capability.LLM_GATEWAY, payload={}))
    assert res.ok
    assert res.data["served_by"] == "cloud_good"  # 高失败，落中


def test_request_low_tier_only_tries_low():
    """请求 low 档：只从该档尝试，不向上跳到高/中档。"""
    r = _reg()
    # 让中/高档都 ok，低档失败 → 若请求 low 不应回退到高/中
    r.register(_Fake("free_fallback", [Capability.LLM_GATEWAY], TIER_LOW,
                     InvokeResult(ok=False, error="rate limited")))
    res = r.route(InvokeRequest(capability=Capability.LLM_GATEWAY,
                                payload={}, tier=TIER_LOW))
    assert res.ok is False  # 低档失败，不向上借高/中
    assert "free_fallback" in res.error


def test_request_medium_tier_tries_medium_then_low():
    """请求 medium：中档先试，失败级联到低档。"""
    r = FabricRegistry()
    r.register(_Fake("cloud_good", [Capability.LLM_GATEWAY], TIER_MEDIUM,
                     InvokeResult(ok=False, error="cloud 503")))
    r.register(_Fake("free_fallback", [Capability.LLM_GATEWAY], TIER_LOW, _ok("free_fallback")))
    res = r.route(InvokeRequest(capability=Capability.LLM_GATEWAY,
                                payload={}, tier=TIER_MEDIUM))
    assert res.ok
    assert res.data["served_by"] == "free_fallback"


def test_capability_grading_static():
    """能力分级静态视图：某能力可被哪些档位满足。"""
    # PLANNING 由 ag2(高) + deerflow(中) 提供 → 高、中两档
    assert capability_tiers(Capability.PLANNING) == [TIER_HIGH, TIER_MEDIUM]
    # LLM_GATEWAY 由 openclaw/agnes/litellm(中) 提供 → 中档
    assert capability_tiers(Capability.LLM_GATEWAY) == [TIER_MEDIUM]


def test_capability_grading_live():
    """tiers_for 给出当前 live 可达档位。"""
    r = _reg()
    live = r.tiers_for(Capability.LLM_GATEWAY)
    assert live == [TIER_HIGH, TIER_MEDIUM, TIER_LOW]
    # 杀掉高/中档后只剩低档
    r.register(_Fake("local_heavy", [Capability.LLM_GATEWAY], TIER_HIGH, health=False))
    r.register(_Fake("cloud_good", [Capability.LLM_GATEWAY], TIER_MEDIUM, health=False))
    assert r.tiers_for(Capability.LLM_GATEWAY) == [TIER_LOW]


def test_registry_default_tier_is_auto():
    assert FabricRegistry().tier == TIER_AUTO
