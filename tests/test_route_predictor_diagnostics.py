"""路由预测器可观测端点测试：predictor_diagnostics() 只读快照 + 路由注册。

不依赖真实引擎/网络：用 FakeAdapter 构造可控场景。核心断言：
- 默认（无 predictor）→ 诚实返回「未启用」中性状态，绝不伪造；
- 训练后 → 暴露词汇表规模 + 对各能力×引擎的预测成功概率，且学到了规律；
- 未训练 → sample_predictions 为空（不假装给出概率）；
- /api/route/predictor 确实注册到 app.routes（抓 import 接错/路由缺失）。
"""
from __future__ import annotations

import os
import tempfile

from core.fabric.adapter import BaseAgentAdapter, Capability, InvokeRequest, InvokeResult
from core.fabric.registry import FabricRegistry
from core.fabric.route_outcome_store import RouteOutcomeStore
from core.fabric.route_predictor import RoutePredictor


class FakeAdapter(BaseAgentAdapter):
    def __init__(self, engine_id, caps, tier="medium", ok=True):
        self._eid = engine_id
        self._caps = caps
        self._tier = tier
        self._ok = ok

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return self._caps

    def health(self):
        return True

    def tier(self):
        return self._tier

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=self._ok, data={"engine": self._eid})


def _trained_registry():
    """造一个已知规律（engA 总成功 / engB 总失败）且已训练的注册表。"""
    tmp = tempfile.mkdtemp(prefix="aos-diag-")
    store = RouteOutcomeStore(path=os.path.join(tmp, "route_outcomes.jsonl"))
    recs = []
    for _ in range(10):
        recs.append({"capability": "inference.llm", "engine": "engA", "tier": "auto", "ok": True, "latency_ms": 10.0})
        recs.append({"capability": "inference.llm", "engine": "engB", "tier": "auto", "ok": False, "latency_ms": 50.0})
    for r in recs:
        store.record(r["capability"], r["engine"], r["tier"], r["ok"], r["latency_ms"])
    p = RoutePredictor(hidden=8, epochs=400, seed=1)
    p.fit(store.load())
    assert p.trained
    reg = FabricRegistry(predictor=p, outcome_store=store, strategy="learned", tier="auto")
    reg.register(FakeAdapter("engA", [Capability("inference.llm")], tier="auto"))
    reg.register(FakeAdapter("engB", [Capability("inference.llm")], tier="auto"))
    return reg


def test_diagnostics_default_no_predictor():
    """默认构造（preference 策略、无 predictor）→ 诚实「未启用」状态。"""
    reg = FabricRegistry()
    d = reg.predictor_diagnostics()
    assert d["has_predictor"] is False
    assert d["trained"] is False
    assert d["outcome_store_connected"] is False
    assert d["sample_count"] == 0
    assert d["vocab_capabilities"] == 0
    assert d["vocab_engines"] == 0
    assert d["vocab_tiers"] == 0
    assert d["sample_predictions"] == []


def test_diagnostics_trained_exposes_predictions():
    """训练后 → 暴露词汇表 + 能力×引擎预测，且学到 engA>engB 的规律。"""
    reg = _trained_registry()
    d = reg.predictor_diagnostics()
    assert d["has_predictor"] is True
    assert d["trained"] is True
    assert d["vocab_capabilities"] >= 1
    assert d["vocab_engines"] >= 2
    assert d["vocab_tiers"] >= 1
    preds = d["sample_predictions"]
    assert len(preds) >= 2
    by_eng = {p["engine"]: p["p_success"] for p in preds}
    assert 0.0 <= by_eng["engA"] <= 1.0
    assert 0.0 <= by_eng["engB"] <= 1.0
    # 学到了规律：engA 的预测成功概率应高于 engB
    assert by_eng["engA"] > by_eng["engB"]


def test_diagnostics_untrained_no_predictions():
    """predictor 注入但未训练 → sample_predictions 为空（不假装给出概率）。"""
    tmp = tempfile.mkdtemp(prefix="aos-diag-untrained-")
    store = RouteOutcomeStore(path=os.path.join(tmp, "route_outcomes.jsonl"))
    reg = FabricRegistry(predictor=RoutePredictor(), outcome_store=store,
                         strategy="learned", tier="auto")
    d = reg.predictor_diagnostics()
    assert d["has_predictor"] is True
    assert d["trained"] is False
    assert d["sample_predictions"] == []


def test_endpoint_registered():
    """/api/route/predictor 确实注册到 app.routes（GET）。"""
    import api.main as m
    found = any(
        getattr(r, "path", None) == "/api/route/predictor"
        and "GET" in getattr(r, "methods", set())
        for r in m.app.routes
    )
    assert found, "/api/route/predictor (GET) 未注册"
