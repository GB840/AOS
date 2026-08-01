"""L4 双向思辨演化调节器 单测（诚实度 ②）"""
from kernel.soul.dialectic import DialecticRegulator


def test_low_mid_high_strength():
    low = DialecticRegulator("low")
    mid = DialecticRegulator("mid")
    high = DialecticRegulator("high")
    v = "本地优先是最好架构"
    assert len(low.challenge(v)) == 1
    assert len(mid.challenge(v)) == 2
    assert len(high.challenge(v)) == 3


def test_set_level():
    r = DialecticRegulator("low")
    r.set_level("high")
    assert len(r.challenge("x")) == 3
