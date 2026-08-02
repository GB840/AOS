"""生命体 OS 自研转化模块单元测试（白皮书 11.10 四项证伪→自研）。

覆盖：Mobius→L6 自进化引擎 / Holo→L2/L6 分形全息 / IEEE→L3 记忆生命周期 /
LeWM→L7 轻量世界模型。仅验证机制骨架（② 级），不声称端到端跑通。
"""

from __future__ import annotations

import time

from src.lifeform import (
    FractalHoloAgent,
    SelfEvolveEngine,
    WorldModelEngine,
)
from src.kernel.store.memory_lifecycle import (
    MemoryLifecycle,
    anchor,
    forget,
    importance_score,
    promote,
)


def test_self_evolve_guard_blocks_over_limit():
    eng = SelfEvolveEngine()
    # 连续逼近硬上限，应被护栏挡住
    for _ in range(60):
        eng.apply_rewrite("code", "feedback")
    snap = eng.snapshot()
    assert snap["iteration"] < eng.limit.max_iterations
    assert eng.can_evolve() is False


def test_self_evolve_empty_feedback_no_fabricated_improvement():
    eng = SelfEvolveEngine()
    out = eng.apply_rewrite("orig", "")
    assert out["applied"] is False
    assert eng.propose_rewrite("orig", "") == "orig"


def test_self_evolve_fitness_pure():
    eng = SelfEvolveEngine()
    assert eng.assess_fitness({}) == 0.0
    assert eng.assess_fitness({"success": 1.0}) == 1.0


def test_fractal_holo_three_stages():
    a = FractalHoloAgent(max_depth=3, max_children_per_node=2)
    a.self_learn({"accuracy": 0.5})
    child = a.self_improve("subtask-a")
    assert child is not None
    assert child.depth == 1
    a.self_adapt({"latency": 0.3})
    assert a.metrics["latency"] == 0.3
    assert a.count_nodes() == 2


def test_fractal_holo_depth_guard():
    a = FractalHoloAgent(max_depth=1, max_children_per_node=5)
    child = a.self_improve("x")
    assert child is not None
    # 已达 max_depth，不能再派生
    assert a.self_improve("y", parent=child) is None


def test_world_model_two_layer_causal():
    wm = WorldModelEngine()
    s1 = wm.predict("physical", {"x": 1.0})
    assert s1["x"] == 1.0
    s2 = wm.predict("human_centric", {"trust": 0.5})
    assert s2["trust"] == 0.5
    assert wm.causal_score() > 0.0
    assert wm.is_le_wm_active() is False  # 未接入真实 le-wm


def test_memory_lifecycle_promote_and_forget():
    ml = MemoryLifecycle()
    ml.ingest("m1", {"content": "重要记忆很重要很重要很重要", "recall_count": 20, "weight": 1.0})
    # 高频访问 → 重要性应超阈值 → 晋升
    assert promote(ml.store["m1"]) is not None

    ml.ingest("old", {"content": "x", "recall_count": 0, "weight": 0.0, "last_access": time.monotonic() - 86400 * 365})
    assert forget(ml.store["old"]) is True  # 一年后低频 → 遗忘

    anchored = {"content": "y", "user_anchored": True}
    anchor(anchored, "u1")
    assert forget(anchored) is False  # 锚定永不忘


def test_memory_lifecycle_tick_stats():
    ml = MemoryLifecycle()
    for i in range(5):
        ml.ingest(f"h{i}", {"content": "高频高频高频", "recall_count": 15, "weight": 1.0})
    stats = ml.tick()
    assert stats["promoted"] >= 1


def test_importance_score_bounds():
    assert 0.0 <= importance_score({"recall_count": 0}) <= 1.0
    assert importance_score({"recall_count": 100, "weight": 1.0, "user_anchored": True}) == 1.0
