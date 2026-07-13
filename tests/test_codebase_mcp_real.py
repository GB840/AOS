#!/usr/bin/env python3
"""Real-binary end-to-end check for the codebase-memory-mcp integration.

Unlike tests/test_mcp_stdio_adapter.py (which talks to a mock peer), this test
talks to the REAL DeusData binary and verifies AOS can actually:
  - spawn it as an MCP stdio server,
  - complete the initialize handshake + tools/list (8 real MCP tools),
  - call get_architecture / search_code against the indexed graph of AOS itself.

It is skipped automatically when the binary or the indexed graph is absent, so it
is safe in environments that have not run setup_codebase_memory.ps1. Run:

  python tests/test_codebase_mcp_real.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from core.fabric.capability import Capability
from core.fabric.adapters.codebase_memory_mcp_adapter import build_codebase_mcp_adapter
from core.fabric.adapter import InvokeRequest

BIN = os.path.join(ROOT, "third_party", "codebase-memory-mcp", "bin", "codebase-memory-mcp.exe")
REPO = os.path.abspath(ROOT)
GRAPH = os.path.join(REPO, ".codebase-memory", "graph.db.zst")


def main() -> None:
    if not os.path.exists(BIN):
        print("SKIP: real binary not found at", BIN)
        print("      run: powershell -ExecutionPolicy Bypass -File setup_codebase_memory.ps1")
        return
    if not os.path.exists(GRAPH):
        print("SKIP: indexed graph not found at", GRAPH)
        print("      run the setup script first to index the repo.")
        return

    fac = build_codebase_mcp_adapter(BIN, REPO)
    assert fac.health(), "real binary should be healthy after handshake"
    names = sorted(t["name"] for t in fac._tools)
    print("MCP tools (%d): %s" % (len(names), names))
    assert len(names) == 8, "MCP server exposes exactly 8 tools, got %d: %s" % (len(names), names)

    r1 = fac.invoke(InvokeRequest(
        capability=Capability.CODE_UNDERSTANDING,
        payload={"tool": "get_architecture",
                 "arguments": {"project": "D-AOS", "aspects": ["all"]}},
    ))
    assert r1.ok, "get_architecture failed: %s" % r1.error
    print("get_architecture ok: %s" % (r1.data or {}).get("text", "")[:120])

    r2 = fac.invoke(InvokeRequest(
        capability=Capability.CODE_UNDERSTANDING,
        payload={"tool": "search_code", "arguments": {"project": "D-AOS", "pattern": "FabricHub"}},
    ))
    assert r2.ok, "search_code failed: %s" % r2.error
    print("search_code ok: %s" % (r2.data or {}).get("text", "")[:120])

    fac.shutdown()
    print("PASS: real codebase-memory-mcp E2E (handshake + 8 tools + live graph queries)")


if __name__ == "__main__":
    main()
