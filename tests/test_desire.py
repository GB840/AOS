"""L2 内生欲望引擎 单测（诚实度 ②）"""
from kernel.desire import DesireEngine, GoalCandidate


def test_energy_gate_blocks_high_cost_when_low():
    e = DesireEngine(energy_floor=0.25)
    cands = e.propose(
        energy=0.1,  # 低能量
        recent_goals=[],
        memory_gaps=["量子计算"],
        failed_topics=[],
    )
    # 低能量时只允许低成本（维护型 cost=0.1）目标
    assert all(c.cost <= 0.15 for c in cands)
    assert any(c.source == "maintenance" for c in cands)


def test_normal_energy_allows_curiosity():
    e = DesireEngine()
    cands = e.propose(
        energy=0.8,
        recent_goals=[],
        memory_gaps=["Rust 异步"],
        failed_topics=["向量检索"],
    )
    texts = [c.text for c in cands]
    assert any("Rust 异步" in t for t in texts)
    assert any("换思路重试" in t for t in texts)


def test_recent_goals_deduped():
    e = DesireEngine()
    cands = e.propose(
        energy=0.8,
        recent_goals=["换思路重试：向量检索"],
        memory_gaps=[],
        failed_topics=["向量检索"],
    )
    assert not any("向量检索" in c.text for c in cands)
