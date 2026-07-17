"""测试AnomalyDetector事件类型分组（O2修复验证）"""
import pytest
import time
from kernel.events import EventBus, Event, SystemEvent
from kernel.immunity import AnomalyDetector


def test_anomaly_detector_event_grouping():
    """测试AnomalyDetector按事件类型分组存储事件"""
    bus = EventBus()
    detector = AnomalyDetector(bus, window_seconds=60.0)

    # 发射不同类型的事件
    for i in range(10):
        bus.emit(Event(
            event_type=SystemEvent.MODEL_FAILED,
            source="test",
            payload={"index": i}
        ))
        bus.emit(Event(
            event_type=SystemEvent.AGENT_STARTED,
            source="test",
            payload={"index": i}
        ))
        bus.emit(Event(
            event_type=SystemEvent.SKILL_FAILED,
            source="test",
            payload={"index": i}
        ))

    # 验证事件按类型分组存储
    with detector._lock:
        assert SystemEvent.MODEL_FAILED in detector._events_by_type
        assert SystemEvent.AGENT_STARTED in detector._events_by_type
        assert SystemEvent.SKILL_FAILED in detector._events_by_type

        assert len(detector._events_by_type[SystemEvent.MODEL_FAILED]) == 10
        assert len(detector._events_by_type[SystemEvent.AGENT_STARTED]) == 10
        assert len(detector._events_by_type[SystemEvent.SKILL_FAILED]) == 10


def test_anomaly_detector_high_frequency_performance():
    """测试高频事件响应时间<500ms"""
    bus = EventBus()
    detector = AnomalyDetector(bus, window_seconds=60.0)

    # 发射100个事件
    start = time.time()
    for i in range(100):
        bus.emit(Event(
            event_type=SystemEvent.MODEL_FAILED,
            source="test",
            payload={"index": i}
        ))
    end = time.time()

    # 验证响应时间<500ms
    elapsed = (end - start) * 1000  # 转换为毫秒
    assert elapsed < 500, f"高频事件响应时间{elapsed:.2f}ms超过500ms阈值"


def test_anomaly_detector_error_rate_calculation():
    """测试错误率计算正确"""
    bus = EventBus()
    detector = AnomalyDetector(bus, window_seconds=60.0)

    # 发射10个成功事件和10个失败事件
    for i in range(10):
        bus.emit(Event(
            event_type=SystemEvent.MODEL_INVOKED,
            source="test",
            payload={"index": i}
        ))
        bus.emit(Event(
            event_type=SystemEvent.MODEL_FAILED,
            source="test",
            payload={"index": i}
        ))

    # 验证错误率为50%
    error_rate = detector.error_rate()
    assert error_rate == 0.5, f"错误率应该是0.5，实际是{error_rate}"