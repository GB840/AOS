"""FabricHub 真实通电自检测试（MASTER_PLAN 阶段 1.2）。

不依赖具体环境是否通电：只验证「诚实」这一核心不变量——
resolve_engine 绝不返回未通电的引擎；dead 引擎如实写出；无 live 提供者时
优雅失败（带原因，不静默）。
"""
from __future__ import annotations

import sys

from kernel.kernel import AOSKernel
from kernel.plugins.fabric_hub import FabricHub

_KNOWN_CAPS = (
    "inference.llm",
    "system.observability",
    "memory.semantic",
    "group.orchestration",
    "action.aci",
    "channel.access",
    "media.image",
    "media.video",
)
_EXPECTED_ENGINES = {
    "openclaw",
    "ag2",
    "litellm",
    "mem0",
    "browser-use",
    "langfuse",
    "duckduckgo",
    "agnes",
}


def test_registers_all_six_and_reports_total():
    hub = FabricHub()
    rep = hub.health_report()
    assert rep["total"] == 8
    assert set(rep["adapters"].keys()) == _EXPECTED_ENGINES
    # health_report 的字段是条件性的：核心字段恒在，隔离引擎额外带 isolation，
    # 支持 health_detail 的适配器额外带 health_detail。只校验「核心必在 + 无未知字段」。
    _CORE = {"live", "capabilities", "error", "isolated"}
    _OPTIONAL = {"isolation", "health_detail"}
    for info in rep["adapters"].values():
        assert _CORE <= set(info.keys())
        assert set(info.keys()) <= (_CORE | _OPTIONAL)


def test_resolve_never_returns_dead_engine():
    """核心诚实不变量：返回的引擎一定 live；绝不谎报。"""
    hub = FabricHub()
    rep = hub.health_report()
    for cap in _KNOWN_CAPS:
        eng = hub.resolve_engine(cap)
        if eng is None:
            continue
        assert eng in rep["adapters"]
        assert rep["adapters"][eng]["live"] is True


def test_route_to_unpowered_capability_fails_gracefully():
    hub = FabricHub()
    res = hub.route("memory.semantic", {"prompt": "x"})
    assert hasattr(res, "ok")
    if not res.ok:
        # 失败必须给出原因，绝不静默回退假装成功
        assert res.error


def test_hub_import_does_not_pull_brain():
    """内核零依赖接缝不被破坏：构造 Hub 不应拉起重型 brain 栈。"""
    before = set(sys.modules)
    FabricHub()
    pulled = set(sys.modules) - before
    assert "core.brain" not in pulled


def test_kernel_delegates_resolve_engine_to_hub():
    """内核级单一可信源：resolve_engine / fabric_health 正确委派给 Hub。"""
    k = AOSKernel()
    assert k.resolve_engine("inference.llm") is None  # 尚未登记枢纽
    assert k.fabric_health() is None

    k.set_fabric_hub(FabricHub())
    rep = k.fabric_health()
    assert rep is not None and rep["total"] == 8

    hub = k.fabric_hub
    for cap in _KNOWN_CAPS:
        assert k.resolve_engine(cap) == hub.resolve_engine(cap)
