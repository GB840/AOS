"""L2F 元认知自省内核单测（生命体OS 白皮书 L2F）。"""
from kernel.metacognition import (
    Metacognition, VERDICT_CONTINUE, VERDICT_GATHER, VERDICT_REFLECT, VERDICT_ABORT,
)


def test_strong_evidence_allows_continue():
    m = Metacognition()
    r = m.introspect(text="x" * 300, claimed_confidence=0.9,
                     sources=3, exit_code=0, bytes_written=2000, search_hits=5)
    assert r.verdict == VERDICT_CONTINUE
    assert r.evidence_score > 0.5
    assert r.overconfident is False


def test_hedging_text_kills_evidence_score():
    """拒答话术不算证据——不许拿'作为一个AI我无法'冒充结论。"""
    m = Metacognition()
    r = m.introspect(text="作为一个AI，我无法访问网络，抱歉。",
                     claimed_confidence=0.95)
    assert r.evidence_score < 0.2
    assert r.verdict in (VERDICT_GATHER, VERDICT_ABORT)
    assert r.overconfident is True


def test_calibration_caps_confidence_by_evidence():
    m = Metacognition()
    r = m.introspect(text="也许可能大概吧", claimed_confidence=1.0)
    assert r.confidence < r.claimed_confidence
    assert r.overconfident is True


def test_loop_detection_by_repeated_action():
    m = Metacognition(loop_window=6, loop_repeat=3)
    for _ in range(3):
        m.record_action("web.search", {"q": "同一个查询"})
    assert m.detect_loop() is True
    r = m.introspect(text="y" * 300, sources=3, exit_code=0)
    assert r.looping is True and r.verdict == VERDICT_REFLECT


def test_loop_detection_by_repeated_error():
    m = Metacognition()
    m.record_error("ModuleNotFoundError: no module named foo")
    m.record_error("ModuleNotFoundError: no module named foo")
    assert m.detect_loop() is True


def test_different_actions_not_a_loop():
    m = Metacognition()
    m.record_action("web.search", {"q": "a"})
    m.record_action("code.exec", {"src": "b"})
    m.record_action("fs.write", {"p": "c"})
    assert m.detect_loop() is False


def test_abort_at_last_step_with_no_evidence():
    m = Metacognition()
    r = m.introspect(text="", claimed_confidence=0.5, step_index=19, max_steps=20)
    assert r.verdict == VERDICT_ABORT


def test_failed_exit_code_lowers_evidence():
    m = Metacognition()
    ok = m.evidence_score("z" * 250, exit_code=0)
    bad = m.evidence_score("z" * 250, exit_code=1)
    assert bad < ok


def test_reset_clears_state():
    m = Metacognition()
    m.record_action("a")
    m.record_error("e")
    m.reset()
    assert m.detect_loop() is False
