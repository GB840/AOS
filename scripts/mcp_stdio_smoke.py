#!/usr/bin/env python3
"""真机 stdio 端到端：起 AOS MCP server（subprocess），发 JSON-RPC 走通
initialize -> tools/list -> tools/call aos_list_engines，验证 FabricHub
经标准 MCP 对外暴露。不设 env 变量，靠隔离层自动退避 + best-effort .env。

这是「不虚」的硬证据：真实子进程、真实 JSON-RPC、真实 build FabricHub
（spawn agnes/ag2 隔离子进程），不是 mock。
"""
import json
import os
import subprocess
import sys
import time

PY = r"C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe"
ROOT = r"D:/AOS"
SRC = os.path.join(ROOT, "src")


def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC
    env["AOS_CLI_STANDALONE"] = "1"

    proc = subprocess.Popen(
        [PY, "-m", "aos_mcp.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=ROOT, text=True,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    # 1) initialize（MCP 规范要求先于其它调用）
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "mcp-stdio-smoke", "version": "1.0"}}})
    # 2) tools/list（秒回，不触发 hub build）
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    # 3) tools/call aos_list_engines（触发懒加载 build hub + spawn agnes/ag2）
    send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
          "params": {"name": "aos_list_engines", "arguments": {}}})

    responses = {}
    deadline = time.time() + 180
    while time.time() < deadline and len(responses) < 2:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("id") in (2, 3):
            responses[msg["id"]] = msg

    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

    ok = True
    tools = []
    if 2 in responses:
        tools = [t["name"] for t in responses[2].get("result", {}).get("tools", [])]
    else:
        print("[FAIL] 未收到 tools/list 响应")
        ok = False
    for need in ("aos_list_engines", "aos_route", "aos_invoke_engine"):
        if need not in tools:
            print(f"[FAIL] tools/list 缺少 {need}")
            ok = False
        else:
            print(f"[PASS] tools/list 含 {need}")

    if 3 in responses:
        try:
            content = responses[3]["result"]["content"][0]["text"]
            data = json.loads(content)
            if "adapters" not in data:
                print("[FAIL] aos_list_engines 返回缺少 adapters 键")
                ok = False
            else:
                print(f"[PASS] aos_list_engines 返回 {data.get('total')} 引擎, "
                      f"{data.get('live')} live")
                for eid, info in data.get("adapters", {}).items():
                    if info.get("isolated"):
                        iso = info.get("isolation", {})
                        print(f"   隔离引擎 {eid}: pid={iso.get('subprocess_pid')} "
                              f"standby={iso.get('standby_ready')}")
        except Exception as e:
            print(f"[FAIL] 解析 aos_list_engines 响应失败: {e}")
            ok = False
    else:
        print("[FAIL] 未收到 aos_list_engines 响应（build hub 可能超时）")
        ok = False

    if ok:
        print("MCP STDIO SMOKE PASS")
        return 0
    print("MCP STDIO SMOKE FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
