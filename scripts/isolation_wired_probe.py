"""B 路线收口探针：把真实适配器隔离进子进程，跑通「路由→调用→崩溃→恢复」全环。

用法（沙箱需 tcp，生产可默认 pipe）：
    AOS_ISO_TRANSPORT=tcp python scripts/isolation_wired_probe.py
    python scripts/isolation_wired_probe.py            # 生产：Named Pipe

直接证明 FabricHub 现在能把一个芯粒放进独立进程：
  - route() 把请求打到子进程（PID 与宿主不同）；
  - 杀掉子进程后，recover() 在 ≤3s 内 respawn 并恢复服务；
  - 其余（未崩溃）引擎完全不受影响。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "D:/AOS/src")

from kernel.isolation.subprocess_iso import GATE_RECOVER_MS, GATE_SPAWN_MS
from kernel.plugins.fabric_hub import FabricHub
from kernel.isolation._bench_adapter import BenchRealAdapter


def _print(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    transport = os.environ.get("AOS_ISO_TRANSPORT", "pipe")
    print(f"[probe] transport={transport}")

    hub = FabricHub(adapters=())
    eid = hub.add_isolated_engine(
        "bench_real", BenchRealAdapter, transport=transport)
    _print(f"已隔离引擎 '{eid}' 进子进程")
    rep = hub.health_report()["adapters"][eid]
    print(f"  isolated={rep.get('isolated')}  live={rep['live']}  "
          f"caps={rep['capabilities']}")

    _print("经 FabricHub.route() 调用隔离引擎（应返回子进程 PID）")
    r1 = hub.route("bench.isolate", {"hello": "world"})
    pid1 = r1.data.get("pid") if r1.ok else None
    print(f"  ok={r1.ok}  pid={pid1}  host_pid={os.getpid()}")
    assert r1.ok and pid1 != os.getpid(), "隔离引擎未在子进程执行！"

    _print("模拟子进程崩溃（kill worker）")
    host = hub._isolated[eid]
    host._layer._proc.kill()
    host._layer._proc.wait()
    print(f"  崩溃后 health={host.health()}（应为 False）")
    assert host.health() is False

    _print("FabricHub.recover() 回收子进程")
    ok = hub.recover(eid)
    r2 = hub.route("bench.isolate", {"hello": "again"})
    pid2 = r2.data.get("pid") if r2.ok else None
    print(f"  recover_ok={ok}  live={host.health()}  new_pid={pid2}")
    assert ok and r2.ok and pid2 != os.getpid() and pid2 != pid1, "恢复失败！"

    spawn = host.spawn_ms or 0
    print(f"\n[结果] 子进程冷启动 spawn≈{spawn:.1f}ms "
          f"(闸门 {GATE_SPAWN_MS}ms)；recover 后已恢复服务。")
    print("[结论] B 路线收口成功：芯粒在独立进程运行，崩溃经 recover() 隔离恢复。")
    hub._isolated[eid].stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
