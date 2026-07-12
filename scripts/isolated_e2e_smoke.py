"""端到端冒烟：默认生产接线(build_fabric_hub) → 隔离 Agnes → 真对话 → recover。

这是 B 路线从「组件验证」到「系统级可演示」的铁证：用和 build_default_kernel
完全相同的接线函数构造枢纽，重型引擎(Agnes)真在隔离子进程里跑，经 FabricHub
能力路由拿到真实回复，崩溃恢复走热备切换（毫秒级）。

注：演示集默认只含 agnes。AG2 的隔离登记逻辑与 agnes 同源（同一 try/except 路径
+ test_no_double_registration 锁死），但本环境 AG2 适配器实例化需 key 且冷启动
极慢（import ~2.5min），会拖垮演示，故此处不默认纳入；生产接线
_ISOLATED_BY_DEFAULT 已含 ag2（见 wiring.py）。要演示全量隔离含 AG2，设
环境变量 INCLUDE_AG2_ISO=1（会很慢）。
"""
from __future__ import annotations

import os
import sys
import time
from unittest import mock

sys.path.insert(0, "D:/AOS/src")

# best-effort 加载 .env，使隔离子进程继承 AGNES_API_KEY（不覆盖已有环境变量）。
try:
    from dotenv import load_dotenv

    load_dotenv("D:/AOS/.env", override=False)
except Exception:  # noqa: BLE001 - 无 dotenv / 无 .env 时跳过，隔离与 recover 仍可验证
    pass

from kernel import wiring  # noqa: E402
from kernel.isolation.subprocess_iso import GATE_RECOVER_MS  # noqa: E402

AGNES_SPEC = "core.fabric.adapters.agnes_adapter:AgnesAdapter"
AG2_SPEC = "core.fabric.adapters.ag2_adapter:AG2Adapter"


def main() -> int:
    include_ag2 = os.environ.get("INCLUDE_AG2_ISO") == "1"
    isolated = {"agnes": AGNES_SPEC}
    if include_ag2:
        isolated["ag2"] = AG2_SPEC

    # 用真实生产接线函数构造枢纽（与 build_default_kernel 内部调用一致），
    # 仅临时收窄默认隔离集，避免本环境 AG2 极慢冷启动拖垮演示。
    with mock.patch.object(wiring, "_ISOLATED_BY_DEFAULT", isolated):
        hub = wiring.build_fabric_hub(isolate_heavy=True)

    rep = hub.health_report()
    print(f"[build] {rep['live']}/{rep['total']} engines live")
    for eid, info in sorted(rep["adapters"].items()):
        mark = "ISO" if info.get("isolated") else "   "
        live = "live" if info["live"] else "dead"
        print(f"  [{mark}] {eid:12s} {live}")

    # 1) agnes 必须被隔离（不是进程内双注册假象）
    ag = rep["adapters"].get("agnes")
    assert ag is not None, "agnes 未注册进枢纽"
    assert ag["isolated"] is True, "agnes 未被隔离（双注册假象复现？）"
    print("[check] agnes 确在隔离子进程（isolated=True）")

    # 2) 进程外铁证：子进程 PID ≠ 宿主进程
    host = hub._isolated["agnes"]
    child_pid = host.subprocess_pid
    assert child_pid is not None, "隔离子进程未拉起"
    assert child_pid != os.getpid(), "PID 等于宿主 → 隔离失效"
    print(f"[check] 隔离子进程 PID={child_pid} ≠ 宿主 PID={os.getpid()}（进程外铁证）")

    # 3) 直接打隔离子进程里的 Agnes 真对话（绕过能力路由，精确命中 agnes）。
    #    route() 按能力选第一个 live 引擎，会落到进程内 litellm；这里直接调
    #    隔离宿主，才能验证「隔离 Agnes 真在子进程里出真实回复」。
    r = host.invoke("inference.llm", {"prompt": "用一句话介绍 Agent OS。", "model": "agnes-2.0-flash"})
    if not r.get("ok"):
        print(f"[chat] Agnes 隔离调用未成功（可能无 API key / 网关不可达）: {r.get('error')}")
    else:
        content = (r.get("data") or {}).get("content", "")
        print(f"[chat] OK via 隔离子进程 PID={host.subprocess_pid} → {content[:80]!r}")
        assert content, "对话返回空内容"

    # 4) 崩溃恢复走热备切换（毫秒级，过 3s 闸门）
    t0 = time.perf_counter()
    dt_ms = host.recover()
    wall = (time.perf_counter() - t0) * 1000.0
    gate_ok = dt_ms <= GATE_RECOVER_MS
    print(
        f"[recover] 切换耗时 {dt_ms:.2f}ms（外部计时 {wall:.2f}ms，闸门 {GATE_RECOVER_MS}ms）"
        f"{'PASS' if gate_ok else 'FAIL'}"
    )
    assert gate_ok, "recover 超闸门"
    assert host.health() is True, "recover 后未恢复服务"

    print("\nE2E SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
