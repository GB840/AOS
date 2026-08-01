"""L1 肉体层单测：HAL 统一指令集 + Phy-Bus 物理总线（生命体OS 白皮书 L1G/L1H）。"""
import pytest

from kernel.body import (
    HAL, Instruction, DeviceProfile, DryRunDriver, UnsupportedInstruction,
    PhyBus, Interlock, InterlockDenied,
)
from kernel.body.hal import CallableDriver, OPS
from kernel.body.phy_bus import QOS_BEST_EFFORT, QOS_IMPORTANT, QOS_CRITICAL


# ------------------------------------------------------------------ HAL
def test_instruction_rejects_unknown_op():
    with pytest.raises(ValueError):
        Instruction(op="explode")


def test_hal_routes_by_capability():
    hal = HAL()
    hal.register(DryRunDriver("cam0", "sensor", ops=["sense", "query"]))
    hal.register(DryRunDriver("gpu0", "gpu", ops=["compute"], latency_ms=2.0))
    cap = hal.capabilities()
    assert cap["sense"] == ["cam0"]
    assert cap["compute"] == ["gpu0"]
    res = hal.execute(Instruction("sense", args={"n": 1}))
    assert res.ok and res.device == "cam0" and res.dry_run is True


def test_hal_prefers_lower_latency():
    hal = HAL()
    hal.register(DryRunDriver("slow", "cpu", ops=["compute"], latency_ms=50.0))
    hal.register(DryRunDriver("fast", "npu", ops=["compute"], latency_ms=1.0))
    assert hal.execute(Instruction("compute")).device == "fast"


def test_hal_unsupported_raises_and_try_execute_returns_error():
    hal = HAL()
    hal.register(DryRunDriver("cam0", "sensor", ops=["sense"]))
    with pytest.raises(UnsupportedInstruction):
        hal.execute(Instruction("actuate"))
    r = hal.try_execute(Instruction("actuate"))
    assert r.ok is False and r.exit_code == 127 and "无驱动" in r.error


def test_hal_reports_real_failure_not_fake_success():
    """宪法理念 6：失败如实回传，不伪造成功。"""
    def boom(instr):
        raise RuntimeError("device offline")

    hal = HAL()
    hal.register(CallableDriver(
        DeviceProfile("arm0", "actuator", frozenset({"actuate"})), boom))
    r = hal.execute(Instruction("actuate", target="arm0"))
    assert r.ok is False and r.exit_code == 1
    assert "RuntimeError: device offline" in r.error


def test_unhealthy_device_not_routed():
    hal = HAL()
    d = DryRunDriver("cam0", "sensor", ops=["sense"])
    d._profile.healthy = False
    hal.register(d)
    assert hal.route(Instruction("sense")) is None


def test_dangerous_ops_flagged():
    assert Instruction("actuate").dangerous is True
    assert Instruction("reset").dangerous is True
    assert Instruction("sense").dangerous is False
    assert set(OPS) >= {"compute", "sense", "actuate", "render"}


# --------------------------------------------------------------- Phy-Bus
def test_interlock_denies_physical_output_by_default():
    bus = PhyBus()
    with pytest.raises(InterlockDenied):
        bus.emit("actuator/arm/move", {"deg": 30})
    assert bus.denied == 1


def test_interlock_grant_once_is_consumed():
    bus = PhyBus()
    bus.interlock.grant_once("actuator/arm/move")
    bus.emit("actuator/arm/move", {"deg": 30})       # 第一次放行
    with pytest.raises(InterlockDenied):             # 用完即焚
        bus.emit("actuator/arm/move", {"deg": 30})


def test_irreversible_topic_cannot_be_long_term_allowed():
    il = Interlock()
    with pytest.raises(InterlockDenied):
        il.allow("actuator/arm/move")
    il.allow("display/hud")          # 可逆输出可长期放行
    assert il.check("display/hud") is True


def test_backpressure_drops_low_qos_first():
    bus = PhyBus(capacity=2)
    bus.publish("imu", {"i": 1}, qos=QOS_BEST_EFFORT)
    bus.publish("imu", {"i": 2}, qos=QOS_BEST_EFFORT)
    m = bus.publish("hr", {"bpm": 180}, qos=QOS_CRITICAL)   # 关键消息必须进得来
    assert m is not None
    assert bus.dropped == 1
    topics = [x.topic for x in bus.drain()]
    assert "hr" in topics


def test_backpressure_drops_incoming_when_lowest():
    bus = PhyBus(capacity=1)
    bus.publish("hr", {"bpm": 60}, qos=QOS_CRITICAL)
    assert bus.publish("imu", {}, qos=QOS_BEST_EFFORT) is None
    assert bus.dropped == 1


def test_subscribe_receives_on_drain_and_emit():
    got = []
    bus = PhyBus()
    bus.subscribe("imu", got.append)
    bus.subscribe("display/hud", got.append)
    bus.publish("imu", {"x": 1}, qos=QOS_IMPORTANT)
    bus.drain()
    bus.interlock.allow("display/hud")
    bus.emit("display/hud", {"text": "hi"})
    assert [m.topic for m in got] == ["imu", "display/hud"]
    assert bus.stats()["pending"] == 0
