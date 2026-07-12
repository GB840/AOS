"""build_default_kernel 的默认隔离接线：重型引擎应默认隔离进子进程。

验证默认配置下，FabricHub 把 _ISOLATED_BY_DEFAULT 里的引擎登记为 isolated
（子进程），而非进程内。用轻量 BenchRealAdapter 替代真实重型适配器，避免
18s 冷启动与网络依赖导致 flaky；验证的是「接线契约」而非具体引擎。

运行：AOS_ISO_TRANSPORT=tcp 下子进程走 tcp loopback（沙箱无 Named Pipe）。
"""
from __future__ import annotations

import os
import sys

REPO_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

import kernel.wiring as wiring  # noqa: E402

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
