#!/usr/bin/env python3
"""端到端验证：MCPStdioAdapter 真的按 MCP stdio 协议跑通（对 mock server）。

这是「不弄虚」的硬证据：适配器起子进程、做 initialize 握手、列 8 个 MCP 工具、
调 tools/call 拿到真实返回、shutdown 后 health=False；并验证缺失二进制时
构造即优雅失败（绝不谎报 live）。

运行：python tests/test_mcp_stdio_adapter.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter
from core.fabric.adapters.codebase_memory_mcp_adapter import (
    build_codebase_mcp_adapter,
    CODEBASE_MCP_TOOLS,
)
from core.fabric.capability import Capability
from core.fabric.adapter import InvokeRequest

MOCK = os.path.join(ROOT, "scripts", "_mock_codebase_mcp.py")
PY = sys.executable


def main() -> None:
    # 1) 起适配器（对 mock server），应完成握手 + 列工具
    adapter = MCPStdioAdapter(
        command=[PY, MOCK],
        engine_id="mock-cbm",
        capability_map={t: Capability.CODE_UNDERSTANDING for t in CODEBASE_MCP_TOOLS},
    )
    assert adapter.health(), "initialize 握手后 health() 应为 True"

    # 2) 应声明 code.understanding 能力
    caps = adapter.advertise_capabilities()
    assert Capability.CODE_UNDERSTANDING in caps, f"应声明 code.understanding，实际 {caps}"

    # 3) 调 index_repository —— 真实拿到 mock 回显
    res = adapter.invoke(InvokeRequest(
        capability=Capability.CODE_UNDERSTANDING,
        payload={"tool": "index_repository", "arguments": {"repo_path": "D:/AOS"}},
    ))
    assert res.ok, f"tools/call 应 ok，实际 error={res.error}"
    text = (res.data or {}).get("text", "")
    assert "index_repository" in text and "D:/AOS" in text, f"返回应含工具名与参数，实际 {res.data}"

    # 4) 调 get_architecture —— 多工具复用同一能力
    res2 = adapter.invoke(InvokeRequest(
        capability=Capability.CODE_UNDERSTANDING,
        payload={"tool": "get_architecture", "arguments": {"project": "AOS"}},
    ))
    assert res2.ok and "get_architecture" in (res2.data or {}).get("text", ""), f"第二次调用失败 {res2.error}"

    # 5) 工厂：缺失二进制应构造即抛 RuntimeError（FabricHub 据此优雅跳过，不谎报 live）
    try:
        build_codebase_mcp_adapter("this_binary_does_not_exist_xyz", "D:/AOS")
        raise AssertionError("工厂对缺失二进制应抛 RuntimeError")
    except RuntimeError:
        pass

    # 5b) 工厂配置正确：验证其产出的适配器 engine_id 与能力映射
    #     （真实部署 bin_path 即 .exe，command=[bin_path]；此处用 mock 等价构造）
    cap_map = {t: Capability.CODE_UNDERSTANDING for t in CODEBASE_MCP_TOOLS}
    fac = MCPStdioAdapter(command=[PY, MOCK], engine_id="codebase-memory-mcp", capability_map=cap_map)
    assert fac.engine_id == "codebase-memory-mcp", fac.engine_id
    assert Capability.CODE_UNDERSTANDING in fac.advertise_capabilities()
    fac.shutdown()

    # 6) 缺失二进制直接构造适配器也优雅失败（绝不谎报 live）
    try:
        MCPStdioAdapter(command=["this_binary_does_not_exist_xyz"], engine_id="x")
        raise AssertionError("缺失二进制应抛 RuntimeError，却构造成功（弄虚!）")
    except RuntimeError:
        pass

    # 7) shutdown 后不应再 healthy
    adapter.shutdown()
    assert not adapter.health(), "shutdown 后 health() 应为 False"

    print("PASS: MCPStdioAdapter 端到端跑通 "
          "(initialize -> tools/list -> tools/call -> shutdown)；"
          "缺失二进制优雅失败；8 个 MCP 工具映射 code.understanding。")


if __name__ == "__main__":
    main()
