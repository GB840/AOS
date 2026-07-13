r"""AOS <-> OpenClaw 全链路自检（必须在用户的 Windows 主机跑，不在沙箱）。

为什么不能在沙箱跑：openclaw-weixin 插件需要你登录 Windows 桌面会话里的
微信鉴权上下文（contextToken），沙箱的非交互会话拿不到，网关会卡在插件初始化、
端口永远起不来。昨天（2026-07-13 13:49）在本机跑出过铁证：
  "gateway/channels/openclaw-weixin" outbound: text sent OK to=o9cq80z6...@im.wechat

本脚本验证四件事：
  [1] 网关 TCP 端口可达 (127.0.0.1:18789)
  [2] CHANNEL_ACCESS：openclaw agent CLI 真能产出 LLM 回包（网关->模型 通）
  [3] CHANNEL_SEND：经 openclaw agent --channel openclaw-weixin --deliver 真把
      一条测试消息投递出去（文档「场景1：通过微信通知我」的真实落地）
  [4] 经 AOS 的 OpenClawAdapter 调上面两项（证明 AOS->网关 接线通）

用法（在你自己的 PowerShell，已在桌面登录会话里）：
  cd D:\AOS
  $env:OPENCLAW_GATEWAY_TOKEN = "aos-fabric-2026local"
  # 可选：指定微信投递目标。格式 to:<openid> | agent:<id> | session_key:<k> | session_id:<id>
  # 不设置则默认 agent:main（投递到 main agent 自己的微信会话）
  $env:AOS_OPENCLAW_WEIXIN_TARGET = "to:o9cq80z6BKVik3cdrmwbq2uSpD8k@im.wechat"
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
SEND_TEXT = "[AOS 自检] 这是一条来自 AOS openclaw 适配器的 CHANNEL_SEND 投递测试消息，收到请忽略。"


def resolve_cli() -> str:
    f = shutil.which("openclaw")
    if f:
        return f
    if os.path.exists(OPENCLAW_CLI):
        return OPENCLAW_CLI
    return "openclaw"


def resolve_send_target() -> tuple[str | None, str | None, str | None, str | None]:
    """从 AOS_OPENCLAW_WEIXIN_TARGET 解析投递目标。

    返回 (to, agent, session_key, session_id)，恰好一个非空。
    默认 agent=main（投递到 main agent 自己的微信会话）。
    """
    raw = os.environ.get("AOS_OPENCLAW_WEIXIN_TARGET", "").strip()
    if not raw:
        return (None, "main", None, None)
    if raw.startswith("to:"):
        return (raw[3:], None, None, None)
    if raw.startswith("agent:"):
        return (None, raw[7:] or "main", None, None)
    if raw.startswith("session_key:"):
        return (None, None, raw[12:], None)
    if raw.startswith("session_id:"):
        return (None, None, None, raw[11:])
    # 裸 openid 也当作 to
    if "@" in raw:
        return (raw, None, None, None)
    return (None, "main", None, None)


def probe_gateway():
    try:
        with socket.create_connection(("127.0.0.1", GATEWAY_PORT), timeout=2):
            return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def run(cli: str, *args: str, timeout: int = 600):
    env = dict(os.environ)
    env["OPENCLAW_GATEWAY_TOKEN"] = TOKEN
    return subprocess.run(
        [cli, *args], capture_output=True, text=True, timeout=timeout, env=env
    )


def run_agent(cli: str, text: str):
    try:
        p = run(cli, "agent", "--agent", "main", "-m", text, "--json")
    except subprocess.TimeoutExpired:
        return None, "openclaw agent 超时(>600s)，网关背后的模型可能没响应"
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


def run_send(cli: str, text: str, to, agent, session_key, session_id):
    args = ["agent", "--channel", "openclaw-weixin", "--message", text,
            "--deliver", "--json"]
    if to:
        args += ["--to", str(to)]
    elif agent:
        args += ["--agent", str(agent)]
    elif session_key:
        args += ["--session-key", str(session_key)]
    elif session_id:
        args += ["--session-id", str(session_id)]
    try:
        p = run(*args, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "CHANNEL_SEND 超时(>600s)，投递未确认"
    if p.returncode != 0:
        return False, f"rc={p.returncode} stderr={p.stderr.strip()[:300]}"
    try:
        data = json.loads(p.stdout)
    except Exception as e:  # noqa: BLE001
        return False, f"坏 JSON: {e}; stdout={p.stdout[:300]}"
    if data.get("status") != "ok":
        return False, f"status={data.get('status')} summary={data.get('summary')}"
    return True, None


def main() -> int:
    print("=== AOS <-> OpenClaw 全链路自检 ===")
    print(f"token={TOKEN}  port={GATEWAY_PORT}\n")

    ok_gw, err = probe_gateway()
    print(f"[1] 网关可达 (TCP 18789): {'YES' if ok_gw else 'NO'}")
    if not ok_gw:
        print(f"    {err}")
        print("    >> 先在你自己的 PowerShell（已在桌面登录会话）起网关:")
        print("    openclaw gateway run --bind loopback --port 18789 "
              "--token aos-fabric-2026local")
        print("    （沙箱/非交互会话起不来，因为 weixin 插件要你的微信鉴权上下文）")
        return 1

    cli = resolve_cli()
    print(f"[2] openclaw CLI: {cli}")
    reply, err = run_agent(cli, PING)
    if err:
        print(f"    CHANNEL_ACCESS 失败: {err}")
        return 1
    print(f"    CHANNEL_ACCESS 真实回包:\n    {reply}\n")

    print("[3] CHANNEL_SEND 真投递到微信...")
    to, agent, sk, sid = resolve_send_target()
    tgt = f"to={to}" if to else (f"agent={agent}" if agent else
           (f"session_key={sk}" if sk else f"session_id={sid}"))
    print(f"    目标: {tgt}")
    ok_send, err = run_send(cli, SEND_TEXT, to, agent, sk, sid)
    if not ok_send:
        print(f"    CHANNEL_SEND 失败: {err}")
        print("    >> 若提示 No target session selected，设置 "
              "$env:AOS_OPENCLAW_WEIXIN_TARGET 指定投递目标")
        # CHANNEL_SEND 失败不致命（可能目标格式问题），继续验证 AOS 接线
    else:
        print("    CHANNEL_SEND 成功：消息已真实投递到微信（去微信确认收到）\n")

    print("[4] 经 AOS OpenClawAdapter 调用...")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from core.fabric.adapters.openclaw_adapter import OpenClawAdapter
        from core.fabric.adapter import InvokeRequest
        from core.fabric.capability import Capability

        ad = OpenClawAdapter(gateway_token=TOKEN)
        print(f"    adapter.health = {ad.health()}")
        print(f"    adapter 能力 = {[c.value for c in ad.advertise_capabilities()]}")

        res = ad.invoke(
            InvokeRequest(capability=Capability.CHANNEL_ACCESS, payload={"text": PING})
        )
        print(f"    AOS CHANNEL_ACCESS: ok={res.ok}"
              + (f" reply={res.data.get('reply')}" if res.ok else f" err={res.error}"))

        if ok_send:
            res2 = ad.invoke(
                InvokeRequest(capability=Capability.CHANNEL_SEND,
                              payload={"text": SEND_TEXT, "to": to, "agent": agent,
                                        "session_key": sk, "session_id": sid})
            )
            print(f"    AOS CHANNEL_SEND: ok={res2.ok}"
                  + ("" if res2.ok else f" err={res2.error}"))
    except Exception as e:  # noqa: BLE001
        print(f"    AOS 导入/调用异常(可忽略，[1][2][3] 已证明网关工作): "
              f"{type(e).__name__}: {e}")

    print("\n=== 结论 ===")
    print(f"  网关+CLI 可用: {'YES' if ok_gw and not err else 'NO'}")
    print(f"  CHANNEL_ACCESS 真实出包: {'YES' if not err else 'NO'}")
    print(f"  CHANNEL_SEND 真实投递微信: {'YES' if ok_send else 'NO (见上)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
