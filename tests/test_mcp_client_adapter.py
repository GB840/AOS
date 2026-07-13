"""通用 MCP 客户端芯粒的本地真验证。

不依赖外网：起一个本地 ThreadingHTTPServer 实现最小 MCP（initialize /
tools/list / tools/call），验证适配器能真实发现工具、按 capability_map 映射
能力、并经 tools/call 取回结果。这等价于把 AnySearch / ExploreYC 这类真实
MCP Server 接进 AOS 的端到端行为。
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.adapters.mcp_client_adapter import MCPClientAdapter
from core.fabric.capability import Capability


class _MockMCPHandler(BaseHTTPRequestHandler):
    """最小 MCP Server：按 JSON-RPC method 派发。"""

    def _send(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - httpserver 约定
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        method = req.get("method", "")
        msg_id = req.get("id")
        if method == "initialize":
            self._send({"jsonrpc": "2.0", "id": msg_id,
                        "result": {"protocolVersion": "2025-06-18",
                                   "capabilities": {},
                                   "serverInfo": {"name": "mock", "version": "0"}}})
        elif method == "notifications/initialized":
            self._send({})  # 通知：空响应即可（无 id / 无 result）
        elif method == "tools/list":
            self._send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [
                {"name": "search_companies",
                 "description": "查 YC 公司", "inputSchema": {"type": "object"}},
                {"name": "ping",
                 "description": "通用工具", "inputSchema": {"type": "object"}},
            ]}})
        elif method == "tools/call":
            name = req.get("params", {}).get("name")
            args = req.get("params", {}).get("arguments", {})
            text = f"called {name} with {args}"
            self._send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}})
        else:
            self._send({"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32601, "message": "method not found"}})

    def log_message(self, *args: Any) -> None:  # 静默
        pass


def _start_server() -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockMCPHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def test_mcp_adapter_discovers_and_maps_capabilities():
    server, port = _start_server()
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        # search_companies -> data.query；其余默认 tool_use
        adapter = MCPClientAdapter(
            url, engine_id="mcp-test",
            capability_map={"search_companies": Capability.DATA_QUERY},
        )
        caps = adapter.advertise_capabilities()
        assert Capability.DATA_QUERY in caps
        assert Capability.TOOL_USE in caps
        assert adapter.health() is True
    finally:
        server.shutdown()


def test_mcp_adapter_invokes_mapped_tool():
    server, port = _start_server()
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        adapter = MCPClientAdapter(
            url, engine_id="mcp-test",
            capability_map={"search_companies": Capability.DATA_QUERY},
        )
        res = adapter.invoke(InvokeRequest(
            capability=Capability.DATA_QUERY,
            payload={"query": "YC 2024 AI"},
        ))
        assert res.ok is True
        assert "search_companies" in res.data["text"]
        assert "YC 2024 AI" in res.data["text"]
    finally:
        server.shutdown()


def test_mcp_adapter_unmapped_capability_fails_honestly():
    server, port = _start_server()
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        # 不映射任何 tool，所有 tool 默认 tool_use；WEB_SEARCH 无映射 -> 应失败
        adapter = MCPClientAdapter(url, engine_id="mcp-test")
        res = adapter.invoke(InvokeRequest(
            capability=Capability.WEB_SEARCH, payload={"query": "x"}))
        assert res.ok is False
        assert "无 tool 映射" in res.error
    finally:
        server.shutdown()


# ---- FabricHub.register_mcp_server 不崩溃契约 -------------------------
def test_fabric_hub_register_mcp_bad_url_is_safe():
    """坏 URL 不应抛、不应拖垮枢纽，返回 None 并记错误。"""
    from kernel.plugins.fabric_hub import FabricHub
    hub = FabricHub(adapters=())  # 空枢纽，只测 MCP 注册路径
    eid = hub.register_mcp_server("http://127.0.0.1:1/mcp", engine_id="mcp-dead", timeout=2.0)
    assert eid is None
    assert any(k.startswith("mcp:") for k in hub._errors)


def test_fabric_hub_register_mcp_live_server():
    server, port = _start_server()
    try:
        from kernel.plugins.fabric_hub import FabricHub
        hub = FabricHub(adapters=())
        eid = hub.register_mcp_server(
            f"http://127.0.0.1:{port}/mcp", engine_id="mcp-live",
            capability_map={"search_companies": "data.query"},
        )
        assert eid == "mcp-live"
        # 经枢纽路由到该 MCP 芯粒
        res = hub.route("data.query", {"query": "YC"})
        assert res.ok is True
        assert "search_companies" in res.data["text"]
    finally:
        server.shutdown()
