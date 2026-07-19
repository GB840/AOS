"""autopilot 因果反思闭环「真跑」端到端验证（D5 决策论层接入反思链路）。

这不再是函数级单测，而是真实驱动 `_reflect_and_redesign`：
  预填白盒蒸馏器 → 某步(web.search)失败 → 反思三后端降级到 heuristic →
  `_compute_causal_hints` 用蒸馏器产出换做法建议 → `_attach_engine_hints` 把
  engine_hint 打到重设计步骤 → `_finalize_reflect` 把 causal_hints 记录进结果。

验证点（对应 AGENTS.md §1.10「改变之后会怎样」）：
  1. 失败步经因果决策论层被建议改用更值引擎（duckduckgo：成功率最高且免费）；
  2. 建议以 engine_hint 形式真实落到重设计步骤，路由时会被 SearchAdapter 优先采用；
  3. 反思结果明文记录 causal_hints，上层/日志可复核「为什么换、换了哪个」；
  4. 无 LLM（ag2/ollama 均不可用）时仍能闭环，绝不空转、绝不伪造建议。
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


def test_e2e_reflection_loop_attaches_engine_hint_and_records_causal():
    """真跑反思链路：蒸馏器有数据 + web.search 失败 → 步骤带 engine_hint + 记录 causal_hints。"""
    import kernel.autopilot as ap_mod

    d = _fake_distiller()

    # 让三后端降级到 heuristic（无 LLM 环境）：ag2 返 None、ollama 抛异常。
    def _none_ag2():
        return None

    def _boom_ollama(*a, **k):
        raise RuntimeError("no ollama in test")

    # 上一轮执行：web.search 失败（真实闸门判空转）。
    r = {"execution": {"trace": [
        {"capability": "web.search", "ok": False,
         "real_metrics": {"is_real": False}, "summary": "所有搜索源均无结果"},
    ]}}

    # 替换模块级依赖：注入预填蒸馏器、掐掉 LLM 后端、屏蔽 lesson 落盘。
    orig = (
        ap_mod._get_causal_distiller, ap_mod._get_ag2,
        ap_mod._ollama_generate, ap_mod._save_lesson,
    )
    ap_mod._get_causal_distiller = lambda: d
    ap_mod._get_ag2 = _none_ag2
    ap_mod._ollama_generate = _boom_ollama
    ap_mod._save_lesson = lambda *a, **k: None
    try:
        res = ap_mod._reflect_and_redesign("测试任务：搜点东西回来", r, 1)
    finally:
        (ap_mod._get_causal_distiller, ap_mod._get_ag2,
         ap_mod._ollama_generate, ap_mod._save_lesson) = orig

    # 1) 反思应产出修正计划（heuristic 兜底，不空转）。
    assert res is not None, "反思应产出修正计划（heuristic 兜底）"
    steps = res["steps"]
    assert any(s.get("capability") == "web.search" for s in steps), steps

    # 2) 失败步被因果建议打上 engine_hint=duckduckgo（最值引擎）。
    ws = [s for s in steps if s.get("capability") == "web.search"][0]
    assert ws.get("engine_hint") == "duckduckgo", ws

    # 3) 反思结果明文记录 causal_hints，上层/日志可复核「为什么换、换了哪个」。
    assert res.get("causal_hints", {}).get("web.search") == "duckduckgo", res


def test_e2e_reflection_no_distiller_still_returns_plan_no_fabrication():
    """无蒸馏器（样本不足）时：反思仍走通但不编造换做法建议——steps 不带 engine_hint。"""
    import kernel.autopilot as ap_mod

    def _none_ag2():
        return None

    def _boom_ollama(*a, **k):
        raise RuntimeError("no ollama in test")

    r = {"execution": {"trace": [
        {"capability": "web.search", "ok": False,
         "real_metrics": {"is_real": False}, "summary": "失败"},
    ]}}

    orig = (
        ap_mod._get_causal_distiller, ap_mod._get_ag2,
        ap_mod._ollama_generate, ap_mod._save_lesson,
    )
    ap_mod._get_causal_distiller = lambda: None  # 空蒸馏器 → 因果建议恒空
    ap_mod._get_ag2 = _none_ag2
    ap_mod._ollama_generate = _boom_ollama
    ap_mod._save_lesson = lambda *a, **k: None
    try:
        res = ap_mod._reflect_and_redesign("测试任务", r, 1)
    finally:
        (ap_mod._get_causal_distiller, ap_mod._get_ag2,
         ap_mod._ollama_generate, ap_mod._save_lesson) = orig

    assert res is not None
    # 诚实兜底：无数据 → 不伪造 engine_hint。
    for s in res["steps"]:
        assert "engine_hint" not in s, s
    assert res.get("causal_hints", {}) == {}
