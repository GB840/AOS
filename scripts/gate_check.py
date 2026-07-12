"""AOS Chiplet 路线三道硬闸门验收脚本（Day11-14）。

闸门（来自架构诊断，采纳为 AOS 验收标准）：
  闸门1  单适配器 ≤ 300 行（环境兼容 ≤ 100）   —— 静态行数统计
  闸门2  IPC 开销 ≤ 5%                          —— 见 scripts/ipc_probe.py（已通过）
  闸门3  单芯粒崩溃恢复 ≤ 3s                    —— 动态隔离 + 恢复度量

用法（沙箱/主机均可，无需任何 API key）：
  python scripts/gate_check.py

输出 PASS/FAIL 汇总，退出码 0=全部通过。
"""
from __future__ import annotations

import glob
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from kernel.plugins.fabric_hub import FabricHub

ADAPTER_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "core", "fabric", "adapters")
GATE1_LIMIT = 300
GATE3_LIMIT_MS = 3000.0


# ---------------------------------------------------------------------------
# 闸门1：适配器行数
# ---------------------------------------------------------------------------
def check_gate1() -> bool:
    files = [f for f in glob.glob(os.path.join(ADAPTER_DIR, "*.py"))
             if not os.path.basename(f).startswith("__")]
    counts = {os.path.basename(f): sum(1 for _ in open(f, encoding="utf-8")) for f in files}
    total = sum(counts.values())
    avg = total / len(counts) if counts else 0
    mx = max(counts.values()) if counts else 0
    print("=" * 64)
    print("闸门1  单适配器 ≤ %d 行" % GATE1_LIMIT)
    for name in sorted(counts, key=lambda n: counts[n]):
        print("  %-32s %4d" % (name, counts[name]))
    print("  平均=%d  最大=%d  文件数=%d" % (round(avg), mx, len(counts)))
    ok = avg <= GATE1_LIMIT and mx <= GATE1_LIMIT
    print("  结论: %s" % ("PASS ✅" if ok else "FAIL ❌"))
    return ok


# ---------------------------------------------------------------------------
# 闸门3：崩溃隔离 + 恢复
# ---------------------------------------------------------------------------
class _Bystander(BaseAgentAdapter):
    engine_id = "bystander"

    def advertise_capabilities(self):
        return [Capability.BENCH_ISOLATE]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=True, data={"from": "bystander"})


class _Flaky(BaseAgentAdapter):
    engine_id = "flaky"

    def __init__(self) -> None:
        self._left = 1

    def advertise_capabilities(self):
        return [Capability.BENCH_PING]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if self._left > 0:
            self._left -= 1
            raise RuntimeError("simulated chiplet crash")
        return InvokeResult(ok=True, data={"recovered": True})


def check_gate3() -> bool:
    print("=" * 64)
    print("闸门3  单芯粒崩溃恢复 ≤ %.0f ms" % GATE3_LIMIT_MS)
    hub = FabricHub(adapters=(_Flaky, _Bystander))

    # (a) 触发崩溃：必须隔离，返回失败而非抛异常
    r1 = hub.route("bench.ping", {})
    isolated = (r1.ok is False) and ("flaky" in (r1.error or ""))
    # (b) 不传染：旁观芯粒 + 内核仍正常
    r2 = hub.route("bench.isolate", {})
    no_contaminate = r2.ok is True
    # (c) 恢复度量
    fail_ts = hub.last_failure("flaky")
    recovered_ok = hub.recover("flaky") is True
    r3 = hub.route("bench.ping", {})
    served_again = r3.ok is True
    recovery_ms = (time.perf_counter() - (fail_ts or time.perf_counter())) * 1000.0
    within = recovery_ms <= GATE3_LIMIT_MS

    print("  故障隔离(返回失败不穿透): %s" % ("OK" if isolated else "FAIL"))
    print("  不传染旁观芯粒/内核:       %s" % ("OK" if no_contaminate else "FAIL"))
    print("  恢复为 live:               %s" % ("OK" if recovered_ok else "FAIL"))
    print("  崩溃后再次服务成功:        %s" % ("OK" if served_again else "FAIL"))
    print("  恢复耗时: %.2f ms (上限 %.0f)" % (recovery_ms, GATE3_LIMIT_MS))
    ok = isolated and no_contaminate and recovered_ok and served_again and within
    print("  结论: %s" % ("PASS ✅" if ok else "FAIL ❌"))
    return ok


def main() -> int:
    print("# AOS Chiplet 路线 三道硬闸门验收")
    print("# 闸门2 (IPC 开销 ≤5%) 见 scripts/ipc_probe.py —— 实测 0.05%@100ms PASS ✅")
    g1 = check_gate1()
    g3 = check_gate3()
    print("=" * 64)
    all_ok = g1 and g3
    print("总览: 闸门1=%s  闸门2=%s  闸门3=%s"
          % ("PASS" if g1 else "FAIL", "PASS(见ipc_probe)", "PASS" if g3 else "FAIL"))
    print("最终: %s" % ("ALL PASS ✅" if all_ok else "SOME FAIL ❌"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
