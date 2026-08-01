"""L0 生命状态内核单元测试（诚实度 ②）。"""
import pytest
from pathlib import Path

from kernel.life_state import LifeState, LifeStateStore


def test_decay_lowers_energy_and_raises_debt():
    s = LifeState(energy=1.0, debt=0.0)
    s.decay(cost=0.2, failed=1.0)
    assert s.energy == 0.8
    assert s.debt == 1.0


def test_low_energy_picks_light_engine():
    heavy, light = "qwen3-72b", "qwen3-1.7b"
    low = LifeState(energy=0.1)
    high = LifeState(energy=0.9)
    assert low.pick_engine_tier(heavy, light) == light
    assert high.pick_engine_tier(heavy, light) == heavy


def test_mood_lowers_risk_tolerance():
    sad = LifeState(mood=0.1)
    happy = LifeState(mood=0.9)
    assert sad.risk_tolerance() < happy.risk_tolerance()


def test_persistence_roundtrip(tmp_path: Path):
    store = LifeStateStore(base_dir=tmp_path)
    s = LifeState(energy=0.5, mood=0.7)
    store.save("u1", s)
    loaded = store.load("u1")
    assert loaded.energy == 0.5
    assert loaded.mood == 0.7
