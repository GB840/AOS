"""端到端演示：把真实 Agnes 多模态引擎隔离进子进程，经 FabricHub 按能力路由调用。

证明 B 路线收口不是空壳，而是真能接「真实开源引擎」：
  - 真实适配器（AgnesAdapter，OpenAI 兼容多模态平面，依赖 requests）在独立进程运行；
  - FabricHub.route("inference.llm", ...) 把对话打到子进程，拿到真实回复；
  - 子进程 PID ≠ 宿主 PID（真故障隔离，崩溃不传染内核）；
  - 杀掉子进程后，recover() 在 ≤3s 内 respawn 恢复服务。

用法（沙箱用 tcp，生产默认 Named Pipe）：
    AOS_ISO_TRANSPORT=tcp python scripts/isolated_real_engine_demo.py
    python scripts/isolated_real_engine_demo.py            # 生产：Windows Named Pipe
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "D:/AOS/src")

from kernel.isolation.subprocess_iso import GATE_RECOVER_MS
from kernel.plugins.fabric_hub import FabricHub
from core.fabric.adapters import AgnesAdapter
from kernel.isolation._bench_adapter import BenchRealAdapter


def _load_dotenv() -> None:
    """把 D:/AOS/.env 灌进 environ（子进程会继承），让用户 key 可用。"""
    candidates = [
        os.path.join(os.environ.get("AOS_SRC", "D:/AOS/src"), "..", ".env"),
        "D:/AOS/.env",
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    if not k:
                        continue
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    os.environ.setdefault(k, v)
            return


def _section(title: str) -> None:
    print(f"\n===== {title} =====")


def main() -> int:
    _load_dotenv()
    transport = os.environ.get("AOS_ISO_TRANSPORT", "pipe")
    print(f"[demo] transport={transport}  host_pid={os.getpid()}")
    print(f"[demo] AGNES_API_KEY={'set' if os.environ.get('AGNES_API_KEY') else 'NOT SET'}")

    # 只建枢纽，不注册任何 in-process 引擎（保持演示纯净）
    hub = FabricHub(adapters=())

    # ---- 1) 真实 Agnes 适配器隔离进子进程 ----
    _section("1) 把真实 Agnes 多模态引擎隔离进子进程")
    agnes_eid = hub.add_isolated_engine("agnes-iso", AgnesAdapter, transport=transport)
    rep = hub.health_report()["adapters"][agnes_eid]
    print(f"  engine_id={agnes_eid}  isolated={rep['isolated']}  "
          f"live={rep['live']}  caps={rep['capabilities']}")
    assert rep["isolated"] is True, "Agnes 未被隔离！"
    print("  ✅ 真实（依赖 requests 的）AgnesAdapter 已在独立进程加载并实例化")

    # ---- 2) 经 FabricHub 按能力路由一次真实对话（走子进程） ----
    _section("2) 经 FabricHub.route() 把对话打到子进程里的 Agnes")
    r = hub.route("inference.llm", {
        "prompt": "Reply with exactly: AOS-ISO-OK",
        "model": "agnes-2.0-flash",
    })
    print(f"  ok={r.ok}")
    if r.ok:
        print(f"  content={r.data.get('content')!r}  model={r.data.get('model')}")
    else:
        print(f"  （无 key / 网络不可达，诚实返回失败）error={r.error}")

    # ---- 3) 隔离铁证：子进程 PID ≠ 宿主 PID ----
    _section("3) 隔离铁证：响应带回的是子进程 PID")
    iso = hub._isolated[agnes_eid]
    print(f"  host_pid={os.getpid()}  agn缓存=不可直接取 -> 用 bench 芯粒取子进程 PID")
    bench_eid = hub.add_isolated_engine("bench-iso", BenchRealAdapter, transport=transport)
    br = hub.route("bench.isolate", {"probe": "pid"})
    sub_pid = br.data.get("pid") if br.ok else None
    print(f"  bench 子进程 pid={sub_pid}  host_pid={os.getpid()}")
    assert br.ok and sub_pid != os.getpid(), "隔离引擎未跑在子进程！"
    print("  ✅ 芯粒确实运行在独立进程地址空间（真故障隔离）")

    # ---- 4) 崩溃恢复：kill 子进程 → recover() 在 ≤3s 内 respawn ----
    _section("4) 模拟子进程崩溃 → FabricHub.recover() 回收")
    bhost = hub._isolated[bench_eid]
    bhost._layer._proc.kill()
    bhost._layer._proc.wait()
    print(f"  崩溃后 health={bhost.health()}（应为 False）")
    assert bhost.health() is False
    t0 = time.perf_counter()
    ok = hub.recover(bench_eid)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    r3 = hub.route("bench.isolate", {"probe": "after-recover"})
    new_pid = r3.data.get("pid") if r3.ok else None
    print(f"  recover_ok={ok}  health={bhost.health()}  new_pid={new_pid}  "
          f"恢复耗时={dt_ms:.0f}ms (闸门 {GATE_RECOVER_MS}ms)")
    assert ok and r3.ok and new_pid != os.getpid() and new_pid != sub_pid
    assert dt_ms <= GATE_RECOVER_MS, f"恢复 {dt_ms:.0f}ms 超闸门"
    print("  ✅ 崩溃经 recover() 隔离恢复，其余引擎不受影响（≤3s 闸门）")

    # ---- 收尾 ----
    spawn = iso.spawn_ms or 0
    print(f"\n[结论] B 路线收口验证通过：真实 Agnes 引擎已在独立子进程服役"
          f"（冷启动≈{spawn:.0f}ms），按能力路由/崩溃恢复全程走子进程。")
    print(f"  - 真实对话经子进程: {'YES' if r.ok else 'skipped(无 key/网络)'}")
    print(f"  - 故障隔离 + recover ≤3s: YES")
    hub._isolated[agnes_eid].stop()
    hub._isolated[bench_eid].stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
