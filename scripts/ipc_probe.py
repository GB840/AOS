"""IPC 开销探测（Day 8-10 闸门）：测量「内核<->芯粒」这一跳的路由开销占比。

重要：Windows 的 time.sleep() 量化粒度约 1ms，无法精确模拟 20μs 的微秒级
延迟（sleep(20μs) 实际睡 ~1ms）。因此本脚本对「任务耗时」和「模拟路由延迟」
都用 busy-wait（perf_counter 轮询），保证微秒级精度。

测量三个量：
  1) direct      : 直接调适配器（绕开内核枢纽），纯任务耗时 = 基线无路由
  2) routed(sim) : 经 FabricHub.route()，内核这一跳 + 模拟 IPC 延迟 sim_us
  3) seam 开销   : routed(0) - direct  = 路线 A 真实的进程内路由固定成本
  4) ipc 开销    : (routed(20) - routed(0)) / routed(0) = 假设 20μs IPC 跳的开销占比

闸门（用户定义）：模拟 20μs 路由延迟下开销 ≤ 5% 即通过（即「低延迟互通」承诺成立）。

用法（仓库根目录 D:/AOS，系统 Python 3.14）：
    python scripts/ipc_probe.py
"""
from __future__ import annotations

import sys
import time
import statistics
from typing import Any, Dict, List

sys.path.insert(0, "D:/AOS/src")

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from kernel.plugins.fabric_hub import FabricHub

N_ITERS = 25
GATE_PCT = 5.0                       # 闸门：模拟 20μs 路由延迟开销 ≤ 5%
SIM_US_LIST = [0, 20, 100]           # 0=无模拟；20=Named Pipe 典型延迟；100=最坏容限
TASK_MS_LIST = [1.0, 10.0, 100.0]    # 轻任务 → LLM 调用级


def _busy(seconds: float) -> None:
    """忙等指定秒数（微秒级精度，避免 Windows sleep 量化成 ~1ms）。"""
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        pass


class _BenchPingAdapter(BaseAgentAdapter):
    """合成基准芯粒：invoke 只忙等 task_ms，模拟真实引擎任务耗时。"""
    @property
    def engine_id(self) -> str:
        return "bench_ping"

    def advertise_capabilities(self) -> List[Capability]:
        return [Capability.BENCH_PING]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        _busy(float(req.payload.get("task_ms", 1.0)) / 1000.0)
        return InvokeResult(ok=True, data={"slept_ms": req.payload.get("task_ms")})


def _direct(adapter: _BenchPingAdapter, task_ms: float) -> float:
    req = InvokeRequest(capability=Capability.BENCH_PING, payload={"task_ms": task_ms})
    samples = []
    for _ in range(N_ITERS):
        t0 = time.perf_counter()
        adapter.invoke(req)
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples) * 1000.0


def _routed(hub: FabricHub, task_ms: float, sim_us: float) -> float:
    hub.set_route_sim_us(sim_us)
    samples = []
    for _ in range(N_ITERS):
        t0 = time.perf_counter()
        hub.route("bench.ping", {"task_ms": task_ms})
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples) * 1000.0


def main() -> int:
    hub = FabricHub()
    adapter = _BenchPingAdapter()
    hub._registry.register(adapter)  # 仅基准用，不与真实引擎冲突

    print("=" * 92)
    print("IPC 开销探测 | 闸门: 模拟 20μs 路由延迟下开销 ≤ %.1f%%" % GATE_PCT)
    print("=" * 92)
    print("%-9s | %9s | %9s | %9s | %10s | %9s" %
          ("task_ms", "direct", "routed0", "seam_ov%", "ipc20_ov%", "gate20"))
    print("-" * 92)

    worst_ipc20 = 0.0
    for task_ms in TASK_MS_LIST:
        direct = _direct(adapter, task_ms)
        base = _routed(hub, task_ms, 0)
        s20 = _routed(hub, task_ms, 20)
        s100 = _routed(hub, task_ms, 100)
        seam_ov = (base - direct) / direct * 100.0 if direct else 0.0
        ipc20_ov = (s20 - base) / base * 100.0 if base else 0.0
        ipc100_ov = (s100 - base) / base * 100.0 if base else 0.0
        passed = ipc20_ov <= GATE_PCT
        worst_ipc20 = max(worst_ipc20, ipc20_ov)
        print("%-9.1f | %9.3f | %9.3f | %8.2f%% | %9.3f%% | %9s" %
              (task_ms, direct, base, seam_ov, ipc20_ov, "PASS" if passed else "FAIL"))
        # 同时把 100μs 最坏容限也打出来，但不参与闸门判定
        _ = ipc100_ov

    print("-" * 92)
    decision_pass = worst_ipc20 <= GATE_PCT
    print("20μs 模拟 IPC 跳的最大开销 = %.3f%%  ->  %s" %
          (worst_ipc20,
           "B 路线(进程隔离/Sidecar)的 IPC 假设成立" if decision_pass
           else "B 路线的 IPC 低开销假设存疑"))
    print("结论: IPC 开销闸门 %s (≤%.1f%%)" %
          ("通过 ✅" if decision_pass else "未通过 ❌", GATE_PCT))
    return 0 if decision_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
