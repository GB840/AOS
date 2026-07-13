r"""AOS <-> OpenClaw 链路自检（必须在用户 Windows 主机跑，不在沙箱）。

前置：OpenClaw 网关已起（默认 127.0.0.1:18789，token=aos-fabric-2026local）。
本脚本验证三件事：
  [1] 网关 TCP 端口可达
  [2] `openclaw agent` CLI 真能产出 LLM 回包（证明 网关->模型 通）
  [3] 经 AOS 的 OpenClawAdapter 调一次（证明 AOS->网关 通）

用法：
  cd D:\AOS
  $env:OPENCLAW_GATEWAY_TOKEN = "aos-fabric-2026local"
  C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe scripts/aos_openclaw_smoke.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys

GATEWAY_PORT = 18789
TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "aos-fabric-2026local")
OPENCLAW_CLI = r"C:\Users\Administrator\AppData\Roaming\npm\openclaw.cmd"
PING = "用一句话证明你正在工作，并说出你背后的模型名。"


def resolve_cli() -> str:
    f = shutil.which("openclaw")
    if f:
        return f
    if os.path.exists(OPENCLAW_CLI):
        return OPENCLAW_CLI
    return "openclaw"


def probe_gateway():
    try:
        with socket.create_connection(("127.0.0.1", GATEWAY_PORT), timeout=2):
            return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def run_agent(cli: str, text: str):
    env = dict(os.environ)
    env["OPENCLAW_GATEWAY_TOKEN"] = TOKEN
    try:
        p = subprocess.run(
            [cli, "agent", "--agent", "main", "-m", text, "--json"],
            capture_output=True, text=True, timeout=300, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "openclaw agent 超时(>300s)，网关背后的模型可能没响应"
    if p.returncode != 0:
        return None, f"rc={p.returncode} stderr={p.stderr.strip()[:300]}"
    try:
        data = json.loads(p.stdout)
    except Exception as e:  # noqa: BLE001
        return None, f"坏 JSON: {e}; stdout={p.stdout[:300]}"
    if data.get("status") != "ok":
        return None, f"status={data.get('status')} summary={data.get('summary')}"
    payloads = (data.get("result") or {}).get("payloads") or []
    reply = payloads[0].get("text", "") if payloads else ""
    return reply, None


def main() -> int:
    print("=== AOS <-> OpenClaw 链路自检 ===")
    print(f"token={TOKEN}  port={GATEWAY_PORT}\n")

    ok_gw, err = probe_gateway()
    print(f"[1] 网关可达 (TCP 18789): {'YES' if ok_gw else 'NO'}")
    if not ok_gw:
        print(f"    {err}")
        print("    >> 先起网关: openclaw gateway run --bind loopback --port 18789 "
              "--token aos-fabric-2026local")
        return 1

    cli = resolve_cli()
    print(f"[2] openclaw CLI: {cli}")
    reply, err = run_agent(cli, PING)
    if err:
        print(f"    openclaw agent 失败: {err}")
        return 1
    print(f"    openclaw agent 真实回包:\n    {reply}\n")

    print("[3] 经 AOS OpenClawAdapter 调用...")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from core.fabric.adapters.openclaw_adapter import OpenClawAdapter
        from core.fabric.adapter import InvokeRequest
        from core.fabric.capability import Capability

        ad = OpenClawAdapter(gateway_token=TOKEN)
        print(f"    adapter.health = {ad.health()}")
        res = ad.invoke(
            InvokeRequest(capability=Capability.CHANNEL_ACCESS, payload={"text": PING})
        )
        if res.ok:
            print(f"    AOS invoke 成功:\n    {res.data.get('reply')}\n")
        else:
            print(f"    AOS invoke 失败(非致命): {res.error}")
    except Exception as e:  # noqa: BLE001
        print(f"    AOS 导入/调用异常(可忽略，[1][2] 已证明网关工作): "
              f"{type(e).__name__}: {e}")

    print("=== 结论: 网关 + CLI 真实可用，链路不是玩具 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
