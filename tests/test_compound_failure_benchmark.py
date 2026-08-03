"""抗复合失败内核范式基准（#271 收口验证）。

验证 AOS 自进化内核面对复合失败时的韧性：
1. 多步同时失败 → 因果反思能为每类失败给出独立的换做法建议
2. 假成功拦截 → 真失败不会被假成功掩盖
3. 混合场景 → 部分真失败 + 部分假成功不会被混淆
4. 因果建议透传 → engine_hint 正确写入重设计计划
5. 样本不足降级 → 证据不足时不编造建议

复合失败的本质：单步失败触发的反思'换一个 Engine 重试'不叫复合失败；
只有当 3+ 个不同能力同时失败时还能——
  - 逐一识别失败根因
  - 为每个失败能力给出基于白盒数据的换做法建议
  - 不把假成功混入重设计
——才算抗复合失败。

诚实分级：②（代码+单测实证），不谎报 ③ 端到端。
"""

import sys
sys.path.insert(0, "D:/AOS/src")

from kernel import autopilot as ap
from kernel.evolution_distiller import EvolutionDistiller


# ── 辅助工厂函数 ──────────────────────────────────────────

def _make_distiller_with_mixed_data() -> EvolutionDistiller:
    """构造多能力、混合成败的白盒蒸馏器（模拟真实运行后积累的经验）。

    - web.search: bing 差 (2/10), duckduckgo 好 (9/10), zhipu 中等 (7/10)
    - inference.llm: deepseek 好 (8/10), zhipu 中等 (6/10)
    - action.code_exec: local_exec 唯一 (10/10) → 只有1候选，反思给不出换做法建议
    - memory.recall: mem0 差 (3/10), chroma 好 (9/10)
    """
    d = EvolutionDistiller(store_path=None)
    # web.search
    for _ in range(2):
        d.record_outcome("web.search", "bing", True)
    for _ in range(8):
        d.record_outcome("web.search", "bing", False)
    for _ in range(9):
        d.record_outcome("web.search", "duckduckgo", True)
    for _ in range(1):
        d.record_outcome("web.search", "duckduckgo", False)
    for _ in range(7):
        d.record_outcome("web.search", "zhipu", True)
    for _ in range(3):
        d.record_outcome("web.search", "zhipu", False)
    # inference.llm
    for _ in range(8):
        d.record_outcome("inference.llm", "deepseek", True)
    for _ in range(2):
        d.record_outcome("inference.llm", "deepseek", False)
    for _ in range(6):
        d.record_outcome("inference.llm", "zhipu", True)
    for _ in range(4):
        d.record_outcome("inference.llm", "zhipu", False)
    # action.code_exec — 唯一候选（无法给出换做法建议）
    for _ in range(10):
        d.record_outcome("action.code_exec", "local_exec", True)
    # memory.recall
    for _ in range(3):
        d.record_outcome("memory.recall", "mem0", True)
    for _ in range(7):
        d.record_outcome("memory.recall", "mem0", False)
    for _ in range(9):
        d.record_outcome("memory.recall", "chroma", True)
    for _ in range(1):
        d.record_outcome("memory.recall", "chroma", False)
    return d


# ── 基准 1：多步同时失败 → 各自获得独立因果反思 ──────────

def test_triple_failure_each_gets_independent_hint():
    """3 种能力同时失败 → 每种都能获得独立因果换做法建议。

    场景：搜索、推理、记忆同时失败（不是同一 Engine 的重复失败，
    而是复合场景下不同能力各自失败）。验证因果反思能逐一识别。
    """
    failed = [
        "步骤1[web.search] 失败/空转：bing 超时、duckduckgo 空结果、jina 被限流",
        "步骤3[inference.llm] 失败/空转：zhipu 返回空",
        "步骤5[memory.recall] 失败/空转：mem0 连接超时",
    ]
    block, hints = ap._compute_causal_hints(failed, _make_distiller_with_mixed_data())

    # 三能力都应有换做法建议
    assert "web.search" in hints
    assert "inference.llm" in hints
    assert "memory.recall" in hints
    assert len(hints) == 3

    # 建议合理：蒸馏器里 bing 差 → 建议 duckduckgo（成功率 0.9）
    assert hints["web.search"]["suggested_engine"] == "duckduckgo"
    # 蒸馏器里 mem0 差 → 建议 chroma（成功率 0.9）
    assert hints["memory.recall"]["suggested_engine"] == "chroma"
    # 蒸馏器里 deepseek > zhipu → 建议 deepseek
    assert hints["inference.llm"]["suggested_engine"] == "deepseek"

    # 文本块包含三能力的反思文本
    assert "web.search" in block
    assert "inference.llm" in block
    assert "memory.recall" in block
    # 包含诚实标注
    assert "观测相关" in block


def test_single_candidate_skill_no_hint():
    """只有单一候选的能力 → 不给换做法建议（不编造）。"""
    d = EvolutionDistiller(store_path=None)
    for _ in range(10):
        d.record_outcome("action.code_exec", "local_exec", True)

    failed = ["步骤1[action.code_exec] 失败：语法错误"]
    block, hints = ap._compute_causal_hints(failed, d)

    assert "action.code_exec" not in hints
    assert block == ""  # 无有效建议时不产生文本


# ── 基准 2：假成功不掩盖真失败 ────────────────────────────

def test_mixed_real_fake_distinguishes():
    """混合场景：部分步真失败、部分步假成功 → 两者不可混淆。

    '假成功'（ok=True 但 is_real=False）是复合失败的根源——
    朴素串联会把假成功算进'已完成'，后续雪崩。AOS 闸门必须拦截。
    """
    data = {"failed_steps": 1}
    trace = [
        # 步骤1：真失败
        {"capability": "web.search", "ok": False,
         "real_metrics": {"is_real": False, "count": 0}},
        # 步骤2：假成功（ok=True 但无真实产出 → 空转）
        {"capability": "inference.llm", "ok": True,
         "real_metrics": {"is_real": False}},
    ]
    verdict = ap._verdict("生成竞争对手分析报告", data, trace, {})
    # 真失败 + 假成功 → 整体判未完成，不能谎报"完成 ✅"
    assert "未完成" in verdict["status"]
    assert verdict["status"] != "完成 ✅"


def test_five_failures_all_distinct_capabilities():
    """压力：5 种不同能力同时失败 → 不崩溃、各有建议（如果可以）。"""
    d = _make_distiller_with_mixed_data()
    # 加一些额外能力数据
    for _ in range(8):
        d.record_outcome("data.query", "sqlite", True)
    for _ in range(2):
        d.record_outcome("data.query", "sqlite", False)
    for _ in range(3):
        d.record_outcome("data.query", "duckdb", True)
    for _ in range(7):
        d.record_outcome("data.query", "duckdb", False)

    failed = [
        "步骤1[web.search] 失败/空转",
        "步骤2[inference.llm] 失败/空转",
        "步骤3[memory.recall] 失败/空转",
        "步骤4[data.query] 失败/空转",
        "步骤5[action.code_exec] 失败/空转",
    ]
    block, hints = ap._compute_causal_hints(failed, d)

    # 5 个里 4 个有数据（code_exec 只有 local_exec → 单候选→不给建议）
    assert len(hints) >= 3  # 至少 web.search / memory.recall / data.query
    assert len(hints) <= 4  # 不包括 action.code_exec（单候选）

    # 有建议的每个都诚实标注"观测相关"
    for h in hints.values():
        assert h["inference_type"] == "observational_association"


# ── 基准 3：因果建议透传到重设计 ──────────────────────────

def test_engine_hints_attached_to_redesign_steps():
    """因果建议的 engine_hint 正确写入重设计步骤（路由优先采用）。"""
    hints = {
        "web.search": {
            "suggested_engine": "duckduckgo",
            "best_success_rate": 0.9,
            "best_ci": (0.75, 0.98),
            "best_confidence": "high",
            "inference_type": "observational_association",
        },
        "memory.recall": {
            "suggested_engine": "chroma",
            "best_success_rate": 0.9,
            "best_ci": (0.75, 0.98),
            "best_confidence": "high",
            "inference_type": "observational_association",
        },
    }
    steps = [
        {"capability": "web.search", "payload": {"query": "X"}},
        {"capability": "inference.llm", "payload": {"prompt": "Y"}},
        {"capability": "memory.recall", "payload": {"query": "Z"}},
    ]
    ap._attach_engine_hints(steps, hints)

    assert steps[0]["engine_hint"] == "duckduckgo"
    assert steps[2]["engine_hint"] == "chroma"
    # inference.llm 不在 hints 里 → 不加 engine_hint
    assert "engine_hint" not in steps[1]


def test_engine_hints_do_not_overwrite_existing():
    """已有 engine_hint 的步骤不被覆盖。"""
    steps = [
        {"capability": "web.search", "engine_hint": "bing",
         "payload": {"query": "X"}},
    ]
    hints = {"web.search": {"suggested_engine": "duckduckgo"}}
    ap._attach_engine_hints(steps, hints)
    # 已有明确引擎偏好 → 不透传因果建议（尊重用户/上轮选择）
    assert steps[0]["engine_hint"] == "bing"


# ── 基准 4：零蒸馏器降级 ────────────────────────────────

def test_no_distiller_graceful_degradation():
    """无蒸馏器时因果反思退化为空（不抛异常、不编造）。"""
    failed = [
        "步骤1[web.search] 失败/空转",
        "步骤2[memory.recall] 失败/空转",
    ]
    block, hints = ap._compute_causal_hints(failed, None)
    assert block == ""
    assert hints == {}

    # 验证空蒸馏器也返回空（非 None → None 兼容）
    empty = EvolutionDistiller(store_path=None)
    block2, hints2 = ap._compute_causal_hints(failed, empty)
    assert block2 == ""
    assert hints2 == {}


# ── 基准 5：蒸馏器沉底建议 ←→ 反射建议一致性 ─────────────

def test_distill_sink_aligns_with_reflection_hints():
    """蒸馏器判"沉底"的引擎 = 因果反思永远不会建议使用的引擎。

    反例：蒸馏器说 zhipu 失败率高应沉底，因果反思却还建议用 zhipu →
    那就是蒸馏→反思链断裂。
    """
    d = EvolutionDistiller(store_path=None)
    # bing 非常差（2/10）→ 应被蒸馏器沉底
    for _ in range(2):
        d.record_outcome("web.search", "bing", True)
    for _ in range(8):
        d.record_outcome("web.search", "bing", False)
    # duckduckgo 好
    for _ in range(9):
        d.record_outcome("web.search", "duckduckgo", True)
    for _ in range(1):
        d.record_outcome("web.search", "duckduckgo", False)

    # 蒸馏器沉底建议
    sinks = d.distill()
    sunk_engines = {s["engine"] for s in sinks}
    assert "bing" in sunk_engines  # bing 失败率 0.8 > 0.5 + 样本充足

    # 因果反思建议
    hint = ap._causal_reflection_hint("web.search", d)
    assert hint is not None
    # 因果反思绝对不会建议已被沉底的 bing
    assert hint["suggested_engine"] != "bing"
    assert hint["suggested_engine"] == "duckduckgo"