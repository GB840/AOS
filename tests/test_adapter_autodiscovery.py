"""FabricHub 适配器注册的开闭原则守门测试。

背景（审查报告 #10，核实为真）：
``fabric_hub.py`` 顶部硬编码 28 个适配器 import + 28 行注册列表。新增一个引擎
必须改枢纽文件 —— 对扩展不开放、对修改不封闭。更实际的痛点是"写完适配器忘了
去枢纽登记"，代码在仓库里躺着但永远不会被加载，谁也不知道。

修复方式（增量、不推倒重来）：
- 显式列表保留 —— 注册顺序即能力路由优先级，有语义，不能交给字典序；
- 新增 ``discover_auto_adapters()``：适配器类声明 ``AUTO_REGISTER = True``
  即被自动收录，不必再碰枢纽；
- 本测试守住"遗漏"：包里导出的每个适配器，要么被显式注册，要么 opt-in
  自动注册，要么写进下面这份带理由的豁免清单。新写的适配器必须表态。

诚实分级：② 级（代码 + 单测实证）。
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import BaseAgentAdapter  # noqa: E402
import core.fabric.adapters as adapters_pkg  # noqa: E402
from kernel.plugins import fabric_hub  # noqa: E402


# 明确"不默认上线"的适配器 —— 每条都必须有理由，不接受"先放着"。
_INTENTIONALLY_UNREGISTERED = {
    "EchoAdapter": "测试桩：默认注册会让它参与真实路由竞争",
    "MCPClientAdapter": "须先 register_mcp_server 配好服务器地址才有意义",
    "MCPStdioAdapter": "同上，stdio 传输需显式配置子进程命令",
    "IdaProMcpAdapter": "由 FabricHub.register_ida_pro_mcp() 按需装配（需本机装 IDA Pro + MCP 地址）",
    "CastAdapter": "按需装配，由上层业务显式 register_adapter 注入",
    "ContentMarketerAdapter": "内容营销角色，由 register_content_director 按需装配",
    "RefineAdapter": "精修链路组件，由业务侧显式装配",
    "RefineryAdapter": "精修链路组件，由业务侧显式装配",
}


def _exported_adapter_classes() -> dict[str, type]:
    names = getattr(adapters_pkg, "__all__", None) or dir(adapters_pkg)
    out = {}
    for n in names:
        o = getattr(adapters_pkg, n, None)
        if isinstance(o, type) and issubclass(o, BaseAgentAdapter) and o is not BaseAgentAdapter:
            out[n] = o
    return out


def test_package_exports_adapters():
    assert len(_exported_adapter_classes()) >= 20, "适配器扫描逻辑可能失效"


def test_every_exported_adapter_is_registered_or_explicitly_exempt():
    """新写的适配器不能悄悄躺在仓库里没人加载。"""
    registered = {c.__name__ for c in fabric_hub._ADAPTERS}
    orphans = []
    for name, cls in _exported_adapter_classes().items():
        if name in registered:
            continue
        if getattr(cls, "AUTO_REGISTER", False) is True:
            continue  # opt-in 自动注册（若被 exclude 掉说明已在显式列表里）
        if name in _INTENTIONALLY_UNREGISTERED:
            continue
        orphans.append(name)

    assert not orphans, (
        "以下适配器已导出但既未注册、也未 opt-in、也不在豁免清单里 —— "
        "它们永远不会被加载：\n  " + "\n  ".join(orphans)
        + "\n处理方式：加 AUTO_REGISTER = True 自动注册，"
          "或写进 tests 里的 _INTENTIONALLY_UNREGISTERED 并注明理由。"
    )


def test_explicit_order_is_preserved():
    """显式列表的顺序＝路由优先级，自动发现只能追加在后面，不得插队。"""
    explicit = list(fabric_hub._EXPLICIT_ADAPTERS)
    final = list(fabric_hub._ADAPTERS)
    assert final[: len(explicit)] == explicit, "自动发现破坏了显式注册顺序"


def test_autodiscovery_is_opt_in_only():
    """没声明 AUTO_REGISTER 的适配器不会被自动拉进来（测试桩不得默认上线）。"""
    auto = fabric_hub.discover_auto_adapters(exclude=fabric_hub._EXPLICIT_ADAPTERS)
    for cls in auto:
        assert getattr(cls, "AUTO_REGISTER", False) is True, (
            f"{cls.__name__} 未声明 AUTO_REGISTER 却被自动注册"
        )
    assert "EchoAdapter" not in {c.__name__ for c in auto}, "测试桩被自动上线了"


def test_autodiscovery_excludes_already_registered():
    """已在显式列表里的不会被重复追加。"""
    auto = fabric_hub.discover_auto_adapters(exclude=fabric_hub._EXPLICIT_ADAPTERS)
    assert not (set(auto) & set(fabric_hub._EXPLICIT_ADAPTERS)), "出现重复注册"
    names = [c.__name__ for c in fabric_hub._ADAPTERS]
    assert len(names) == len(set(names)), f"注册表存在同名重复: {names}"


def test_autodiscovery_result_is_stable():
    """同样输入必须给同样顺序，否则每次启动路由行为会漂移。"""
    a = fabric_hub.discover_auto_adapters(exclude=fabric_hub._EXPLICIT_ADAPTERS)
    b = fabric_hub.discover_auto_adapters(exclude=fabric_hub._EXPLICIT_ADAPTERS)
    assert a == b
    assert list(a) == sorted(a, key=lambda c: c.__name__)


def test_autodiscovery_survives_broken_package(monkeypatch):
    """包导入炸了也只能少注册，不能让整个枢纽起不来。"""
    import builtins
    real_import = builtins.__import__

    def boom(name, *a, **k):
        if name == "core.fabric.adapters":
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    monkeypatch.delitem(sys.modules, "core.fabric.adapters", raising=False)
    monkeypatch.setattr(builtins, "__import__", boom)
    assert fabric_hub.discover_auto_adapters() == ()


@pytest.mark.parametrize("name,reason", sorted(_INTENTIONALLY_UNREGISTERED.items()))
def test_exempt_list_has_no_stale_entries(name, reason):
    """豁免清单不能留僵尸条目：适配器已删掉就该同步清理。"""
    assert reason.strip(), f"{name} 的豁免理由为空"
    assert name in _exported_adapter_classes(), (
        f"{name} 已不在适配器包中，请从豁免清单删除"
    )
