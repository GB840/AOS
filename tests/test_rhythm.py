"""L2 生命节律调度 单测（诚实度 ②）"""
from kernel.rhythm import RhythmScheduler


def test_deep_sleep_at_night():
    s = RhythmScheduler()
    d = s.tick(energy=0.9, debt=0.0, hour=3)
    assert d.mode == "deep_sleep"


def test_rest_when_low_energy():
    s = RhythmScheduler()
    d = s.tick(energy=0.1, debt=0.0, hour=14)
    assert d.mode == "rest"
    assert "能量" in d.reason


def test_review_at_end_of_day():
    s = RhythmScheduler()
    d = s.tick(energy=0.9, debt=0.0, hour=23)
    assert d.mode == "review"


def test_active_when_healthy():
    s = RhythmScheduler()
    d = s.tick(energy=0.9, debt=0.1, hour=10)
    assert d.mode == "active"


def test_deep_sleep_on_high_debt():
    s = RhythmScheduler(debt_sleep=0.8)
    d = s.tick(energy=0.9, debt=0.9, hour=10)
    assert d.mode == "deep_sleep"
