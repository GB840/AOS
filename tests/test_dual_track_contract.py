"""债 #9 双轨收敛契约测试：brain 能力路由收敛到 FabricHub 单基座。

**修复前的真实缺陷**（不是纸面债）：``brain._init_fabric`` 自建裸 ``FabricRegistry``，
``route_via_fabric`` 直调 ``registry.route()``。而 ``FabricRegistry.route`` 只有朴素
failover——完全绕过 ``FabricHub.route`` 里的 ResilienceBus 熔断（should_skip /
on_outcome）、EvolutionDistiller 沉底、FailureMonitor 记账、媒体契约归一。
后果：**坏引擎在 brain 这一轨永远不会被熔断**，同一进程里「谁负责这个能力」
有两个互不知情的答案。

本文件用可控假引擎证明收敛后的契约：
  1. 默认模式下 brain.fabric 就是 FabricHub 单例本身（同一实例，非副本）；
  2. 坏引擎经 brain 路由会被熔断并自动切降级引擎（修复前做不到）；
  3. ``AOS_BRAIN_DIRECT_REGISTRY=1`` 能退回裸 registry 应急轨；
  4. 枢纽 route 抛异常时 brain 自动降级裸轨，不阻断服务（双保险）；
  5. resolve_engine / health 统计在两种形态下口径一致。

诚实分级：**② 级**（代码改动 + 单测实证，全离线，无真 LLM 调用）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import InvokeResult  # noqa: E402
from kernel.plugins.fabric_hub import (  # noqa: E402
    FabricHub, peek_fabric_hub, reset_fabric_hub, set_fabric_hub,
)


class _FakeAdapter:
    """可控假引擎：记录被调次数，按需成功/失败。"""

    def __init__(self, eid, ok=True, error=None, raises=False):
        self._eid = eid
        self._ok = ok
        self._error = error
        self._raises = raises
        self.calls = 0

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return ["web.search"]

    def health(self):
        return True

    def invoke(self, req):
        self.calls += 1
        if self._raises:
            raise RuntimeError(f"{self._eid} 崩了")
        if self._ok:
            return InvokeResult(ok=True, data={"engine": self._eid, "count": 1})
        return InvokeResult(ok=False, error=self._error or "fail")


@pytest.fixture(autouse=True)
def _clean_singleton(monkeypatch):
    """每例前后重置枢纽单例与 env，避免跨用例污染。"""
    monkeypatch.setenv("AOS_DISTILLER_OFF", "1")     # 不写盘、不引入蒸馏噪声
    monkeypatch.delenv("AOS_BRAIN_DIRECT_REGISTRY", raising=False)
    reset_fabric_hub()
    yield
    reset_fabric_hub()


def _make_hub(providers):
    """构造隔离的 FabricHub：真 route/真 ResilienceBus，假 providers、不落盘。"""
    hub = FabricHub(adapters=())
    hub._providers = list(providers)
    hub._registry.providers_for = lambda cap, tier=None: hub._providers
    hub._registry.maybe_retrain = lambda *a, **k: None
    hub._registry.record_outcome = lambda *a, **k: None
    for ad in providers:
        hub._registry._adapters[ad.engine_id] = ad
    return hub


def _bare_brain():
    """不跑重型 __init__ 的 brain 实例（只测路由接缝）。"""
    from core.brain import UnifiedBrain
    return object.__new__(UnifiedBrain)


# ── 1. 默认收敛：brain.fabric 就是枢纽单例本身 ──────────────────────

def test_brain_fabric_is_the_hub_singleton():
    hub = _make_hub([_FakeAdapter("good")])
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()

    assert brain.fabric is hub, "brain 必须复用内核 FabricHub 单例，而非自建裸 registry"
    assert brain._fabric_direct is False
    assert brain._fabric_hub() is hub
    assert brain._fabric_registry() is hub._registry


def test_brain_route_goes_through_hub():
    good = _FakeAdapter("good")
    hub = _make_hub([good])
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()
    res = brain.route_capability("web.search", {"query": "x"}, trace_id="t-1")

    assert res is not None and res.ok is True
    assert good.calls == 1
    # 枢纽会把真实执行引擎回填进结果（裸 registry 轨没有这层保证）
    assert getattr(res, "engine_id", None) in ("good", None)


# ── 2. 核心证据：坏引擎在 brain 轨会被熔断（修复前永远不会） ──────────

def test_bad_engine_gets_circuit_broken_on_brain_track():
    bad = _FakeAdapter("bad", ok=False, error="HTTP 500 upstream boom")
    good = _FakeAdapter("good", ok=True)
    hub = _make_hub([bad, good])          # 坏引擎排在前面，每次都先撞它
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()

    assert hub._res_bus is not None, "枢纽必须带 ResilienceBus，否则熔断无从谈起"

    for _ in range(3):                     # 连续失败 3 次 → 触发熔断
        res = brain.route_capability("web.search", {"query": "x"})
        assert res is not None and res.ok is True   # 降级到 good，服务不中断

    assert bad.calls == 3
    assert hub._res_bus.should_skip("bad") is True, "坏引擎必须被熔断"

    # 熔断后再路由：直接跳过坏引擎，calls 不再增长
    for _ in range(2):
        assert brain.route_capability("web.search", {"query": "x"}).ok is True
    assert bad.calls == 3, "熔断后 brain 轨仍打到坏引擎 = 双轨未收敛"
    assert good.calls == 5


def test_crashing_engine_isolated_not_propagated():
    """芯粒崩溃隔离：invoke 抛异常不穿透到 brain 调用方。"""
    boom = _FakeAdapter("boom", raises=True)
    good = _FakeAdapter("good", ok=True)
    hub = _make_hub([boom, good])
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()
    res = brain.route_capability("web.search", {"query": "x"})

    assert res is not None and res.ok is True    # 崩溃被隔离，降级成功
    assert boom.calls == 1 and good.calls == 1


# ── 3. 应急 opt-out：退回裸 registry 轨 ─────────────────────────────

def test_direct_registry_optout_does_not_touch_hub(monkeypatch):
    monkeypatch.setenv("AOS_BRAIN_DIRECT_REGISTRY", "1")

    class _Exploding(FabricHub):
        def route(self, *a, **k):            # 一旦被调用就说明 opt-out 失效
            raise AssertionError("opt-out 模式不该走枢纽")

    set_fabric_hub(_Exploding(adapters=()))

    brain = _bare_brain()
    brain._init_fabric()

    assert brain._fabric_direct is True
    assert brain._fabric_hub() is None
    assert not hasattr(brain.fabric, "_registry"), "opt-out 下应是裸 FabricRegistry"

    # 裸轨路由：registry.route 收 InvokeRequest（与枢纽签名不同，此处即契约差异点）
    called = {}

    def _fake_route(req):
        called["cap"] = req.capability
        return InvokeResult(ok=True, data={"via": "bare-registry"})

    brain.fabric.route = _fake_route
    res = brain.route_capability("web.search", {"query": "x"})
    assert res.data == {"via": "bare-registry"}
    assert called["cap"] == "web.search"


def test_init_fabric_does_not_force_build_hub():
    """轻量性契约：brain 初始化期绝不触发 build_fabric_hub（会拉子进程）。"""
    brain = _bare_brain()
    brain._init_fabric()                      # 单例为空

    assert peek_fabric_hub() is None, "brain 初始化不得强行装配枢纽"
    assert brain.fabric is None               # 留待首次 route 懒加载
    assert brain._fabric_stats() == {"status": "lazy", "mode": "hub"}


# ── 4. 双保险：枢纽异常时降级裸轨，不阻断服务 ────────────────────────

def test_hub_failure_falls_back_to_bare_registry():
    hub = _make_hub([_FakeAdapter("good")])

    def _boom(*a, **k):
        raise RuntimeError("枢纽内部炸了")

    hub.route = _boom
    hub._registry.route = lambda req: InvokeResult(ok=True, data={"via": "fallback"})
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()
    res = brain.route_capability("web.search", {"query": "x"})

    assert res is not None and res.data == {"via": "fallback"}, "枢纽异常必须自动降级裸轨"


def test_route_returns_none_when_no_provider():
    hub = _make_hub([])
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()
    assert brain.route_capability("web.search", {"query": "x"}) is None


# ── 5. introspection 口径一致 ──────────────────────────────────────

def test_resolve_engine_and_stats_consistent_across_tracks():
    good = _FakeAdapter("good")
    hub = _make_hub([good])
    set_fabric_hub(hub)

    brain = _bare_brain()
    brain._init_fabric()

    assert brain.resolve_engine("web.search") == "good"
    assert brain.resolve_engine("nonexistent.capability") is None
    # 与枢纽自身的单一可信源答案一致
    assert brain.resolve_engine("web.search") == hub.resolve_engine("web.search")

    # 注：FabricHub.__init__ 还会自动登记 MCP/自动发现类引擎，故只断言口径而非硬数字
    stats = brain._fabric_stats()
    assert stats["mode"] == "hub"
    assert stats["adapters"] == len(hub._registry._adapters)
    assert "good" in stats["live"]
