"""FabricHub 芯粒崩溃隔离 + 恢复（Day11-14 闸门3）。

核心属性（对应 Chiplet 故障隔离）：
1. 单芯粒 invoke 抛异常 -> 被隔离，返回干净 InvokeResult(ok=False)，绝不穿透。
2. 崩溃的芯粒不影响「旁观芯粒」与内核本身（不传染）。
3. 崩溃后可在 ≤3s 内恢复服务（进程内芯粒对象常驻，复探 health 即恢复）。

不依赖任何真实 OSS 引擎，全部用合成芯粒，环境无关、可重复。
"""
from __future__ import annotations

import time

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from kernel.plugins.fabric_hub import FabricHub


class _BystanderAdapter(BaseAgentAdapter):
    """旁观芯粒：永远健康、永远成功，用于验证「不传染」。"""

    engine_id = "bystander"

    def advertise_capabilities(self):
        return [Capability.BENCH_ISOLATE]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=True, data={"from": "bystander"})


class _FlakyAdapter(BaseAgentAdapter):
    """会崩溃的芯粒：首次 invoke 抛异常（模拟进程崩），其后恢复。"""

    engine_id = "flaky"

    def __init__(self) -> None:
        self._crashes_left = 1

    def advertise_capabilities(self):
        return [Capability.BENCH_PING]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if self._crashes_left > 0:
            self._crashes_left -= 1
            raise RuntimeError("simulated chiplet crash")
        return InvokeResult(ok=True, data={"recovered": True})


def _make_hub():
    # 用合成芯粒构造枢纽，隔离真实引擎；顺序：flaky 在前（bench.ping 唯一提供者）
    return FabricHub(adapters=(_FlakyAdapter, _BystanderAdapter))


def test_crash_is_isolated_not_propagated():
    hub = _make_hub()
    # 触发崩溃：必须返回干净失败结果，绝不抛异常穿透到测试
    res = hub.route("bench.ping", {})
    assert res.ok is False
    assert res.error is not None
    assert "flaky" in res.error


def test_crash_does_not_contaminate_bystander_or_kernel():
    hub = _make_hub()
    hub.route("bench.ping", {})  # flaky 崩溃
    # 内核 + 旁观芯粒仍完全正常（不传染）
    res = hub.route("bench.isolate", {})
    assert res.ok is True
    assert res.data == {"from": "bystander"}


def test_recovery_within_3s():
    hub = _make_hub()
    t0 = time.perf_counter()
    first = hub.route("bench.ping", {})  # 崩溃
    assert first.ok is False
    fail_ts = hub.last_failure("flaky")
    assert fail_ts is not None
    # 恢复：进程内芯粒对象常驻，复探 health 即恢复为 live
    assert hub.recover("flaky") is True
    recovered = hub.route("bench.ping", {})  # 第二次成功
    recovery_ms = (time.perf_counter() - (fail_ts or t0)) * 1000.0
    assert recovered.ok is True
    assert recovered.data == {"recovered": True}
    # 闸门：从故障检测到恢复服务 ≤ 3s（此处为微秒级，远优于上限）
    assert recovery_ms <= 3000.0
