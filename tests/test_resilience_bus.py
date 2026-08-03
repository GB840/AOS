"""ResilienceBus 自愈闭环单测（#510 收口验证）。

覆盖四条防御层融合后的核心语义：
  * 初始不误伤 live 引擎（should_skip 默认 False）
  * 连续失败达阈值 → 熔断 open → should_skip 返回 True，并触发自愈
  * 冷却后转 half_open → 允许探测 → 连续成功达阈值 → 关闭
  * 自愈动作按 restart → fallback → isolate → none 次序回退
  * on_outcome 把 outcome 回灌白盒蒸馏器（record_outcome 被调用）
  * health() 报告结构正确（circuit_trips / open_circuits / heal_actions）
  * reset_engine() 关闭熔断并清理 tripped
  * 全局单例 get/set
  * 跨层缺失（distiller=None / failure_monitor=None）不崩（best-effort）

诚实分级：②（代码+单测实证）。端到端（③，真 LLM + 真引擎 route 热路径）
需主机真环境，不在本测试范围；route() 接线为代码级已写、未在自动化覆盖。

用假时钟（mock time.time）消除真实 sleep，保证确定性与快跑。
"""

import sys
sys.path.insert(0, "D:/AOS/src")

import time
from unittest import mock

from core.fabric.resilience_bus import (
    ResilienceBus, _PerEngineBreaker,
    get_resilience_bus, set_resilience_bus,
)


# ── 基础语义 ──────────────────────────────────────────────

def test_initial_should_skip_false():
    """初始没有任何失败记录 → 不跳过任何引擎（绝不误伤 live 引擎）。"""
    bus = ResilienceBus()
    assert bus.should_skip("engine_a") is False


def test_success_does_not_trip():
    """连续成功永不触发熔断。"""
    bus = ResilienceBus()
    for _ in range(5):
        bus.on_outcome("engine_a", True, None)
    assert bus.should_skip("engine_a") is False
    assert bus.health()["circuit_trips"] == 0
    assert bus.health()["total_success"] == 5


def test_failure_trips_circuit():
    """连续失败达阈值（默认 3）→ 熔断 open → should_skip 返回 True，
    health() 正确记录 circuit_trips 与 open_circuits。"""
    bus = ResilienceBus()
    for _ in range(3):
        bus.on_outcome("engine_a", False, "boom")
    assert bus.should_skip("engine_a") is True
    h = bus.health()
    assert h["circuit_trips"] == 1
    assert "engine_a" in h["open_circuits"]


def test_failure_below_threshold_no_trip():
    """失败未达阈值（默认 3）→ 不熔断。"""
    bus = ResilienceBus()
    bus.on_outcome("e", False, "x")
    bus.on_outcome("e", False, "y")
    assert bus.should_skip("e") is False
    assert bus.health()["circuit_trips"] == 0


def test_circuit_recovers_after_cooldown_and_successes():
    """熔断 → 冷却后转 half_open（允许探测）→ 连续成功达阈值 → 关闭。

    用假时钟控制 cooldown 过渡，避免真实 sleep。
    """
    fake = {"t": 1000.0}

    def fake_time():
        return fake["t"]

    # 默认值即 failure_threshold=3 / cooldown=30.0 / success_threshold=2，
    # 与断言一致；阈值由模块常量统一控制，不在构造器暴露（避免 API 膨胀）。
    with mock.patch("core.fabric.resilience_bus.time.time", side_effect=fake_time):
        bus = ResilienceBus()
        for _ in range(3):
            bus.on_outcome("e", False, "x")
        assert bus.should_skip("e") is True            # open
        fake["t"] += 31.0                               # 越过 cooldown
        assert bus.should_skip("e") is False           # half_open → 允许探测
        bus.on_outcome("e", True, None)
        bus.on_outcome("e", True, None)
        assert bus.should_skip("e") is False           # closed
    h = bus.health()
    assert h["total_failures"] == 3
    assert h["total_success"] == 2
    assert h["open_circuits"] == {}                    # 已无开路


# ── 自愈动作回退链 ────────────────────────────────────────

def test_heal_restart_called_on_trip():
    """熔断触发 → 先尝试 restart，成功则记录 restart 并停止（不调 fallback）。"""
    restart = mock.MagicMock(return_value=True)
    fallback = mock.MagicMock(return_value=None)
    isolate = mock.MagicMock(return_value=False)
    bus = ResilienceBus(restart_engine=restart,
                        fallback_resolver=fallback,
                        isolate_engine=isolate)
    for _ in range(3):
        bus.on_outcome("e", False, "x")
    restart.assert_called_once_with("e")
    fallback.assert_not_called()
    assert any(h["action"] == "restart" for h in bus.health()["recent_heals"])


def test_heal_fallback_when_restart_fails():
    """restart 失败 → 尝试 fallback 找备选引擎，记录 fallback。"""
    restart = mock.MagicMock(return_value=False)
    fallback = mock.MagicMock(return_value="engine_b")
    isolate = mock.MagicMock(return_value=False)
    bus = ResilienceBus(restart_engine=restart,
                        fallback_resolver=fallback,
                        isolate_engine=isolate)
    for _ in range(3):
        bus.on_outcome("e", False, "x")
    restart.assert_called_once_with("e")
    fallback.assert_called_once_with("e")
    assert any(h["action"] == "fallback" for h in bus.health()["recent_heals"])


def test_heal_isolate_when_restart_and_fallback_fail():
    """restart + fallback 都失败 → 隔离引擎，记录 isolate。"""
    restart = mock.MagicMock(return_value=False)
    fallback = mock.MagicMock(return_value=None)
    isolate = mock.MagicMock(return_value=True)
    bus = ResilienceBus(restart_engine=restart,
                        fallback_resolver=fallback,
                        isolate_engine=isolate)
    for _ in range(3):
        bus.on_outcome("e", False, "x")
    assert any(h["action"] == "isolate" for h in bus.health()["recent_heals"])


def test_heal_none_when_all_actions_fail():
    """restart / fallback / isolate 全失败 → 记录 none（仍不阻塞主流程）。"""
    restart = mock.MagicMock(return_value=False)
    fallback = mock.MagicMock(return_value=None)
    isolate = mock.MagicMock(return_value=False)
    bus = ResilienceBus(restart_engine=restart,
                        fallback_resolver=fallback,
                        isolate_engine=isolate)
    for _ in range(3):
        bus.on_outcome("e", False, "x")
    assert any(h["action"] == "none" for h in bus.health()["recent_heals"])


def test_heal_triggered_only_once_per_trip():
    """同一引擎熔断期间只触发一次自愈（避免自愈风暴）。"""
    restart = mock.MagicMock(return_value=True)
    bus = ResilienceBus(restart_engine=restart)
    for _ in range(10):           # 远超阈值
        bus.on_outcome("e", False, "x")
    restart.assert_called_once_with("e")
    assert bus.health()["circuit_trips"] == 1


# ── 蒸馏器回灌 ────────────────────────────────────────────

def test_distiller_fed_on_outcome():
    """失败与成功 outcome 都回灌蒸馏器 record_outcome（白盒学习）。"""
    distiller = mock.MagicMock()
    bus = ResilienceBus(distiller=distiller)
    bus.on_outcome("e", False, "err1")
    bus.on_outcome("e", True, None)
    calls = distiller.record_outcome.call_args_list
    assert len(calls) == 2
    fail_call = [c for c in calls if c.args[2] is False][0]
    assert fail_call.args[0] == "e" and fail_call.args[1] == "e"
    assert fail_call.args[3] == "err1"
    ok_call = [c for c in calls if c.args[2] is True][0]
    assert ok_call.args[3] == ""


def test_no_distiller_no_crash():
    """distiller=None 时 on_outcome / health 不崩（best-effort 吞异常）。"""
    bus = ResilienceBus()  # 无 distiller
    for _ in range(3):
        bus.on_outcome("e", False, "x")
    assert bus.should_skip("e") is True
    assert bus.health()["distiller_connected"] is False


# ── 可观测 + 恢复 ─────────────────────────────────────────

def test_health_structure():
    """health() 返回必需字段且类型正确。"""
    bus = ResilienceBus()
    h = bus.health()
    for key in ("total_failures", "total_success", "circuit_trips",
                "open_circuits", "heal_actions", "recent_heals",
                "distiller_connected", "failure_monitor_connected"):
        assert key in h, f"health() 缺字段: {key}"


def test_reset_engine_closes_circuit():
    """外部成功恢复某引擎后 reset_engine() 关闭其熔断。"""
    bus = ResilienceBus()
    for _ in range(3):
        bus.on_outcome("e", False, "x")
    assert bus.should_skip("e") is True
    bus.reset_engine("e")
    assert bus.should_skip("e") is False
    assert "e" not in bus.health()["open_circuits"]


# ── 熔断器状态机（直接测内部类，确定性） ────────────────

def test_breaker_state_machine():
    """_PerEngineBreaker 状态机：closed → open → half_open → closed。"""
    fake = {"t": 0.0}

    def fake_time():
        return fake["t"]

    with mock.patch("core.fabric.resilience_bus.time.time", side_effect=fake_time):
        b = _PerEngineBreaker("x", failure_threshold=2,
                              cooldown=10.0, success_threshold=2)
        assert b.state == "closed"
        assert b.is_open is False
        b.on_failure()
        b.on_failure()                       # 达阈值 → open
        assert b.is_open is True
        assert b.is_open is True             # 冷却期内仍 open
        fake["t"] += 11.0                    # 越过 cooldown
        assert b.state == "half_open"
        assert b.is_open is False            # half_open 不算 open
        b.on_success()
        assert b.state == "half_open"        # 1/2 成功，未到阈值
        b.on_success()
        assert b.state == "closed"           # 2/2 成功 → 关闭
        assert b.is_open is False


# ── 全局单例 ──────────────────────────────────────────────

def test_singleton_get_set():
    """全局单例 set/get 一致；测试后还原，避免污染其他模块。"""
    prev = get_resilience_bus()
    try:
        bus = ResilienceBus()
        set_resilience_bus(bus)
        assert get_resilience_bus() is bus
    finally:
        set_resilience_bus(prev)
