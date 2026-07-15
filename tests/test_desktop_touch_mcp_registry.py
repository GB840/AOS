"""Desktop-Touch-MCP 集成测试（AOS 侧胶水，全离线、不依赖真实 npx / 桌面）。

真实 Desktop-Touch-MCP 需用户 Windows 主机装 Node + 授权辅助功能，沙箱跑不了；
本测试用两路验证：
  1) test_mcp_stdio_adapter_maps_desktop_tools —— 用本地 mock stdio MCP server
     （tests/mock_stdio_mcp_server.py）经真实 MCPStdioAdapter 拉起子进程，验证
     stdio 传输、工具列举、按 capability_map 映射 action.aci、tools/call 调用；
  2) test_register_desktop_touch_mcp_derives_args —— 镜像 WeKnora 测试，mock 掉
     MCPStdioAdapter（不真起 npx），验证 FabricHub.register_desktop_touch_mcp
     从默认值/环境变量正确推导 engine_id 与 capability_map。
"""
import os
import sys

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter

_HERE = os.path.dirname(__file__)
_MOCK_SERVER = os.path.join(_HERE, "mock_stdio_mcp_server.py")


def test_mcp_stdio_adapter_maps_desktop_tools():
    cap_map = {
        "desktop_discover": "action.aci",
        "desktop_act": "action.aci",
        "screenshot": "action.aci",
    }
    adapter = MCPStdioAdapter(
        command=[sys.executable, _MOCK_SERVER],
        engine_id="desktop-touch",
        capability_map=cap_map,
        init_on_start=True,
        timeout=10.0,
    )
    try:
        caps = adapter.advertise_capabilities()
        assert Capability.ACI in caps

        res = adapter.invoke(InvokeRequest(
            capability=Capability.ACI,
            payload={"tool": "desktop_act",
                     "arguments": {"target": "开始菜单", "action": "click"}},
        ))
        assert res.ok, res.error
        assert "MOCK[desktop_act]" in res.data["text"]
        assert "开始菜单" in res.data["text"]
    finally:
        adapter.shutdown()


def test_register_desktop_touch_mcp_derives_args(monkeypatch):
    try:
        from kernel.plugins.fabric_hub import FabricHub
    except Exception as e:  # noqa: BLE001 - 沙箱若拉不起完整 fabric_hub 则跳过（不谎报）
        pytest.skip(f"FabricHub 导入受限(沙箱)，跳过: {e}")

    import core.fabric.adapters.mcp_stdio_adapter as _mod

    class _FakeAdapter:
        def __init__(self, command, engine_id, capability_map=None, timeout=30.0, **kw):
            self.command = list(command)
            self._engine_id = engine_id
            self._cap_map = capability_map or {}
            self._tools = [
                {"name": "desktop_discover"}, {"name": "desktop_act"},
                {"name": "screenshot"}, {"name": "mouse_click"},
            ]

        @property
        def engine_id(self):
            return self._engine_id

        def advertise_capabilities(self):
            caps = set()
            for t in self._tools:
                m = self._cap_map.get(t["name"])
                caps.add(Capability(m) if m else Capability.TOOL_USE)
            return list(caps)

    monkeypatch.setattr(_mod, "MCPStdioAdapter", _FakeAdapter)

    captured = {}

    class _FakeReg:
        def register(self, adapter):
            captured["adapter"] = adapter
            return True

    hub = type("H", (), {"_registry": _FakeReg()})()

    # 清掉可能存在的 .env 注入变量，确保默认分支断言稳定（环境隔离）
    monkeypatch.delenv("DESKTOP_TOUCH_MCP_CMD", raising=False)
    monkeypatch.delenv("DESKTOP_TOUCH_MCP_ENGINE_ID", raising=False)

    # 默认（无 env）：engine_id=desktop-touch，映射到 action.aci
    FabricHub.register_desktop_touch_mcp(hub)
    assert captured["adapter"].engine_id == "desktop-touch"
    assert Capability.ACI in captured["adapter"].advertise_capabilities()
    assert captured["adapter"]._cap_map["desktop_act"] == "action.aci"
    assert "npx" in captured["adapter"].command[0] or "-y" in captured["adapter"].command

    # 自定义命令经 env 生效
    captured.clear()
    monkeypatch.setenv(
        "DESKTOP_TOUCH_MCP_CMD",
        "node D:/tools/desktop-touch-mcp/dist/index.js",
    )
    monkeypatch.setenv("DESKTOP_TOUCH_MCP_ENGINE_ID", "dt-custom")
    FabricHub.register_desktop_touch_mcp(hub)
    assert captured["adapter"].engine_id == "dt-custom"
    assert captured["adapter"].command == ["node", "D:/tools/desktop-touch-mcp/dist/index.js"]
