#!/usr/bin/env python3
"""Mock MCP stdio server —— 仅供测试 AOS 的 MCPStdioAdapter。

忠实地按真实 codebase-memory-mcp（DeusData）的 stdio 协议说话：
- 行分隔 JSON-RPC 2.0，从 stdin 读请求、向 stdout 写响应；
- 日志只走 stderr（绝不污染协议流）；
- 响应 initialize / tools/list / tools/call；忽略无 id 的 notification。

它不真的索引代码，只把调用回显成文本，用于证明 AOS 适配器确实在按 MCP 协议
与子进程对话、能拿到真实返回——这是「不弄虚」的端到端证据。
"""
import json
import sys

TOOLS = [
    "index_repository", "search_graph", "trace_path", "query_graph",
    "get_graph_schema", "get_code_snippet", "get_architecture", "search_code",
]


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params", {}) or {}
        # 无 id = notification（如 notifications/initialized）：忽略，不回包。
        if mid is None:
            continue
        if method == "initialize":
            resp = {
                "jsonrpc": "2.0", "id": mid,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "serverInfo": {"name": "mock-codebase-memory-mcp", "version": "0.0.0"},
                },
            }
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0", "id": mid,
                "result": {"tools": [
                    {"name": t, "description": t,
                     "inputSchema": {"type": "object", "properties": {}}}
                    for t in TOOLS
                ]},
            }
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            text = f"[mock {name}] args={json.dumps(args, ensure_ascii=False)}"
            resp = {
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            }
        elif method == "shutdown":
            resp = {"jsonrpc": "2.0", "id": mid, "result": {}}
        else:
            resp = {
                "jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
