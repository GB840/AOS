"""因果世界模型推理层测试：干预认知 / 反事实认知 / 可验证下限。"""
import sys
sys.path.insert(0, "D:/AOS/src")

from kernel.causal import CausalModel, Intervention
from kernel.evolution_distiller import EvolutionDistiller


def _fill(model, context, action, n_ok, n_fail):
    for _ in range(n_ok):
        model.ingest(Intervention(context=context, action=action, outcome=True))
    for _ in range(n_fail):
        model.ingest(Intervention(context=context, action=action, outcome=False))


def test_effect_of_unknown_when_low_samples():
    m = CausalModel()
    _fill(m, "web.search", "bing", 2, 0)  # 仅 2 样本 < MIN_SAMPLES
    e = m.effect_of("web.search", "bing")
    assert e["success_rate"] is None
    assert e["verdict"] == "unknown"
    assert "样本不足" in e["reason"]


def test_effect_of_reliable_and_unreliable():
    m = CausalModel()
    _fill(m, "web.search", "anysearch", 8, 1)   # 0.89 → reliable
    _fill(m, "web.search", "bing", 1, 9)        # 0.10 → unreliable
    good = m.effect_of("web.search", "anysearch")
    bad = m.effect_of("web.search", "bing")
    assert good["verdict"] == "reliable" and abs(good["success_rate"] - 8 / 9) < 1e-9
    assert bad["verdict"] == "unreliable" and abs(bad["success_rate"] - 0.1) < 1e-9


def test_counterfactual_picks_better():
    m = CausalModel()
    _fill(m, "web.search", "actual", 2, 8)   # 0.20
    _fill(m, "web.search", "alt", 9, 1)      # 0.90
    cf = m.counterfactual("web.search", "actual", "alt")
    assert cf["verdict"] == "alt_better"
    assert cf["delta"] is not None and cf["delta"] > 0


def test_counterfactual_unknown_when_low_samples():
    m = CausalModel()
    _fill(m, "web.search", "actual", 1, 0)
    _fill(m, "web.search", "alt", 9, 1)
    cf = m.counterfactual("web.search", "actual", "alt")
    assert cf["verdict"] == "unknown"
    assert cf["delta"] is None


def test_best_action_returns_most_reliable():
    m = CausalModel()
    _fill(m, "c", "a", 2, 8)
    _fill(m, "c", "b", 9, 1)
    best = m.best_action("c", ["a", "b"])
    assert best is not None and best["action"] == "b"


def test_from_distiller_lifts_whitebox_stats():
    d = EvolutionDistiller(store_path=None)
    # 逐条 ingest 真正的 trace（不能用推导式塌缩成单条），共 8 成功 + 2 失败。
    for _ in range(8):
        d.ingest({"steps": [{"capability": "web.search", "engine": "bing",
                             "ok": True, "error": ""}]})
    for _ in range(2):
        d.ingest({"steps": [{"capability": "web.search", "engine": "bing",
                             "ok": False, "error": "x"}]})
    m = CausalModel().from_distiller(d)
    e = m.effect_of("web.search", "bing")
    assert e["samples"] == 10 and abs(e["success_rate"] - 0.8) < 1e-9
