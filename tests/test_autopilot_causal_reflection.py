"""autopilot 因果反思闭环（D5 决策论层接入反思链路）测试。

验证：反思时经 CausalModel 从白盒蒸馏器选「换做法」引擎、证据可复核、
样本不足诚实不瞎建议；engine_hint 透传到 SearchAdapter 真正优先采用。
"""
import sys
sys.path.insert(0, "D:/AOS/src")

from core.fabric.adapter import InvokeResult, InvokeRequest
from kernel.evolution_distiller import EvolutionDistiller


def _fake_distiller() -> EvolutionDistiller:
    """构造一个 web.search 多引擎、样本充足的蒸馏器（bing 差 / duckduckgo 好 / zhipu 贵且差）。"""
    d = EvolutionDistiller(store_path=None)
    for _ in range(2):
        d.record_outcome("web.search", "bing", True)
    for _ in range(8):
        d.record_outcome("web.search", "bing", False)
    for _ in range(9):
        d.record_outcome("web.search", "duckduckgo", True)
    for _ in range(1):
        d.record_outcome("web.search", "duckduckgo", False)
    for _ in range(1):
        d.record_outcome("web.search", "zhipu", True)
    for _ in range(5):
        d.record_outcome("web.search", "zhipu", False)
    return d


def test_causal_reflection_picks_better_engine():
    import kernel.autopilot as ap
    d = _fake_distiller()
    h = ap._causal_reflection_hint("web.search", d)
    assert h is not None
    # duckduckgo 成功率 0.9 且免费 → 带权效用最高（zhipu 虽可能高成功但成本 0.4 被罚）
    assert h["suggested_engine"] == "duckduckgo", h
    assert 0.8 < h["best_success_rate"] <= 1.0
    assert h["inference_type"] == "observational_association"  # 诚实标注非已证因果
    ev = h["evidence"]
    assert ev["delta"] is not None and ev["utility_delta"] is not None
    assert ev["inference_type"] == "observational_association"  # 诚实标注非已证因果


def test_causal_reflection_insufficient_data_returns_none():
    import kernel.autopilot as ap
    # 空蒸馏器
    assert ap._causal_reflection_hint("web.search", EvolutionDistiller(store_path=None)) is None
    # 仅单一候选引擎（<2）→ 证据不足
    d = EvolutionDistiller(store_path=None)
    for _ in range(6):
        d.record_outcome("web.search", "bing", True)
    assert ap._causal_reflection_hint("web.search", d) is None
    # 另一能力无数据
    assert ap._causal_reflection_hint("memory.semantic", d) is None


def test_compute_causal_hints_injects_block_and_hints():
    import kernel.autopilot as ap
    failed = [
        "步骤1[web.search] 失败/空转：所有搜索源均失败",
        "步骤2[inference.llm] 失败/空转：空",
    ]
    block, hints = ap._compute_causal_hints(failed, _fake_distiller())
    # web.search 有数据 → 给建议；inference.llm 无数据 → 不编造
    assert "web.search" in hints
    assert "inference.llm" not in hints
    assert "duckduckgo" in block
    assert "观测相关" in block  # 诚实标注
    assert "数据支撑的换做法" in block


def test_compute_causal_hints_no_distiller_empty():
    import kernel.autopilot as ap
    block, hints = ap._compute_causal_hints(["步骤1[web.search] 失败"], None)
    assert block == "" and hints == {}


def test_feed_distiller_records_engine_when_enabled():
    import kernel.autopilot as ap
    calls = []

    class _FakeDist:
        def record_outcome(self, cap, eng, ok, error=""):
            calls.append((cap, eng, ok))

    ap._DISTILLER = _FakeDist()
    ap._DISTILLER_INITED = True
    try:
        ok_res = InvokeResult(ok=True, data={"engine": "bing", "real_metrics": {"is_real": True}})
        ap._feed_distiller("web.search", ok_res)
        # 引擎缺失 → 不记录
        no_eng = InvokeResult(ok=True, data={"real_metrics": {"is_real": True}})
        ap._feed_distiller("web.search", no_eng)
        # 真实闸门判失败 → 记 ok=False
        bad = InvokeResult(ok=True, data={"engine": "bing", "real_metrics": {"is_real": False}})
        ap._feed_distiller("web.search", bad)
        assert calls == [("web.search", "bing", True), ("web.search", "bing", False)]
    finally:
        ap._DISTILLER = None
        ap._DISTILLER_INITED = False


def test_search_adapter_honors_engine_hint():
    import core.fabric.adapters.search_adapter as sa
    s = sa.SearchAdapter()
    order = []
    for n in ["anysearch", "baidu", "bing", "duckduckgo", "jina", "zhipu"]:
        def _mk(name):
            def _f(q, m):
                order.append(name)
                raise RuntimeError("forced-fail-for-test")
            return _f
        setattr(s, "_search_" + n, _mk(n))
    res = s.invoke(InvokeRequest(
        capability="web.search",
        payload={"query": "test query", "engine": "jina"}))
    # jina 被提到最前优先尝试（engine_hint 真实生效）；所有源被强制失败后整体失败
    assert order[0] == "jina"
    assert res.ok is False


def test_search_adapter_ignores_unknown_engine_hint():
    import core.fabric.adapters.search_adapter as sa
    s = sa.SearchAdapter()
    order = []
    for n in ["anysearch", "baidu", "bing", "duckduckgo", "jina", "zhipu"]:
        def _mk(name):
            def _f(q, m):
                order.append(name)
                raise RuntimeError("forced-fail-for-test")
            return _f
        setattr(s, "_search_" + n, _mk(n))
    s.invoke(InvokeRequest(
        capability="web.search",
        payload={"query": "x", "engine": "not_a_real_source"}))
    # 未知源名被过滤 → 源顺序不变（anysearch 仍最前），不伪造、不报错
    assert order[0] == "anysearch"
