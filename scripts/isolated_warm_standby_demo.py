"""热备切换演示：真实/重型引擎隔离后，崩溃恢复走热备（毫秒级，过 3s 闸门）。

默认用轻量 BenchRealAdapter（秒级 spawn、零网络），聚焦「热备切换」机制本身；
稳态崩溃恢复**不再需要重新冷启动整个适配器**（重型 Agnes 实测 ~18s），因为
热备子进程早已热身待命。真实重型适配器与 bench 走的是同一套切换路径，仅冷启动
成本不同——这正是 Day22-30 B 路线「热进程池缓解冷启动」的最小完整落点。

运行（沙箱用 tcp，生产用默认 Named Pipe）：
    $env:AOS_ISO_TRANSPORT="tcp"
    python scripts/isolated_warm_standby_demo.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.environ.get(
    "AOS_SRC",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))))

from kernel.isolation.subprocess_iso import GATE_RECOVER_MS
from kernel.isolation._bench_adapter import BenchRealAdapter
from kernel.plugins.fabric_hub import FabricHub


def main() -> None:
    print("=== 热备切换演示（B 路线收口：崩溃恢复过 3s 闸门）===\n")
    # 真空枢纽，只挂我们要演示的隔离引擎（避免注册全部内置适配器）
    hub = FabricHub(adapters=())
    eid = hub.add_isolated_engine("bench-iso", BenchRealAdapter, standby=True)
    host = hub._isolated[eid]

    print(f"[init]    spawn_ms={host.spawn_ms:.1f}ms   热备就绪={host._standby is not None}")
    rep = hub.health_report()["adapters"][eid]
    print(f"[init]    health={rep['live']}   isolated={rep['isolated']}")

    # 稳态调用：经 FabricHub 路由到子进程，拿主进程 PID（隔离铁证）
    r1 = hub.route("bench.ping", {"n": 1})
    p1 = r1.data["pid"]
    print(f"[live]    route=bench.ping  主进程PID={p1}  ok={r1.ok}")

    # 模拟主进程崩溃
    host._layer._proc.kill()
    host._layer._proc.wait()
    print(f"[crash]   主进程 {p1} 已杀；health={host.health()}")

    # 热备切换恢复（毫秒级，远过 3s 闸门）
    t0 = time.perf_counter()
    switched_ms = host.recover()
    dt = (time.perf_counter() - t0) * 1000.0
    gate_ok = switched_ms <= GATE_RECOVER_MS
    print(f"[recover] 热备切换 switched_ms={switched_ms:.2f}ms  外部计时={dt:.2f}ms  "
          f"闸门={GATE_RECOVER_MS}ms  {'PASS' if gate_ok else 'FAIL'}")
    print(f"[recover] health={host.health()}  热备已接管，旧主退出")
    # 后台线程异步补位下一个热备（重型适配器约 18s，bench 约数百 ms）
    time.sleep(1.0)
    print(f"[recover] 后台补位完成={host._standby is not None}")

    # 服务连续：恢复后调用仍成功，且跑在提拔的热备进程里（PID 变了）
    r2 = hub.route("bench.ping", {"n": 2})
    p2 = r2.data["pid"]
    print(f"[live]    route=bench.ping  热备进程PID={p2}  ok={r2.ok}  "
          f"PID变化={p2 != p1}")

    assert r2.ok and p2 != p1, "服务未连续或热备未接管"
    assert gate_ok, "热备切换超闸门"
    print("\n=== 演示通过：真实引擎隔离 + 热备切换使崩溃恢复过 3s 闸门 ===")

    for e in list(hub._isolated):
        hub._isolated[e].stop()


if __name__ == "__main__":
    main()
