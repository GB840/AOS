"""L2D 资源自治调度单测（生命体OS 白皮书 L2D）。"""
from kernel.resource_autonomy import (
    ResourceAutonomy, R_TOKEN, R_MONEY, R_NET_CALL, DEFAULT_BASE,
)


def test_budget_shrinks_with_low_energy():
    ra = ResourceAutonomy()
    full = ra.budget(R_TOKEN, energy=1.0)
    low = ra.budget(R_TOKEN, energy=0.2)
    assert full == DEFAULT_BASE[R_TOKEN]
    assert low < full
    # 能量再低也留保命预算
    assert ra.budget(R_TOKEN, energy=0.0) == DEFAULT_BASE[R_TOKEN] * ra.min_energy_factor


def test_debt_tightens_budget():
    ra = ResourceAutonomy()
    b0 = ra.budget(R_TOKEN, energy=1.0, debt=0.0)
    b3 = ra.budget(R_TOKEN, energy=1.0, debt=3.0)
    assert b3 < b0
    assert abs(b3 - b0 * (0.85 ** 3)) < 1e-6


def test_request_grants_when_enough():
    ra = ResourceAutonomy()
    a = ra.request(R_TOKEN, 1000, energy=1.0)
    assert a.ok and a.degraded is False and a.granted == 1000


def test_request_degrades_instead_of_raising():
    """超支不是崩溃，是自主降级（如实标 degraded）。"""
    ra = ResourceAutonomy(base={R_MONEY: 1.0})
    a1 = ra.request(R_MONEY, 0.8, energy=1.0)
    assert a1.degraded is False
    a2 = ra.request(R_MONEY, 0.5, energy=1.0)
    assert a2.degraded is True
    assert abs(a2.granted - 0.2) < 1e-9
    assert "自主降级" in a2.reason


def test_unknown_resource_is_rejected_honestly():
    ra = ResourceAutonomy()
    a = ra.request("dark_matter", 1, energy=1.0)
    assert a.ok is False and "未知资源" in a.reason


def test_degrade_plan_actions_are_actionable():
    ra = ResourceAutonomy()
    plan = ra.degrade_plan(energy=0.1, debt=3.0)
    assert "switch_engine_tier:light" in plan
    assert "no_new_goals:true" in plan
    # 钱花光 → 硬停
    ra2 = ResourceAutonomy(base=dict(DEFAULT_BASE))
    ra2.request(R_MONEY, DEFAULT_BASE[R_MONEY], energy=1.0)
    assert "hard_stop:money_exhausted" in ra2.degrade_plan(energy=1.0)


def test_release_and_snapshot():
    ra = ResourceAutonomy()
    ra.request(R_NET_CALL, 100, energy=1.0)
    assert ra.used[R_NET_CALL] == 100
    ra.release(R_NET_CALL, 40)
    assert ra.used[R_NET_CALL] == 60
    snap = ra.snapshot(energy=1.0)
    assert snap[R_NET_CALL]["used"] == 60
    ra.reset()
    assert ra.used == {}
