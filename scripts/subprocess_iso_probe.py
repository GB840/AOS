"""B 路线（子进程隔离）三闸门探测 + 热池缓解验证。

用法（仓库根 D:/AOS，系统 Python 3.14）：
    python scripts/subprocess_iso_probe.py                 # 默认 Named Pipe（宿主）
    AOS_ISO_TRANSPORT=tcp python scripts/subprocess_iso_probe.py   # 沙箱/CI 验证

闸门（用户定义，Day22-30）：
  - 拉起(spawn)       ≤ 500ms
  - 单次 IPC 往返(RTT) ≤ 100μs
  - 崩溃恢复(recovery) ≤ 3s

两个场景：
  A. 朴素冷启动：每次请求现拉进程 → 测真实 spawn/RTT/recovery。
  B. 热进程池（生产形态）：预拉热 worker，稳态 assign≈0，崩溃后台 recycle。
退出码 0 = 三闸门全过；1 = 存在未过闸门。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "D:/AOS/src")

from kernel.isolation.subprocess_iso import (
    SubprocessIsolationLayer,
    SubprocessPool,
    GATE_SPAWN_MS,
    GATE_RTT_US,
    GATE_RECOVER_MS,
)

N_PINGS = 50
POOL_SIZE = 2


def _run_naive(transport: str) -> dict:
    layer = SubprocessIsolationLayer(engine_id="bench_iso", transport=transport)
    spawn_ms = layer.start()
    layer.invoke("bench.ping", {"x": 1}, iters=N_PINGS)
    rtt_us = layer.rtt_us
    rec_ms = layer.kill_and_recover()
    res = layer.invoke("bench.ping", {"after": "recover"}, iters=5)
    ok = isinstance(res, dict) and res.get("ok") is True
    layer.stop()
    return {"spawn_ms": spawn_ms, "rtt_us": rtt_us, "rec_ms": rec_ms, "ok": ok}


def _run_pool(transport: str) -> dict:
    pool = SubprocessPool(engine_id="bench_pool", size=POOL_SIZE, transport=transport)
    warmup_ms = pool.warmup()
    # 稳态：连续取/还 worker，assign_ms 取中位
    assign_samples = []
    rtt_samples = []
    w0, _ = pool.acquire()
    w0.invoke("bench.ping", {"x": 1}, iters=N_PINGS)
    rtt_samples.append(w0.rtt_us)
    pool.release(w0)
    for _ in range(N_PINGS):
        w, a = pool.acquire()
        assign_samples.append(a)
        w.invoke("bench.ping", {"k": 1})
        pool.release(w)
    assign_samples.sort()
    assign_ms = assign_samples[len(assign_samples) // 2]
    rtt_us = rtt_samples[0]
    # 稳态中模拟一个 worker 崩溃：取一个，杀掉，验证池仍能服务（其余热 worker），
    # 随后 recycle 该崩溃 worker 恢复容量。
    w_crash, _ = pool.acquire()
    w_crash._proc.kill(); w_crash._proc.wait()
    still_ok = pool.available >= 1  # 还有热 worker 可服务
    rec_ms = pool.recycle(w_crash)
    post = pool.acquire()[0].invoke("bench.ping", {"after": "recycle"})
    post_ok = isinstance(post, dict) and post.get("ok") is True
    pool.stop()
    return {
        "warmup_ms": warmup_ms, "assign_ms": assign_ms, "rtt_us": rtt_us,
        "still_serving": still_ok, "rec_ms": rec_ms, "post_ok": post_ok,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", default=os.environ.get("AOS_ISO_TRANSPORT", "pipe"),
                    choices=["pipe", "tcp"],
                    help="pipe=Windows Named Pipe(生产默认); tcp=loopback(沙箱验证用)")
    args = ap.parse_args()
    print("transport = %s" % args.transport)
    print("=" * 86)
    print("场景 A · 朴素冷启动（每次请求现拉进程）")
    print("=" * 86)
    a = _run_naive(args.transport)
    g1 = a["spawn_ms"] <= GATE_SPAWN_MS
    g2 = a["rtt_us"] <= GATE_RTT_US
    g3 = a["rec_ms"] <= GATE_RECOVER_MS
    print("spawn_ms          = %9.2f ms | gate ≤ %5.0f ms | %s"
          % (a["spawn_ms"], GATE_SPAWN_MS, "PASS" if g1 else "FAIL"))
    print("rtt_us (median)   = %9.2f μs | gate ≤ %5.0f μs | %s"
          % (a["rtt_us"], GATE_RTT_US, "PASS" if g2 else "FAIL"))
    print("recovery_ms       = %9.2f ms | gate ≤ %5.0f ms | %s"
          % (a["rec_ms"], GATE_RECOVER_MS, "PASS" if g3 else "FAIL"))
    print("post-recovery ok  = %s" % a["ok"])

    print("=" * 86)
    print("场景 B · 热进程池（生产形态：预拉热 worker）")
    print("=" * 86)
    b = _run_pool(args.transport)
    pg1 = b["assign_ms"] <= GATE_SPAWN_MS
    pg2 = b["rtt_us"] <= GATE_RTT_US
    pg3 = b["rec_ms"] <= GATE_RECOVER_MS
    print("warmup_ms (一次性) = %9.2f ms | 可摊销，不计入单次请求" % b["warmup_ms"])
    print("assign_ms (稳态)   = %9.4f ms | gate ≤ %5.0f ms | %s"
          % (b["assign_ms"], GATE_SPAWN_MS, "PASS" if pg1 else "FAIL"))
    print("rtt_us (稳态)      = %9.2f μs | gate ≤ %5.0f μs | %s"
          % (b["rtt_us"], GATE_RTT_US, "PASS" if pg2 else "FAIL"))
    print("崩溃时其余热worker仍服务 = %s" % b["still_serving"])
    print("recycle_ms (容量恢复) = %9.2f ms | gate ≤ %5.0f ms | %s"
          % (b["rec_ms"], GATE_RECOVER_MS, "PASS" if pg3 else "FAIL"))
    print("recycle 后 ok      = %s" % b["post_ok"])

    print("-" * 86)
    naive_pass = g1 and g2 and g3 and a["ok"]
    pool_pass = pg1 and pg2 and pg3 and b["still_serving"] and b["post_ok"]
    print("场景 A（朴素冷启动）: %s" % ("三闸门全过 ✅" if naive_pass else "spawn 略超闸门 ❌（需热池缓解）"))
    print("场景 B（热进程池）  : %s" % ("三闸门全过 ✅ 进程级隔离可行，可收口进 FabricHub" if pool_pass else "未过闸门 ❌"))
    print("结论: B 路线 %s（采用热进程池后完全可行）"
          % ("可行 ✅" if pool_pass else "需进一步缓解"))
    return 0 if pool_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
