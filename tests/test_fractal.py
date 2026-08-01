"""L7 分形派生 + 生长约束单元测试（诚实度 ②）。"""
import pytest

from kernel.fractal import FractalSpawner, GrowthGuard, MAX_GEN, MAX_SIBLINGS


def test_spawn_creates_child_with_decayed_quota():
    sp = FractalSpawner()
    child = sp.spawn("root", "c1", parent_gen=0, parent_quota=1.0)
    assert child.gen == 1
    assert abs(child.quota - 1 / 3) < 1e-6
    assert child.mem_ns == "root.c1"


def test_cannot_exceed_max_gen():
    sp = FractalSpawner()
    c1 = sp.spawn("root", "c1", 0, 1.0)
    c2 = sp.spawn("c1", "c2", 1, c1.quota)
    c3 = sp.spawn("c2", "c3", 2, c2.quota)
    with pytest.raises(RuntimeError):
        sp.spawn("c3", "c4", 3, c3.quota)


def test_sibling_limit():
    sp = FractalSpawner()
    for i in range(MAX_SIBLINGS):
        sp.spawn("root", f"s{i}", 0, 1.0)
    with pytest.raises(RuntimeError):
        sp.spawn("root", "overflow", 0, 1.0)


def test_growth_guard_approval():
    g = GrowthGuard()
    assert g.requires_approval("write") is True
    assert g.requires_approval("read") is False


def test_kill_marks_dead_not_removed():
    sp = FractalSpawner()
    sp.spawn("root", "c1", 0, 1.0)
    sp.kill("c1")
    assert sp.nodes["c1"].alive is False
