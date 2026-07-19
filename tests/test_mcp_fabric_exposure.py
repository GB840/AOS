"""MCP 暴露 FabricHub 的能力路由：注册存在性 + handler 透传逻辑（mock hub）。

快测：不 build 真实 FabricHub（避免 spawn 重型 agnes/ag2 子进程），
用 mock 锁死 3 个 aos_* 工具的注册与 handler 对 InvokeResult 的透传。
真实 build + 子进程 spawn 由 scripts/mcp_stdio_smoke.py 真机验证。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import patch, MagicMock

from aos_mcp.protocol import MCPProtocol, MCPMessage


def _new_proto() -> MCPProtocol:
    """模拟已 initialize 的 client（真实 MCP 流程 client 先 initialize）。"""
    p = MCPProtocol()
    p.initialized = True
    return p


def _call(proto: MCPProtocol, name: str, args: dict) -> dict:
    msg = MCPMessage(id="x", method="tools/call",
                     params={"name": name, "arguments": args})
    return proto.handle_message(msg).to_dict().get("result", {})


def test_aos_tools_registered():
    proto = _new_proto()
    resp = proto.handle_message(
        MCPMessage(id="1", method="tools/list", params={})).to_dict()
    tools = [t["name"] for t in resp["result"]["tools"]]
    for need in ("aos_list_engines", "aos_route", "aos_invoke_engine"):
        assert need in tools, f"tools/list 缺少 {need}"


def test_aos_route_handler_translates_invokeresult():
    fake = MagicMock()
    fake.route.return_value = MagicMock(ok=True, data={"reply": "hi"}, error=None)
    with patch("aos_mcp.protocol._get_hub", return_value=fake):
        proto = _new_proto()
        res = _call(proto, "aos_route",
                    {"capability": "inference.llm", "payload": {"x": 1}})
    assert res["isError"] is False
    content = json.loads(res["content"][0]["text"])
    assert content["ok"] is True and content["data"] == {"reply": "hi"}
    fake.route.assert_called_once()


def test_aos_route_missing_capability():
    fake = MagicMock()
    with patch("aos_mcp.protocol._get_hub", return_value=fake):
        proto = _new_proto()
        res = _call(proto, "aos_route", {})
    content = json.loads(res["content"][0]["text"])
    assert content["ok"] is False and "capability" in content["error"]
    fake.route.assert_not_called()


def test_aos_list_engines_handler():
    fake = MagicMock()
    fake.health_report.return_value = {"total": 3, "live": 2, "adapters": {}}
    with patch("aos_mcp.protocol._get_hub", return_value=fake):
        proto = _new_proto()
        res = _call(proto, "aos_list_engines", {})
    content = json.loads(res["content"][0]["text"])
    assert content["total"] == 3 and content["live"] == 2


def test_aos_invoke_engine_handler():
    fake = MagicMock()
    fake.invoke_engine.return_value = MagicMock(ok=True, data={"out": 1}, error=None)
    with patch("aos_mcp.protocol._get_hub", return_value=fake):
        proto = _new_proto()
        res = _call(proto, "aos_invoke_engine",
                    {"engine_id": "agnes", "capability": "inference.llm"})
    content = json.loads(res["content"][0]["text"])
    assert content["ok"] is True and content["data"] == {"out": 1}
    fake.invoke_engine.assert_called_once_with("agnes", "inference.llm", {})


def test_aos_invoke_engine_missing_id():
    fake = MagicMock()
    with patch("aos_mcp.protocol._get_hub", return_value=fake):
        proto = _new_proto()
        res = _call(proto, "aos_invoke_engine", {})
    content = json.loads(res["content"][0]["text"])
    assert content["ok"] is False and "engine_id" in content["error"]
    fake.invoke_engine.assert_not_called()
