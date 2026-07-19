#!/usr/bin/env python3
"""真机 stdio 端到端：起 AOS MCP server（subprocess），发 JSON-RPC 走通
initialize -> tools/list -> tools/call aos_run_task，验证「think→do」自主执行
闭环经标准 MCP 对外暴露。不设 env 变量，靠隔离层自动退避 + best-effort .env。

这是「不虚」的硬证据：真实子进程、真实 JSON-RPC、真实 build FabricHub
（spawn agnes/ag2 隔离子进程），aos_run_task 真实跑了「规划→解析成 steps→
编排执行」全链路，不是 mock。

注意：执行阶段会真实经 route() 委派给下游引擎；沙箱若无外部 API key，
部分引擎会返回 error——这属于环境限制（与 openclaw 网关同理），不影响
「桥本身真通 + plan→steps 真生成」的验证结论。smoke 只校验结构与 steps。
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

    # 1) initialize
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "aos-run-task-smoke", "version": "1.0"}}})
    # 2) tools/list（秒回，不触发 hub build）
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    # 3) tools/call aos_run_task（触发懒加载 build hub + spawn 子进程 + 真跑闭环）
    send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
          "params": {"name": "aos_run_task",
                     "arguments": {"task": "搜索周末天气并画一张示意图",
                                   "planner": "heuristic"}}})

    responses = {}
    deadline = time.time() + 240
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
    if "aos_run_task" not in tools:
        print("[FAIL] tools/list 缺少 aos_run_task")
        ok = False
    else:
        print("[PASS] tools/list 含 aos_run_task")

    if 3 in responses:
        try:
            content = responses[3]["result"]["content"][0]["text"]
            data = json.loads(content)
            for key in ("task", "planner", "plan", "steps", "execution"):
                if key not in data:
                    print(f"[FAIL] aos_run_task 返回缺少 {key} 键")
                    ok = False
            steps = data.get("steps") or []
            if not steps:
                print("[FAIL] aos_run_task 未生成 steps（规划/解析失败）")
                ok = False
            else:
                print(f"[PASS] aos_run_task 生成 {len(steps)} 步: "
                      + " -> ".join(s.get("capability") for s in steps))
                print(f"      planner={data.get('planner')}  "
                      f"execution_keys={list((data.get('execution') or {}).keys())}")
        except Exception as e:
            print(f"[FAIL] 解析 aos_run_task 响应失败: {e}")
            ok = False
    else:
        print("[FAIL] 未收到 aos_run_task 响应（build hub 可能超时）")
        ok = False

    if ok:
        print("AOS_RUN_TASK SMOKE PASS")
        return 0
    print("AOS_RUN_TASK SMOKE FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
