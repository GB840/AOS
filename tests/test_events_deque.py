"""测试EventBus使用deque（O1修复验证）"""
import pytest
from kernel.events import EventBus, Event, SystemEvent


def test_eventbus_deque_maxlen():
    """测试EventBus使用deque，超过maxlen时自动丢弃最旧事件"""
    bus = EventBus(max_history=5)

    # 发射6个事件
    for i in range(6):
        bus.emit(Event(
            event_type=SystemEvent.AGENT_STARTED,
            source="test",
            payload={"index": i}
        ))

    # 验证只有最近5个事件
    recent = bus.recent(n=10)
    assert len(recent) == 5

    # 验证最旧的事件是index=1，index=0被丢弃
    assert recent[0].payload["index"] == 1
    assert recent[-1].payload["index"] == 5


def test_eventbus_memory_stable():
    """测试EventBus内存稳定，事件数量不超过maxlen"""
    bus = EventBus(max_history=10000)

    # 发射20000个事件
    for i in range(20000):
        bus.emit(Event(
            event_type=SystemEvent.AGENT_STARTED,
            source="test",
            payload={"index": i}
        ))

    # 验证事件数量不超过maxlen
    assert len(bus._history) <= 10000

    # 验证最旧的事件是index=10000，之前的被丢弃
    all_events = bus.recent(n=10000)
    assert all_events[0].payload["index"] == 10000
    assert all_events[-1].payload["index"] == 19999


def test_eventbus_recent_with_filter():
    """测试EventBus.recent支持类型过滤"""
    bus = EventBus(max_history=100)

    # 发射不同类型的事件
    for i in range(10):
        bus.emit(Event(
            event_type=SystemEvent.AGENT_STARTED,
            source="test",
            payload={"index": i}
        ))
        bus.emit(Event(
            event_type=SystemEvent.AGENT_STOPPED,
            source="test",
            payload={"index": i}
        ))

    # 获取AGENT_STARTED事件
    started_events = bus.recent(n=20, event_type=SystemEvent.AGENT_STARTED)
    assert len(started_events) == 10
    assert all(e.event_type == SystemEvent.AGENT_STARTED for e in started_events)

    # 获取AGENT_STOPPED事件
    stopped_events = bus.recent(n=20, event_type=SystemEvent.AGENT_STOPPED)
    assert len(stopped_events) == 10
    assert all(e.event_type == SystemEvent.AGENT_STOPPED for e in stopped_events)