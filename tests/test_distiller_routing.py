"""白盒蒸馏接入 FabricHub 实时路由（任务278）。

验证：蒸馏器判不可靠的引擎在 route() 内被沉底（排到末尾）；
有可靠备选且 AOS_DISTILLER_DROP=1 才硬跳过；无备选仍作兜底尝试（诚实不丢能力）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import InvokeResult
from kernel.evolution_distiller import EvolutionDistiller
from kernel.plugins.fabric_hub import FabricHub


class _FakeAdapter:
    def __init__(self, eid, ok, error=None):
        self._eid = eid
        self._ok = ok
        self._error = error
        self.invoked = False

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return ["web.search"]

    def health(self):
        return True

    def invoke(self, req):
        self.invoked = True
        if self._ok:
            return InvokeResult(ok=True, data={"results": [{"url": "x"}], "count": 1})
        return InvokeResult(ok=False, error=self._error or "fail")


def _make_hub(distiller, drop=False):
    hub = FabricHub(adapters=(), distiller=distiller)
    hub._distill_drop = drop
    # 隔离 registry 的副作用（真实 providers_for / 重训 / 落盘），只测 reorder 逻辑。
    hub._registry.providers_for = lambda cap, tier=None: hub._providers
    hub._registry.maybe_retrain = lambda *a, **k: None
    hub._registry.record_outcome = lambda *a, **k: None
    return hub


def _sink_bing(store):
    d = EvolutionDistiller(store_path=store)
    for _ in range(6):
        d.record_outcome("web.search", "bing", ok=False, error="boom")
    return d


def test_distiller_moves_unreliable_engine_last(tmp_path):
    d = _sink_bing(str(tmp_path / "d.jsonl"))
    assert any(s["engine"] == "bing" for s in d.distill())

    hub = _make_hub(d)
    good = _FakeAdapter("good", ok=True)
    bad = _FakeAdapter("bing", ok=False, error="boom")
    hub._providers = [bad, good]  # 原始顺序把不可靠的排前面
    res = hub.route("web.search", {"query": "x"})
    assert res.ok is True
    assert good.invoked is True
    assert bad.invoked is False  # 被沉底，good 先成功所以没轮到


def test_distiller_drop_skips_unreliable_when_alt_exists(tmp_path):
    d = _sink_bing(str(tmp_path / "d.jsonl"))
    hub = _make_hub(d, drop=True)
    good = _FakeAdapter("good", ok=True)
    bad = _FakeAdapter("bing", ok=False, error="boom")
    hub._providers = [bad, good]
    hub.route("web.search", {"query": "x"})
    assert good.invoked is True
    assert bad.invoked is False  # 有备选才硬跳过沉底引擎


def test_distiller_keeps_unreliable_as_fallback_when_only_one(tmp_path):
    d = _sink_bing(str(tmp_path / "d.jsonl"))
    hub = _make_hub(d, drop=True)
    only = _FakeAdapter("bing", ok=False, error="boom")
    hub._providers = [only]
    res = hub.route("web.search", {"query": "x"})
    assert res.ok is False
    assert only.invoked is True  # 无备选，沉底引擎仍作兜底尝试（诚实不丢能力）


def test_distiller_opt_in_disabled_by_default(tmp_path):
    # 默认未开 AOS_DISTILLER_ROUTE，构造未传 distiller → 关闭，route 不受影响。
    hub = FabricHub(adapters=())
    assert hub._distiller is None
