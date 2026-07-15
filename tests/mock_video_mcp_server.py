"""最小 stdio MCP server（测试用，零外部依赖）。

实现 MCP stdio 约定的行分隔 JSON-RPC：读 stdin 一行请求、写 stdout 一行响应、
日志走 stderr。支持 initialize / tools/list / tools/call，模拟视频类 MCP
工具集（omni_video_* 与 video_*）。被 tests/test_video_mcp_registry.py 经
MCPStdioAdapter 子进程拉起，用于真实验证 stdio 传输链路（不依赖真实 ffmpeg / 包）。
"""
import json
import sys


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


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
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "serverInfo": {"name": "mock-video-mcp", "version": "0"},
            }})
        elif method == "notifications/initialized":
            continue  # 通知无需响应
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": "omni_video_ingest", "description": "ingest video", "inputSchema": {}},
                {"name": "omni_video_render", "description": "render video", "inputSchema": {}},
                {"name": "video_frames_extract", "description": "extract frames", "inputSchema": {}},
                {"name": "video_probe", "description": "probe video", "inputSchema": {}},
            ]}})
        elif method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text",
                             "text": f"MOCK[{name}]:{json.dumps(args, ensure_ascii=False)}"}],
                "isError": False,
            }})
        else:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"message": f"unknown {method}"}})


if __name__ == "__main__":
    main()
