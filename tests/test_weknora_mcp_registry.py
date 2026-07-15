"""WeKnora MCP 集成测试（AOS 侧胶水，用 mock MCP server 验证，不依赖真实 WeKnora/Docker）。

真实 WeKnora 需用户主机 Docker 部署 + 起 http 模式 MCP Server，沙箱跑不了；
本测试用标准库 http.server 起一个最小 MCP(JSON-RPC) 服务端，验证：
  1) MCPClientAdapter 能连、能列工具、能按 capability_map 映射能力、能调用工具；
  2) FabricHub.register_weknora_mcp 能从环境变量/默认值正确推导注册参数。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters.mcp_client_adapter import MCPClientAdapter


class _MockWeKnoraHandler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静默
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            msg = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send({"jsonrpc": "2.0", "id": None, "error": {"message": "bad json"}})
            return
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            self._send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "serverInfo": {"name": "mock-weknora", "version": "0"},
            }})
        elif method == "notifications/initialized":
            self._send({"jsonrpc": "2.0", "id": None, "result": None})
        elif method == "tools/list":
            self._send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": "hybrid_search", "description": "hybrid search", "inputSchema": {}},
                {"name": "chat", "description": "rag chat", "inputSchema": {}},
                {"name": "agent_chat", "description": "react agent", "inputSchema": {}},
            ]}})
        elif method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            self._send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text",
                             "text": f"MOCK[{name}]:{json.dumps(args, ensure_ascii=False)}"}],
                "isError": False,
            }})
        else:
            self._send({"jsonrpc": "2.0", "id": mid, "error": {"message": f"unknown {method}"}})


@pytest.fixture
def mock_weknora():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockWeKnoraHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}/mcp"
    server.shutdown()


def test_mcp_client_adapter_maps_weknora_tools(mock_weknora):
    cap_map = {
        "hybrid_search": "data.query",
        "chat": "memory.knowledge",
        "agent_chat": "cognition.reasoning",
    }
    adapter = MCPClientAdapter(server_url=mock_weknora, engine_id="weknora", capability_map=cap_map)
    caps = adapter.advertise_capabilities()
    assert Capability.DATA_QUERY in caps
    assert Capability.MEMORY_KNOWLEDGE in caps
    assert Capability.REASONING in caps

    res = adapter.invoke(InvokeRequest(capability=Capability.DATA_QUERY, payload={"query": "年假流程"}))
    assert res.ok, res.error
    assert "MOCK[hybrid_search]" in res.data["text"]
    assert "年假流程" in res.data["text"]


def test_register_weknora_mcp_derives_args(mock_weknora, monkeypatch):
    try:
        from kernel.plugins.fabric_hub import FabricHub
    except Exception as e:  # noqa: BLE001 - 沙箱若拉不起完整 fabric_hub 则跳过（不谎报）
        pytest.skip(f"FabricHub 导入受限(沙箱)，跳过: {e}")

    captured = {}
    def fake_register(server_url=None, engine_id=None, capability_map=None,
                      auth_token=None, timeout=10.0):
        captured.update(dict(server_url=server_url, engine_id=engine_id,
                              capability_map=capability_map, auth_token=auth_token,
                              timeout=timeout))
        return engine_id or "weknora"

    hub = type("H", (), {"register_mcp_server": staticmethod(fake_register)})()
    monkeypatch.setenv("WEKNORA_MCP_URL", mock_weknora)
    monkeypatch.setenv("WEKNORA_MCP_AUTH_TOKEN", "secret-xyz")
    # 调用真实的 FabricHub.register_weknora_mcp（unbound，注入 fake hub）
    FabricHub.register_weknora_mcp(hub)
    assert captured["server_url"] == mock_weknora
    assert captured["engine_id"] == "weknora"
    assert captured["auth_token"] == "secret-xyz"
    assert captured["capability_map"]["hybrid_search"] == "data.query"
    assert captured["capability_map"]["agent_chat"] == "cognition.reasoning"
