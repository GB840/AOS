"""热备切换机制的锁定测试（不依赖网络，用轻量 BenchRealAdapter）。

覆盖：
  - add 后热备已预拉起就绪；
  - 主进程崩溃 → 热备切换使 recover 过 3s 闸门且服务连续（PID 切换）；
  - standby=False 时回退冷启动 respawn，仍能恢复服务。

重型适配器（Agnes）与 bench 走同一套切换路径，仅冷启动成本不同；本测试用 bench
把「机制」与「重型 import 耗时」解耦，避免 CI 因 18s 冷启动 flaky。
"""
from __future__ import annotations

import pytest

from kernel.isolation.subprocess_iso import GATE_RECOVER_MS
from kernel.isolation._bench_adapter import BenchRealAdapter
from kernel.plugins.fabric_hub import FabricHub


@pytest.fixture
def hub():
    h = FabricHub(adapters=())
    eid = h.add_isolated_engine("bench-iso", BenchRealAdapter, standby=True)
    yield h, eid
    for e in list(h._isolated):
        h._isolated[e].stop()


def test_warm_standby_ready_after_add(hub):
    h, eid = hub
    host = h._isolated[eid]
    assert host.health() is True
    assert host._standby is not None, "add 后应已预拉起热备"


def test_crash_recover_via_standby_passes_gate(hub):
    h, eid = hub
    host = h._isolated[eid]
    # 稳态调用
    r1 = h.route("bench.ping", {"n": 1})
    assert r1.ok, f"稳态调用失败: {r1.error}"
    p1 = r1.data["pid"]
    # 杀主进程
    host._layer._proc.kill()
    host._layer._proc.wait()
    assert host.health() is False
    # 热备切换恢复（毫秒级）
    switched = host.recover()
    assert switched <= GATE_RECOVER_MS, f"热备切换 {switched:.0f}ms 超闸门"
    assert host.health() is True
    # 服务连续：恢复后调用仍成功，且换到热备进程（隔离 + 自愈铁证）
    r2 = h.route("bench.ping", {"n": 2})
    assert r2.ok, f"恢复后调用失败: {r2.error}"
    p2 = r2.data["pid"]
    assert p2 != p1, "恢复后应换到热备进程"


def test_no_standby_falls_back_to_cold_respawn():
    h = FabricHub(adapters=())
    eid = h.add_isolated_engine("bench-iso2", BenchRealAdapter, standby=False)
    host = h._isolated[eid]
    assert host._standby is None
    host._layer._proc.kill()
    host._layer._proc.wait()
    assert host.health() is False
    ok = h.recover(eid)
    assert ok is True, "冷启动 respawn 后未恢复"
    r = h.route("bench.ping", {"n": 3})
    assert r.ok, f"冷启动恢复后调用失败: {r.error}"
    host.stop()
