"""build_default_kernel 的默认隔离接线：重型引擎应默认隔离进子进程。

验证默认配置下，FabricHub 把 _ISOLATED_BY_DEFAULT 里的引擎登记为 isolated
（子进程），而非进程内。用轻量 BenchRealAdapter 替代真实重型适配器，避免
18s 冷启动与网络依赖导致 flaky；验证的是「接线契约」而非具体引擎。

传输：隔离层会自动探测 Named Pipe 可用性，不可用时透明退 tcp，故无需手动
设 AOS_ISO_TRANSPORT（沙箱 / 部分 pwsh 主机均可直接跑通）。
"""
from __future__ import annotations

import os
import sys

REPO_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

import kernel.wiring as wiring  # noqa: E402
from kernel.isolation._bench_adapter import BenchRealAdapter  # noqa: E402
from kernel.plugins.fabric_hub import (  # noqa: E402
    FabricHub,
    IsolatedAdapterProxy,
)

BENCH_SPEC = "kernel.isolation._bench_adapter:BenchRealAdapter"


def test_build_fabric_hub_isolates_configured_engines(monkeypatch):
    """默认 isolate_heavy=True 时，配置的重型引擎应登记为 isolated 且能起来。"""
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})
    hub = wiring.build_fabric_hub(isolate_heavy=True)
    rep = hub.health_report()
    assert rep["adapters"]["bench"]["isolated"] is True, \
        "默认隔离应把 bench 登记为 isolated（子进程），而非进程内"
    # 轻量 bench 子进程应能起来并 live
    assert rep["adapters"]["bench"]["live"] is True


def test_build_fabric_hub_isolate_heavy_false_no_isolation(monkeypatch):
    """isolate_heavy=False 时，不应有任何引擎被隔离。"""
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})
    hub = wiring.build_fabric_hub(isolate_heavy=False)
    rep = hub.health_report()
    for info in rep["adapters"].values():
        assert info["isolated"] is False
    assert "bench" not in rep["adapters"]


def test_build_default_kernel_wires_isolation(monkeypatch):
    """build_default_kernel 真的把默认隔离接进了枢纽（且隔离 Agnes 类引擎）。

    用轻量 bench 替换默认 Agnes 配置，避免 18s 冷启动；并 stub get_brain，
    避免沙箱里 UnifiedBrain 重型初始化阻塞。其余内核构建照常（均有 try/except 兜底）。
    """
    import core  # build_default_kernel 内部 `from core import get_brain`
    monkeypatch.setattr(
        core, "get_brain",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no brain in test")),
    )
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})

    kernel = wiring.build_default_kernel(isolate_heavy=True)
    hub = kernel.fabric_hub
    rep = hub.health_report()
    assert rep["adapters"]["bench"]["isolated"] is True


def test_no_double_registration_when_engine_in_both_sets(monkeypatch):
    """复现真实冲突：某引擎既在默认进程内集合，又在隔离集合。

    验证 build_fabric_hub 不会把它注册成「进程内 + 隔离」两份（旧实现靠同名
    engine_id 覆盖，隔离是否生效全看注册顺序，极易静默失效）。修复后：构建时
    就从默认集合排除待隔离引擎，注册表里该 eid 只有隔离代理、无进程内副本。
    """
    # 让默认集合包含 bench（模拟"既在默认又在隔离"），并把它列入隔离。
    monkeypatch.setattr(
        FabricHub, "DEFAULT_ADAPTERS", (BenchRealAdapter,),
    )
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})

    hub = wiring.build_fabric_hub(isolate_heavy=True)
    eids = [e for e in hub._registry._adapters if e == "bench"]
    assert len(eids) == 1, f"bench 不应双注册，实际条目: {eids}"
    assert isinstance(hub._registry._adapters["bench"], IsolatedAdapterProxy), \
        "bench 应只以隔离代理注册，而非进程内实例"


def test_isolated_engine_exposes_subprocess_pid(monkeypatch):
    """隔离引擎必须真在另一个进程：subprocess_pid 非 None 且 ≠ 宿主 PID。

    这是「进程外铁证」的自动锁死——防止某天隔离退化为进程内却仍报 isolated=True。
    """
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})
    hub = wiring.build_fabric_hub(isolate_heavy=True)
    host = hub._isolated["bench"]
    pid = host.subprocess_pid
    assert pid is not None, "隔离引擎子进程未拉起，subprocess_pid 应为非 None"
    assert pid != os.getpid(), "subprocess_pid 等于宿主 PID → 隔离失效（没真进子进程）"


def test_health_report_exposes_isolation_details(monkeypatch):
    """health_report 对隔离引擎应含可观测块：PID / 热备就绪 / 三闸门数字。

    这是 B 路线生产可观测的落点——运维看报告能判断隔离引擎「健康到什么程度」，
    而非仅知道 isolated=True。
    """
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})
    hub = wiring.build_fabric_hub(isolate_heavy=True)
    iso = hub.health_report()["adapters"]["bench"].get("isolation")
    assert iso is not None, "隔离引擎 health_report 应含 isolation 可观测块"
    assert iso["subprocess_pid"] is not None
    assert iso["standby_ready"] is True, "默认开启热备，standby_ready 应为 True"
    assert iso["spawn_ms"] is not None and iso["spawn_ms"] > 0
    # isolation_summary() 应返回同一份同源快照
    assert hub.isolation_summary()["bench"]["subprocess_pid"] == iso["subprocess_pid"]


def test_recover_records_recovery_time(monkeypatch):
    """recover 隔离引擎后应记录恢复耗时（热备切换毫秒级），并在报告里可见。

    锁死「恢复耗时被记录且过 3s 闸门」——防止热备切换退化成冷启动却无人知晓。
    """
    monkeypatch.setattr(wiring, "_ISOLATED_BY_DEFAULT", {"bench": BENCH_SPEC})
    hub = wiring.build_fabric_hub(isolate_heavy=True)
    ok = hub.recover("bench")
    assert ok is True
    iso = hub.health_report()["adapters"]["bench"]["isolation"]
    assert iso["last_recover_ms"] is not None, "recover 后应记录恢复耗时"
    assert iso["last_recover_ms"] <= 3000.0, "恢复耗时超 3s 闸门"
    # 热备提拔 + 后台补位，主进程应已恢复 live
    assert hub.health_report()["adapters"]["bench"]["live"] is True
