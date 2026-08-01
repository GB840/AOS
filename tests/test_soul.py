"""L3 灵魂层单元测试（诚实度 ②）。"""
from kernel.soul import ValueHierarchy, EmotionState


def test_resolve_deterministic():
    vh = ValueHierarchy()
    assert vh.resolve("speed", "accuracy") == "accuracy"
    assert vh.resolve("safety", "cost") == "safety"


def test_hard_constraint_blocks_lower_rank():
    vh = ValueHierarchy()
    assert vh.permitted("speed", ["safety"]) is False
    assert vh.permitted("safety", ["safety"]) is True


def test_low_mood_lowers_risk_weight():
    sad = EmotionState(mood=0.1)
    happy = EmotionState(mood=0.9)
    assert sad.risk_weight() < happy.risk_weight()


def test_emotion_adjust_for_life_risk():
    e = EmotionState(mood=0.5)
    assert e.adjust_for(0.0) == 0.0
    assert e.adjust_for(1.0) > 0.0
