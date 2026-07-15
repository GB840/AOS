"""视频类 MCP 集成测试（AOS 侧胶水，全离线、不依赖真实 ffmpeg / npm 包）。

真实 omni-video-mcp 需用户 Windows 主机装 ffmpeg + ELEVENLABS_API_KEY + Playwright；
真实 video-use 需 ffmpeg + yt-dlp + Node，沙箱跑不了。本测试用两路验证：

  1) test_mcp_stdio_adapter_maps_video_tools —— 用本地 mock stdio MCP server
     （tests/mock_video_mcp_server.py）经真实 MCPStdioAdapter 拉起子进程，验证
     stdio 传输、工具列举、按 capability_map 映射 media.video、tools/call 调用；
  2) test_register_video_mcps_derive_args —— mock 掉 MCPStdioAdapter（不真起
     进程），验证 FabricHub.register_omni_video_mcp / register_video_use_mcp
     从默认值/环境变量正确推导 engine_id 与 capability_map。
"""
import os
import sys

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter

_HERE = os.path.dirname(__file__)
_MOCK_SERVER = os.path.join(_HERE, "mock_video_mcp_server.py")


def test_mcp_stdio_adapter_maps_video_tools():
    cap_map = {
        "omni_video_ingest": "media.video",
        "omni_video_render": "media.video",
        "video_frames_extract": "media.video",
        "video_probe": "media.video",
    }
    adapter = MCPStdioAdapter(
        command=[sys.executable, _MOCK_SERVER],
        engine_id="video-mock",
        capability_map=cap_map,
        init_on_start=True,
        timeout=10.0,
    )
    try:
        caps = adapter.advertise_capabilities()
        assert Capability.MEDIA_VIDEO in caps

        res = adapter.invoke(InvokeRequest(
            capability=Capability.MEDIA_VIDEO,
            payload={"tool": "omni_video_render",
                     "arguments": {"edl": "cut.json", "lut": "film.cube"}},
        ))
        assert res.ok, res.error
        assert "MOCK[omni_video_render]" in res.data["text"]
        assert "cut.json" in res.data["text"]
    finally:
        adapter.shutdown()


def test_register_video_mcps_derive_args(monkeypatch):
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
                {"name": "omni_video_ingest"}, {"name": "omni_video_render"},
                {"name": "video_frames_extract"}, {"name": "video_probe"},
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
    for _v in ("OMNI_VIDEO_MCP_CMD", "OMNI_VIDEO_MCP_ENGINE_ID",
               "VIDEO_USE_MCP_CMD", "VIDEO_USE_MCP_ENGINE_ID"):
        monkeypatch.delenv(_v, raising=False)
    # 删 APPDATA：否则若主机全局装了 video-use.cmd，register 会探测到它并优先用
    # 该绝对路径（正确的运行时行为），使默认分支不再是 npx。测试要验证「派生逻辑」
    # 而非「主机装没装」，故强制走 npx 回落分支，与主机状态解耦。
    monkeypatch.delenv("APPDATA", raising=False)

    # omni-video 默认（无 env）：engine_id=omni-video，映射到 media.video
    FabricHub.register_omni_video_mcp(hub)
    assert captured["adapter"].engine_id == "omni-video"
    assert Capability.MEDIA_VIDEO in captured["adapter"].advertise_capabilities()
    assert captured["adapter"]._cap_map["omni_video_render"] == "media.video"
    assert "uv" in captured["adapter"].command[0] or "server.py" in captured["adapter"].command[-1]

    # omni-video 自定义命令经 env 生效
    captured.clear()
    monkeypatch.setenv(
        "OMNI_VIDEO_MCP_CMD",
        "uv run /d/AI_Model/omni-video-mcp/server.py",
    )
    monkeypatch.setenv("OMNI_VIDEO_MCP_ENGINE_ID", "ov-custom")
    FabricHub.register_omni_video_mcp(hub)
    assert captured["adapter"].engine_id == "ov-custom"
    assert captured["adapter"].command == ["uv", "run", "/d/AI_Model/omni-video-mcp/server.py"]

    # video-use 默认（无 env）：engine_id=video-use，映射到 media.video
    captured.clear()
    FabricHub.register_video_use_mcp(hub)
    assert captured["adapter"].engine_id == "video-use"
    assert Capability.MEDIA_VIDEO in captured["adapter"].advertise_capabilities()
    assert captured["adapter"]._cap_map["video_frames_extract"] == "media.video"
    assert captured["adapter"].command[:2] == ["npx", "-y"]

    # video-use 自定义命令经 env 生效
    captured.clear()
    monkeypatch.setenv("VIDEO_USE_MCP_CMD", "video-use --stdio")
    monkeypatch.setenv("VIDEO_USE_MCP_ENGINE_ID", "vu-custom")
    FabricHub.register_video_use_mcp(hub)
    assert captured["adapter"].engine_id == "vu-custom"
    assert captured["adapter"].command == ["video-use", "--stdio"]
