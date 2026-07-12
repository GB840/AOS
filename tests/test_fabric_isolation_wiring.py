"""FabricHub × 子进程隔离 收口测试（沙箱用 tcp 传输；set AOS_ISO_TRANSPORT=tcp）。

覆盖：
  1. worker 能托管一个真实 BaseAgentAdapter，invoke 在子进程地址空间执行；
  2. FabricHub.add_isolated_engine 注册后，route() 打到子进程、recover() 回收；
  3. 崩溃隔离：杀掉子进程不影响宿主，recover() 在 ≤3s 内恢复服务。
"""
from __future__ import annotations

import os

import pytest

from kernel.isolation._bench_adapter import BenchRealAdapter
from kernel.isolation.subprocess_iso import GATE_RECOVER_MS, SubprocessIsolationLayer
from kernel.plugins.fabric_hub import FabricHub


TRANSPORT = os.environ.get("AOS_ISO_TRANSPORT", "tcp")


@pytest.fixture
def host():
    layer = SubprocessIsolationLayer(
        engine_id="bench_real",
        adapter_spec="kernel.isolation._bench_adapter:BenchRealAdapter",
        transport=TRANSPORT,
    )
    layer.start()
    yield layer
    layer.stop()


def test_worker_hosts_real_adapter_in_subprocess(host):
    """worker 托管真实适配器，响应带回子进程 PID（≠ 父进程）。"""
    resp = host.invoke("bench.isolate", {"k": "v"})
    assert isinstance(resp, dict) and resp.get("ok") is True
    data = resp["data"]
    assert data["pid"] != os.getpid(), "invoke 未跑在子进程"
    assert data["cap"] == "bench.isolate"
    assert data["echo"] == {"k": "v"}


def test_worker_ping_capability_routable(host):
    resp = host.invoke("bench.ping", {})
    assert resp.get("ok") is True


def test_hub_isolates_engine_and_recovers():
    hub = FabricHub(adapters=())
    eid = hub.add_isolated_engine("bench_real", BenchRealAdapter, transport=TRANSPORT)
    try:
        # 注册为隔离引擎，健康检查应标记 isolated=True
        rep = hub.health_report()["adapters"][eid]
        assert rep["isolated"] is True
        assert rep["live"] is True

        # route() 打到子进程
        r1 = hub.route("bench.isolate", {"x": 1})
        assert r1.ok and r1.data["pid"] != os.getpid()

        # 模拟崩溃
        iso_host = hub._isolated[eid]
        iso_host._layer._proc.kill()
        iso_host._layer._proc.wait()
        assert iso_host.health() is False

        # recover() 回收并恢复
        ok = hub.recover(eid)
        assert ok is True
        assert iso_host.health() is True
        r2 = hub.route("bench.isolate", {"x": 2})
        assert r2.ok and r2.data["pid"] != os.getpid()
    finally:
        hub._isolated[eid].stop()


def test_recover_within_gate():
    """崩溃恢复耗时 ≤3s 闸门（B 路线硬指标）。"""
    import time
    hub = FabricHub(adapters=())
    eid = hub.add_isolated_engine("bench_real", BenchRealAdapter, transport=TRANSPORT)
    try:
        iso_host = hub._isolated[eid]
        iso_host._layer._proc.kill()
        iso_host._layer._proc.wait()
        t0 = time.perf_counter()
        hub.recover(eid)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        assert dt_ms <= GATE_RECOVER_MS, f"恢复 {dt_ms:.0f}ms 超闸门 {GATE_RECOVER_MS}ms"
    finally:
        hub._isolated[eid].stop()
