"""AnomalyDetector 连续失败计数回归测试。

背景（审查报告 #5，已核实为真 bug）：
``_check_consecutive`` 只做 ``+= 1``，全代码没有任何归零路径。
名义上的"连续失败"实际是"自进程启动以来累计失败数"——
长时间运行的进程必然把零散失败堆到阈值，触发不该发生的重启/隔离/降级。

本测试锁死修复后的语义：
1. 连续失败会累加并在到阈值时告警；
2. 一次成功调用会打断连击，计数归零；
3. 归零后重新连挂到阈值仍能再次告警（不是一次性哑火）；
4. 中性事件（agent.registered / skill.discovered）不清计数。

诚实分级：② 级（代码 + 单测实证，纯 stdlib，无真 LLM 参与）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.events import Event, EventBus, SystemEvent  # noqa: E402
from kernel.immunity import AnomalyDetector  # noqa: E402


def _mk(threshold: int = 3):
    alerts = []
    bus = EventBus()
    det = AnomalyDetector(
        bus,
        consecutive_failures=threshold,
        on_alert=lambda rule, msg, detail: alerts.append((rule, msg, detail)),
    )
    return bus, det, alerts


def _fail(bus: EventBus, n: int = 1) -> None:
    for _ in range(n):
        bus.emit(Event(SystemEvent.MODEL_FAILED, "gw", payload={"model": "m"}))


def _ok(bus: EventBus, n: int = 1) -> None:
    for _ in range(n):
        bus.emit(Event(SystemEvent.MODEL_INVOKED, "gw", payload={"model": "m"}))


def test_consecutive_failures_accumulate_and_alert():
    bus, det, alerts = _mk(threshold=3)
    _fail(bus, 2)
    assert det.consecutive_failure_count == 2
    assert alerts == []

    _fail(bus, 1)
    assert det.consecutive_failure_count == 3
    assert len(alerts) == 1
    assert alerts[0][0] == "consecutive_failures"


def test_success_resets_the_streak():
    """核心回归：一次成功必须打断失败连击。"""
    bus, det, alerts = _mk(threshold=3)
    _fail(bus, 2)
    assert det.consecutive_failure_count == 2

    _ok(bus, 1)
    assert det.consecutive_failure_count == 0, "成功事件未归零 → 退回旧 bug"

    # 再挂两次也不该告警：真实的"连续 3 次"还没发生
    _fail(bus, 2)
    assert alerts == [], "成功打断后仍误报，说明计数没真正归零"
    assert det.consecutive_failure_count == 2


def test_alert_can_fire_again_after_reset():
    bus, det, alerts = _mk(threshold=3)
    _fail(bus, 3)
    assert len(alerts) == 1

    _ok(bus, 1)
    assert det.consecutive_failure_count == 0

    _fail(bus, 3)
    assert len(alerts) == 2, "归零后应能重新触发告警，而不是永久哑火"


def test_interleaved_failures_never_reach_threshold():
    """成败交替（真实系统的常态）不应被误判为连续失败。"""
    bus, det, alerts = _mk(threshold=3)
    for _ in range(20):
        _fail(bus, 2)
        _ok(bus, 1)
    assert alerts == [], "成败交替被误报为连续失败 → 旧 bug 未修"
    # 最后一个事件是成功，计数应停在 0；旧实现此处会是 40
    assert det.consecutive_failure_count == 0


def test_neutral_events_do_not_reset_streak():
    """agent.registered / skill.discovered 是中性事件，不代表调用成功。"""
    bus, det, _alerts = _mk(threshold=5)
    _fail(bus, 3)
    bus.emit(Event(SystemEvent.AGENT_REGISTERED, "kernel", payload={"agent_id": "a1"}))
    bus.emit(Event(SystemEvent.SKILL_DISCOVERED, "kernel", payload={"skill_id": "s1"}))
    assert det.consecutive_failure_count == 3, "中性事件不应清空失败计数"


def test_is_healthy_recovers_after_success():
    bus, det, _alerts = _mk(threshold=3)
    _fail(bus, 3)
    assert det.is_healthy() is False

    # 连续成功既拉低错误率，也归零连击计数
    _ok(bus, 20)
    assert det.consecutive_failure_count == 0
    assert det.is_healthy() is True, "恢复后仍判 unhealthy → 系统永远无法自愈出坑"


def test_manual_reset_api():
    bus, det, _alerts = _mk(threshold=5)
    _fail(bus, 4)
    assert det.consecutive_failure_count == 4
    det.reset_consecutive()
    assert det.consecutive_failure_count == 0


def test_success_across_all_four_channels():
    """model / agent / skill / message 四条订阅链都要能归零。"""
    cases = [
        (SystemEvent.MODEL_FAILED, SystemEvent.MODEL_INVOKED),
        (SystemEvent.AGENT_FAILED, SystemEvent.AGENT_STARTED),
        (SystemEvent.SKILL_FAILED, SystemEvent.SKILL_CALLED),
        (SystemEvent.MESSAGE_DENIED, SystemEvent.MESSAGE_ROUTED),
    ]
    for fail_evt, ok_evt in cases:
        bus, det, _alerts = _mk(threshold=5)
        bus.emit(Event(fail_evt, "src", payload={}))
        bus.emit(Event(fail_evt, "src", payload={}))
        assert det.consecutive_failure_count == 2, f"{fail_evt} 未累加"
        bus.emit(Event(ok_evt, "src", payload={}))
        assert det.consecutive_failure_count == 0, f"{ok_evt} 未归零"
