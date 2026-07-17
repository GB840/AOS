"""测试SelfHealer和AnomalyDetector联动（O4修复验证）"""
import pytest
from kernel.events import EventBus, Event, SystemEvent
from kernel.immunity import AnomalyDetector, SelfHealer


def test_selfhealer_anomaly_detector_linkage():
    """测试AnomalyDetector检测到异常时SelfHealer自动触发"""
    bus = EventBus()
    detector = AnomalyDetector(bus, window_seconds=60.0, consecutive_failures=3)

    healed_actions = []

    def mock_restart(agent_id: str) -> bool:
        healed_actions.append(("restart", agent_id))
        return True

    def mock_fallback(model: str) -> str:
        healed_actions.append(("fallback", model))
        return "backup_model"

    def mock_isolate(skill_id: str) -> bool:
        healed_actions.append(("isolate", skill_id))
        return True

    healer = SelfHealer(
        bus,
        detector=detector,
        restart_agent=mock_restart,
        fallback_model=mock_fallback,
        isolate_skill=mock_isolate
    )

    # 发射3次agent.failed事件，触发连续失败异常
    for i in range(3):
        bus.emit(Event(
            event_type=SystemEvent.AGENT_FAILED,
            source="agent123",
            payload={"agent_id": "agent123"}
        ))

    # 验证SelfHealer自动触发恢复操作
    assert len(healed_actions) > 0
    assert any(action[0] == "restart" and action[1] == "agent123" for action in healed_actions)


def test_selfhealer_recovery_strategy_matching():
    """测试SelfHealer恢复策略匹配"""
    bus = EventBus()
    detector = AnomalyDetector(bus, window_seconds=60.0, consecutive_failures=3)

    healed_actions = []

    def mock_restart(agent_id: str) -> bool:
        healed_actions.append(("restart", agent_id))
        return True

    def mock_fallback(model: str) -> str:
        healed_actions.append(("fallback", model))
        return "backup_model"

    def mock_isolate(skill_id: str) -> bool:
        healed_actions.append(("isolate", skill_id))
        return True

    healer = SelfHealer(
        bus,
        detector=detector,
        restart_agent=mock_restart,
        fallback_model=mock_fallback,
        isolate_skill=mock_isolate
    )

    # 测试agent失败触发restart
    for i in range(3):
        bus.emit(Event(
            event_type=SystemEvent.AGENT_FAILED,
            source="agent123",
            payload={"agent_id": "agent123"}
        ))

    # 测试skill失败触发isolate
    for i in range(3):
        bus.emit(Event(
            event_type=SystemEvent.SKILL_FAILED,
            source="skill456",
            payload={"skill_id": "skill456"}
        ))

    # 验证恢复策略匹配正确
    assert any(action[0] == "restart" and action[1] == "agent123" for action in healed_actions)
    assert any(action[0] == "isolate" and action[1] == "skill456" for action in healed_actions)