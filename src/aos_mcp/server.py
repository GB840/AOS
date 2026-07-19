"""AOS MCP Server — 将 AOS 能力暴露为标准 MCP（Model Context Protocol）服务端。

复用 `protocol.py` 的 `MCPProtocol`（已实现的 JSON-RPC 2.0 MCP 骨架），在其上挂载
**stdio transport**，使外部 MCP 客户端（如 Claude Desktop / Cursor / 任意 MCP 宿主）可通过
stdio 连接 AOS。

已知约束（重要，已按"验证够再定性"纪律核实，勿遗漏）：
1. **命名冲突**：AOS 自有 `src/aos_mcp/` 包与官方 `mcp` SDK 同名。在 AOS 运行时（PYTHONPATH 含 src）
   下 `import aos_mcp` 解析到 AOS 本地包，官方 SDK 被遮蔽；且 `src/api/main.py`、`src/core/brain.py`
   共 3 处 `from aos_mcp import ...` 依赖本地包。因此本服务端用本地 `MCPProtocol` + 自研 stdio 循环，
   而非官方 `mcp.server` SDK。彻底解决需将 `src/aos_mcp` 重命名为 `src/aos_mcp` 并更新这 3 处引用
   （已记录为待办 #140）。
2. **stdout 纯净**：MCP stdio 要求 stdout 仅含 JSON-RPC。真实工具（openclaw / gui / office /
   RAG / agency）在调用时会 `import core` 或 `import skills`，触发 AOS 启动日志/警告刷屏污染流。
   故本服务端默认仅挂载“不触发 core/skills”的干净工具（get_status 等）；需要大脑的工具在大脑
   就绪、且日志抑制/重定向就位后再接入（见 `build_protocol()` 注释处的扩展点）。
3. 启动即 `logging.disable(CRITICAL)` + `AOS_CLI_STANDALONE=1`，最大限度抑制日志噪音。

运行：
    PYTHONPATH=D:/AOS/src python -m mcp.server
MCP 客户端配置（stdio）：
    { "mcpServers": { "aos": { "command": "python", "args": ["-m", "mcp.server"], "env": { "PYTHONPATH": "D:/AOS/src" } } } }
"""

import json
import logging
import os
import sys

# 必须在导入任何 AOS 模块之前抑制日志，保证 stdio 输出纯净
logging.disable(logging.CRITICAL)
os.environ.setdefault("AOS_CLI_STANDALONE", "1")

from .protocol import MCPProtocol, MCPMessage  # noqa: E402


def build_protocol() -> MCPProtocol:
    """构造 MCP 协议层并挂载工具。

    扩展点：接入真实 AOS 能力时，在此处注册新工具，例如：
        proto.register_tool(
            MCPTool(name="codebase_search", description="...", input_schema={...}),
            _codebase_search_handler,
        )
    注意：若 handler 内部会 `import core` / `import skills`（触发启动日志污染 stdout），
    需先解决约束 #2（日志重定向 / 独立解释器），否则会破坏 MCP 流。
    """
    proto = MCPProtocol()
    return proto


def run_stdio() -> None:
    """stdio transport 主循环：从 stdin 逐行读 JSON-RPC，写响应到 stdout。"""
    proto = build_protocol()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = MCPMessage.from_json(raw)
        except Exception as e:  # noqa: BLE001
            sys.stdout.write(
                json.dumps(
                    {"jsonrpc": "2.0", "error": {"code": -32700, "message": f"parse error: {e}"}},
                    ensure_ascii=False,
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        resp = proto.handle_message(msg)
        sys.stdout.write(resp.to_json() + "\n")
        sys.stdout.flush()


def main() -> int:
    run_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
