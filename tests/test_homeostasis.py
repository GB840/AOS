"""L2E 体感稳态系统单测（生命体OS 白皮书 L2E）。"""
from kernel.homeostasis import Homeostasis, Vital


def test_within_deadband_no_correction():
    h = Homeostasis.with_defaults()
    out = h.tick({"energy": 0.52, "focus": 0.6, "mood": 0.5, "debt": 0.5,
                  "error_rate": 0.1})
    assert out == []
    assert h.is_stable() is True


def test_low_energy_triggers_rest():
    h = Homeostasis.with_defaults()
    out = h.tick({"energy": 0.1})
    assert len(out) == 1
    assert out[0].vital == "energy" and out[0].action == "rest_cycle"
    assert out[0].effort > 0
    assert "energy" in h.unstable_vitals()


def test_high_debt_triggers_pay_debt():
    h = Homeostasis.with_defaults()
    out = h.tick({"debt": 4.0})
    assert out[0].vital == "debt" and out[0].action == "pay_debt_first"


def test_repeated_instability_escalates_to_critical():
    h = Homeostasis(instability_threshold=3)
    h.register(Vital("energy", setpoint=0.5, higher_is_better=True))
    for _ in range(2):
        c = h.tick({"energy": 0.4})[0]
        assert c.severity != "critical"
    c = h.tick({"energy": 0.4})[0]
    assert c.severity == "critical"


def test_recovery_resets_streak():
    h = Homeostasis()
    h.register(Vital("energy", setpoint=0.5, higher_is_better=True))
    h.tick({"energy": 0.2})
    assert h.is_stable() is False
    h.tick({"energy": 0.9})
    assert h.is_stable() is True


def test_should_hibernate_after_prolonged_instability():
    h = Homeostasis(instability_threshold=2)
    h.register(Vital("energy", setpoint=0.5, higher_is_better=True))
    for _ in range(4):
        h.tick({"energy": 0.05})
    assert h.should_hibernate() is True


def test_corrections_sorted_by_effort():
    h = Homeostasis.with_defaults()
    out = h.tick({"energy": 0.40, "mood": 0.0})   # 0.40 越过 0.05 死区
    assert len(out) == 2
    assert out[0].effort >= out[1].effort
