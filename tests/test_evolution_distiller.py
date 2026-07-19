"""白盒进化蒸馏引擎测试（任务272 / 白皮书 3.3）。

验证：从 Trace 蒸馏不可靠引擎 → 沉底建议；样本不足不误杀；经验持久化可重载。
"""
from kernel.evolution_distiller import EvolutionDistiller, MIN_SAMPLES, SINK_FAIL_RATE


def _trace(cap, eng, ok, err=""):
    return {"steps": [{"capability": cap, "engine": eng, "ok": ok, "error": err}]}


def test_distill_sinks_unreliable_engine(tmp_path):
    d = EvolutionDistiller(str(tmp_path / "distill.jsonl"))
    # 10 个 trace：bing 前 3 次成功、后 7 次失败（失败率 0.7），mistralrs 全成功
    for i in range(10):
        d.ingest(_trace("web.search", "bing", i < 3, "timeout" if i >= 3 else ""))
        d.ingest(_trace("inference.llm", "mistralrs", True))
    recs = d.distill()
    sunk = [r for r in recs if r["engine"] == "bing"]
    assert sunk, "高失败率引擎应被沉底"
    assert sunk[0]["fail_rate"] >= SINK_FAIL_RATE
    # 稳定引擎不应沉底
    assert not any(r["engine"] == "mistralrs" for r in recs)


def test_distill_requires_min_samples(tmp_path):
    d = EvolutionDistiller(str(tmp_path / "d.jsonl"))
    for _ in range(3):  # < MIN_SAMPLES
        d.ingest(_trace("x", "flaky", False, "boom"))
    assert d.distill() == [], "样本不足不沉底（避免噪声误杀）"


def test_persistence_reload(tmp_path):
    p = str(tmp_path / "d.jsonl")
    d1 = EvolutionDistiller(p)
    d1.ingest(_trace("web.search", "bing", False, "e"))
    d2 = EvolutionDistiller(p)  # 重载
    assert "web.search::bing" in d2.stats
    assert d2.stats["web.search::bing"].total == 1
