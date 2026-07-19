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


def test_effect_of_wilson_ci_within_bounds():
    # D4：输出 Wilson 95% 置信区间，且落在 [0,1] 并与点估计自洽。
    m = CausalModel()
    _fill(m, "web.search", "bing", 8, 1)
    e = m.effect_of("web.search", "bing")
    assert 0.0 <= e["ci_low"] <= e["success_rate"] <= e["ci_high"] <= 1.0
    assert e["ci_high"] - e["ci_low"] > 0  # 非零区间，不确定度被显式交出去


def test_effect_of_labels_observational_and_confidence():
    # D4：明确标注「观测相关、非已证因果」，并带置信级别。
    m = CausalModel()
    _fill(m, "web.search", "bing", 9, 1)
    e = m.effect_of("web.search", "bing")
    assert e["inference_type"] == "observational_association"
    assert e["confidence"] in ("low", "medium", "high")


def test_best_action_weighted_prefers_cheaper():
    # D5：带权决策下，「成功率稍低但更便宜」的动作胜出（默认退化为比成功率）。
    m = CausalModel()
    _fill(m, "c", "expensive", 9, 1)  # 0.9 成功率，成本 5
    _fill(m, "c", "cheap", 7, 3)      # 0.7 成功率，成本 0
    best = m.best_action("c", ["expensive", "cheap"],
                         weights={"rate": 1.0, "cost": 1.0, "latency": 0.0},
                         costs={"expensive": 5.0, "cheap": 0.0})
    assert best is not None and best["action"] == "cheap"
    assert best["utility"] < 0.9  # 计入成本惩罚后效用低于裸成功率


def test_counterfactual_utility_flips_with_costs():
    # D5：成功率更高 ≠ 更值；注入成本后反事实效用可能反转（autopilot 降本依据）。
    m = CausalModel()
    _fill(m, "c", "actual", 2, 8)  # 0.2
    _fill(m, "c", "alt", 9, 1)     # 0.9
    cf = m.counterfactual("c", "actual", "alt", costs={"alt": 0.8, "actual": 0.0})
    assert cf["delta"] > 0                 # 成功率：alt 更高
    assert cf["utility_delta"] < 0         # 算上成本：actual 更值
    assert cf["verdict"] == "actual_better"
