"""路由预测器端到端测试：落盘 → 学习 → learned 排序 → 诚实回落。

不依赖真实引擎/网络：用 FakeAdapter 构造可控的路由场景。
核心断言：learned 策略确实比静态偏好更准地选出了「历史上更可能成功」的引擎，
且默认无 predictor 时行为与静态策略完全一致（绝不破坏现有路由）。
"""
from __future__ import annotations

import os
import tempfile

from core.fabric.adapter import BaseAgentAdapter, Capability, InvokeRequest, InvokeResult
from core.fabric.registry import FabricRegistry
from core.fabric.route_outcome_store import RouteOutcomeStore
from core.fabric.route_predictor import RoutePredictor


class FakeAdapter(BaseAgentAdapter):
    def __init__(self, engine_id, caps, tier="medium", health=True, ok=True):
        self._eid = engine_id
        self._caps = caps
        self._tier = tier
        self._health = health
        self._ok = ok
        self.last_req = None

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return self._caps

    def health(self):
        return self._health

    def tier(self):
        return self._tier

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        self.last_req = req
        return InvokeResult(ok=self._ok, data={"engine": self._eid})


def _make_predictor():
    """构造一个已知规律的训练集：engA 对某 cap 总成功，engB 总失败。"""
    recs = []
    for _ in range(10):
        recs.append({"capability": "inference.llm", "engine": "engA", "tier": "auto", "ok": True, "latency_ms": 10.0})
        recs.append({"capability": "inference.llm", "engine": "engB", "tier": "auto", "ok": False, "latency_ms": 50.0})
    # 加入一点噪声无关维度，确保不过拟合到单一特征
    for _ in range(3):
        recs.append({"capability": "memory.semantic", "engine": "engA", "tier": "auto", "ok": True, "latency_ms": 12.0})
    p = RoutePredictor(hidden=8, epochs=400, seed=1)
    p.fit(recs)
    assert p.trained
    return p


def test_store_records_and_loads():
    with tempfile.TemporaryDirectory() as d:
        store = RouteOutcomeStore(path=os.path.join(d, "out.jsonl"))
        assert store.count() == 0
        store.record("inference.llm", "engA", "auto", True, 10.0)
        store.record("inference.llm", "engB", "auto", False, 50.0, error="boom")
        assert store.count() == 2
        loaded = store.load()
        assert loaded[0]["engine"] == "engA" and loaded[0]["ok"] is True
        assert loaded[1]["engine"] == "engB" and loaded[1]["error"] == "boom"
        assert store.trainable() is False  # 2 < 8 默认阈值


def test_predictor_learns_distinction():
    p = _make_predictor()
    # 学完后，engA 对该 cap 的预测成功概率应明显高于 engB
    pa = p.predict("inference.llm", "engA", "auto")
    pb = p.predict("inference.llm", "engB", "auto")
    assert pa > 0.8, f"engA 应高概率成功, got {pa}"
    assert pb < 0.2, f"engB 应低概率成功, got {pb}"
    # 未见过的新引擎 → 中性 0.5（诚实，不瞎编）
    assert p.predict("inference.llm", "engUnknown", "auto") == 0.5


def test_predictor_untrained_returns_neutral():
    p = RoutePredictor()
    assert p.trained is False
    assert p.predict("x", "y", "auto") == 0.5


def test_learned_strategy_ranks_winner_first():
    p = _make_predictor()
    reg = FabricRegistry(strategy="learned", predictor=p)
    reg.register(FakeAdapter("engB", [Capability("inference.llm")], ok=False))
    reg.register(FakeAdapter("engA", [Capability("inference.llm")], ok=True))
    # 静态偏好下 engA/engB 同档，preference 排序会按 _pref 而非历史成败；
    # learned 下应把历史高成功率的 engA 排到最前。
    ordered = reg.providers_for(Capability("inference.llm"))
    assert [a.engine_id for a in ordered] == ["engA", "engB"], ordered


def test_learned_without_predictor_falls_back():
    """learned 策略但没注入 predictor → 用静态 preference，不报错、行为合理。"""
    reg = FabricRegistry(strategy="learned")  # predictor=None
    reg.register(FakeAdapter("lowpref", [Capability("inference.llm")]))   # _pref=50
    reg.register(FakeAdapter("hipref", [Capability("inference.llm")]))    # _pref=50 同分
    # 无 predictor 时退回 _sort_key（preference），不应抛异常
    ordered = reg.providers_for(Capability("inference.llm"))
    assert len(ordered) == 2


def test_route_records_outcome_and_routes_by_learned():
    """route() 真实记录每次尝试；learned 先选历史高成功引擎。"""
    with tempfile.TemporaryDirectory() as d:
        store = RouteOutcomeStore(path=os.path.join(d, "out.jsonl"))
        p = _make_predictor()
        reg = FabricRegistry(strategy="learned", predictor=p, outcome_store=store)
        a = FakeAdapter("engA", [Capability("inference.llm")], ok=True)
        b = FakeAdapter("engB", [Capability("inference.llm")], ok=False)
        reg.register(b)
        reg.register(a)
        # 第一次真实路由：learned 应先试 engA（历史成功），直接命中返回
        res = reg.route(InvokeRequest(capability=Capability("inference.llm"), payload={}))
        assert res.ok is True and res.data["engine"] == "engA"
        # outcome 已落盘（至少记录了 engA 这次成功尝试）
        assert store.count() >= 1
        recs = store.load()
        assert any(r["engine"] == "engA" and r["ok"] for r in recs)


def test_default_registry_unchanged_without_predictor():
    """默认构造（无 predictor）行为完全不变：不落盘、不训练。"""
    reg = FabricRegistry()  # 默认 preference 策略，无 predictor/store
    assert reg.strategy == "preference"
    assert reg.predictor is None
    assert reg.outcome_store is None
    reg.register(FakeAdapter("x", [Capability("inference.llm")], ok=True))
    res = reg.route(InvokeRequest(capability=Capability("inference.llm"), payload={}))
    assert res.ok is True
