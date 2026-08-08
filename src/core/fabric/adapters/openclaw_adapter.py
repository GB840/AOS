"""Real OpenClaw adapter for the AOS open fabric.

OpenClaw (openclaws.io, MIT) is a self-hosted gateway that bridges 20+ chat
platforms to AI coding agents. AOS does NOT re-implement it: this adapter
shells out to the real OpenClaw CLI (`openclaw agent ...`) against a RUNNING
OpenClaw Gateway (default http://127.0.0.1:18789, token auth).

Verified working 2026-07-08:
  $ openclaw agent --agent main -m "<text>" --json
returns {"status":"ok","result":{"payloads":[{"text": ...}]}} produced by the
real OpenClaw agent harness over the configured LLM provider.

This is the ONLY correct way to talk to OpenClaw — no hand-rolled REST paths.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from typing import Optional

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult, extract_text
from ..capability import Capability

# OpenClaw installs a `openclaw` shim on PATH; on Windows the launcher is .cmd.
OPENCLAW_DEFAULT_CLI = r"C:\Users\Administrator\AppData\Roaming\npm\openclaw.cmd"
OPENCLAW_GATEWAY_PORT = 18789
OPENCLAW_DEFAULT_AGENT = "main"


def _resolve_cli() -> str:
    found = shutil.which("openclaw")
    if found:
        return found
    if os.path.exists(OPENCLAW_DEFAULT_CLI):
        return OPENCLAW_DEFAULT_CLI
    return "openclaw"


# --- gateway 自愈路径解析（与 aos_supervisor.py 同源逻辑，独立实现避免跨层导入） ---
def _resolve_node_bin() -> str:
    if os.environ.get("NODE_BIN"):
        return os.environ["NODE_BIN"]
    candidate = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2\node.exe"
    if Path(candidate).exists():
        return candidate
    return "node"


def _resolve_openclaw_mjs() -> Optional[str]:
    if os.environ.get("OPENCLAW_MJS"):
        return os.environ["OPENCLAW_MJS"]
    try:
        out = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            mjs = Path(out.stdout.strip()) / "openclaw" / "openclaw.mjs"
            if mjs.exists():
                return str(mjs)
    except Exception as e:
        logger.warning("npm root -g 查找 openclaw.mjs 失败，尝试回退路径: %s", e)
    fb = Path(r"C:\Users\Administrator\AppData\Roaming\npm\node_modules\openclaw\openclaw.mjs")
    if fb.exists():
        return str(fb)
    return None


class OpenClawAdapter(BaseAgentAdapter):
    """Talks to a real, running OpenClaw Gateway via the `openclaw` CLI."""

    def __init__(
        self,
        gateway_token: str | None = None,
        agent_id: str = OPENCLAW_DEFAULT_AGENT,
        cli: str | None = None,
    ) -> None:
        # Token is read from env OPENCLAW_GATEWAY_TOKEN if not passed explicitly.
        self._token = gateway_token or os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        self._agent = agent_id
        self._cli = cli or _resolve_cli()

    @property
    def engine_id(self) -> str:
        return "openclaw"

    def advertise_capabilities(self) -> list[Capability]:
        # CHANNEL_ACCESS：经 openclaw agent 把消息交给网关背后的 LLM（聊天）。
        # CHANNEL_SEND：经 openclaw agent --channel <渠道> --deliver 把消息
        #   真正推送出去（文档「场景1：通过微信通知我」的真实落地路径）。
        # TOOL_USE / MEMORY_PERSISTENT 由 AOS 其它芯粒（ag2 / mem0）真实承载，
        # 此处不虚报，避免路由优先选中却立刻 ok=False 再降级。
        return [Capability.CHANNEL_ACCESS, Capability.CHANNEL_SEND]

    def _run(self, *args: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        if self._token:
            env["OPENCLAW_GATEWAY_TOKEN"] = self._token
        return subprocess.run(
            [self._cli, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

    @staticmethod
    def _build_send_args(
        channel: str,
        text: str,
        to: str | None = None,
        agent: str | None = None,
        session_key: str | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        """构造真实的渠道投递命令（供 dry-run 验证，无副作用）。

        机制已探明（非文档臆测，实测验证）：
          openclaw agent --channel <渠道> --message "<文本>" --deliver --json
            [--to <E.164> | --agent <id> | --session-key <key> | --session-id <id>]
        OpenClaw 要求「必须指定投递目标」，四种模式任选其一；缺省会报
        "No target session selected"。
        """
        args = ["agent", "--channel", channel, "--message", text, "--deliver", "--json"]
        if to:
            args += ["--to", str(to)]
        elif agent:
            args += ["--agent", str(agent)]
        elif session_key:
            args += ["--session-key", str(session_key)]
        elif session_id:
            args += ["--session-id", str(session_id)]
        return args

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        try:
            if req.capability == Capability.CHANNEL_ACCESS:
                # AOS hands a user message to the real OpenClaw agent turn.
                # 文本可显式给，或从上游产出（图片/搜索结果）投影得到——
                # 否则 openclaw CLI 会因空 -m "" 报 Missing message。
                text = req.payload.get("text") or extract_text(req.payload)
                proc = self._run(
                    "agent", "--agent", self._agent, "-m", text, "--json", timeout=600
                )
                if proc.returncode != 0:
                    err, action = self._parse_failure(proc)
                    return InvokeResult(
                        ok=False, error=err, data={"action": action} if action else None
                    )
                try:
                    data = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    # 非 JSON 输出（openclaw 把报错打到 stdout 而非 stderr 的情况）
                    err, action = self._parse_failure(proc)
                    return InvokeResult(
                        ok=False,
                        error=err or "openclaw 返回非 JSON 内容",
                        data={"action": action} if action else None,
                    )
                if data.get("status") != "ok":
                    return InvokeResult(ok=False, error=str(data.get("summary")))
                payloads = (data.get("result") or {}).get("payloads") or []
                reply = payloads[0].get("text", "") if payloads else ""
                return InvokeResult(
                    ok=True, data={"reply": reply, "agent": self._agent}
                )
            if req.capability == Capability.CHANNEL_SEND:
                # 真实落地文档「场景1：通过微信通知我」。
                # 机制（已探明，非文档臆测，且经真实发送实测验证）：
                #   openclaw agent --channel <渠道> --message "<文本>" --deliver --json
                #     [--to <E.164> | --agent <id> | --session-key <key> | --session-id <id>]
                # OpenClaw 要求「必须指定投递目标」，故 payload 需给 to/agent/
                # session_key/session_id 之一；本机已配置 openclaw-weixin。
                text = req.payload.get("text") or extract_text(req.payload)
                if not text:
                    return InvokeResult(
                        ok=False, error="CHANNEL_SEND 需要 text 载荷（消息正文）"
                    )
                channel = req.payload.get("channel") or "openclaw-weixin"
                to = req.payload.get("to")
                agent = req.payload.get("agent")
                session_key = req.payload.get("session_key")
                session_id = req.payload.get("session_id")
                if not any([to, agent, session_key, session_id]):
                    return InvokeResult(
                        ok=False,
                        error="CHANNEL_SEND 需指定投递目标：to / agent / session_key / session_id",
                    )
                args = self._build_send_args(
                    channel, text, to, agent, session_key, session_id
                )
                proc = self._run(*args, timeout=600)
                if proc.returncode != 0:
                    err, action = self._parse_failure(proc)
                    return InvokeResult(
                        ok=False, error=err, data={"action": action} if action else None
                    )
                try:
                    data = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    err, action = self._parse_failure(proc)
                    return InvokeResult(
                        ok=False,
                        error=err or "openclaw 返回非 JSON 内容",
                        data={"action": action} if action else None,
                    )
                if data.get("status") != "ok":
                    return InvokeResult(ok=False, error=str(data.get("summary")))
                return InvokeResult(
                    ok=True,
                    data={"channel": channel, "to": to, "delivered": True, "raw": data},
                )
            # TOOL_USE / MEMORY_PERSISTENT are delegated to the OpenClaw agent
            # harness itself (skills + persistent memory live inside OpenClaw);
            # AOS routes those capabilities to OpenClaw via the same agent turn.
            return InvokeResult(
                ok=False, error=f"unsupported capability {req.capability.value}"
            )
        except Exception as e:  # gateway down / cli missing -> graceful degrade
            logger.warning("openclaw invoke failed: %s", e)
            return InvokeResult(ok=False, error=str(e))

    @staticmethod
    def _strip_ansi(s: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*m", "", s or "")

    def _parse_failure(self, proc: "subprocess.CompletedProcess[str]") -> tuple[str, str | None]:
        """把 openclaw CLI 的报错翻译成「诚实 + 可操作」的中文诊断。

        不把整段带 ANSI 颜色码的 stderr 当 error 甩出去（那是之前误导
        'Expecting value' 的根源）。优先识别已知故障模式并给出修复动作。
        """
        clean = self._strip_ansi((proc.stderr or "") + "\n" + (proc.stdout or ""))
        if "SessionWriteLockStaleError" in clean:
            return (
                "openclaw 网关 session 写锁污染(stale lock)：网关进程卡住了一个会话锁，"
                "新 agent 调用无法创建会话",
                "重启网关清除锁：先 `openclaw gateway stop`（或 "
                "`schtasks /End /TN \"OpenClaw Gateway\"`）停掉旧进程，再 "
                "`openclaw gateway run --bind loopback --port 18789 "
                "--token aos-fabric-2026local` 重新拉起",
            )
        low = clean.lower()
        if "401" in clean or ("unauthorized" in low) or ("token" in low and "fail" in low):
            return (
                "openclaw 网关鉴权失败：OPENCLAW_GATEWAY_TOKEN 与网关启动时不一致",
                "确保 AOS 环境变量 OPENCLAW_GATEWAY_TOKEN 等于启动网关用的 --token",
            )
        if "gateway" in low and ("not" in low or "refused" in low or "down" in low):
            return (
                "openclaw 网关不可达",
                "启动网关：openclaw gateway run --bind loopback --port 18789 "
                "--token aos-fabric-2026local",
            )
        # 兜底：取最后一行有意义的内容，截断避免噪音
        lines = [l.strip() for l in clean.splitlines() if l.strip()]
        head = lines[-1] if lines else "openclaw agent 异常退出（无错误输出）"
        return (head[:300], None)

    def agent_health(self, timeout: int = 20) -> dict:
        """真实 agent 可达性探针：不只查端口，而是真发一个 ping 看能否出会话。

        health() 只看 TCP 端口（端口在听 ≠ agent 真能工作，stale lock 就是反例）。
        本方法弥补这个「假健康」缺口。开头做轻量端口探（不回调用 health_detail，
        避免与 health_detail→agent_health 互递归）。
        返回 {"status": "ok" | "gateway_down" | "agent_stale" | "agent_error",
              "reason": str|None, "action": str|None}
        """
        try:
            with socket.create_connection(("127.0.0.1", OPENCLAW_GATEWAY_PORT), timeout=2):
                pass
        except Exception:  # noqa: BLE001
            return {"status": "gateway_down"}
        try:
            proc = self._run(
                "agent", "--agent", self._agent, "-m", "ping", "--json", timeout=timeout
            )
            if proc.returncode == 0:
                try:
                    json.loads(proc.stdout)
                    return {"status": "ok"}
                except json.JSONDecodeError as e:
                    logger.warning("openclaw agent ping 响应非合法 JSON: %s", e)
            err, action = self._parse_failure(proc)
            return {"status": "agent_stale", "reason": err, "action": action}
        except Exception as e:  # noqa: BLE001
            return {"status": "agent_error", "reason": str(e)}

    def health(self) -> bool:
        # 轻量：仅探端口。热路径（route 每次都调 health）不做 agent ping，
        # 否则每次路由都多一次 agent 调用。真实 agent 可达性由 health_detail
        # / agent_health 暴露。
        try:
            with socket.create_connection(("127.0.0.1", OPENCLAW_GATEWAY_PORT), timeout=2):
                return True
        except Exception:  # noqa: BLE001
            return False

    def health_detail(self) -> dict:
        """结构化自检：区分「网关端口不通」「二进制缺失」「agent 真不可用」。

        比 health() 多一层：端口在听 ≠ agent 真能工作（stale lock 就是反例），
        故 TCP 可达时再发一次轻量 agent ping 探真实可达性。
        返回 {"status": "ok"|"port_down"|"binary_missing"|"agent_stale"|"agent_error",
              "reason": str|None, "action": str|None}
        """
        try:
            with socket.create_connection(("127.0.0.1", OPENCLAW_GATEWAY_PORT), timeout=2):
                pass
        except Exception:  # noqa: BLE001
            have_cli = bool(shutil.which("openclaw")) or os.path.exists(OPENCLAW_DEFAULT_CLI)
            if _resolve_openclaw_mjs() is None and not have_cli:
                return {
                    "status": "binary_missing",
                    "reason": "OpenClaw 网关未运行，且未找到 openclaw 二进制（npm -g openclaw / openclaw.cmd）",
                    "action": "npm i -g openclaw   或   运行 python scripts/aos_supervisor.py --only openclaw 拉起网关(:18789)",
                }
            return {
                "status": "port_down",
                "reason": f"OpenClaw 网关未监听 127.0.0.1:{OPENCLAW_GATEWAY_PORT}",
                "action": "启动网关：openclaw gateway run --bind loopback --port 18789 --token aos-fabric-2026local",
            }
        # 端口在听 → 进一步探 agent 是否真能出会话（暴露 stale lock 等假健康）
        ah = self.agent_health(timeout=8)
        if ah["status"] != "ok":
            return {
                "status": ah["status"],
                "reason": ah.get("reason"),
                "action": ah.get("action"),
            }
        return {"status": "ok", "reason": "网关端口可达且 agent 可出会话", "action": None}

    def ensure_gateway(self, token: str | None = None, timeout: float = 60.0) -> bool:
        """尽力自动拉起 OpenClaw Gateway（:18789）。已健康则直接返回 True。

        仅依赖本机已安装的 openclaw（node + openclaw.mjs）。拉起失败（无二进制 /
        端口持续不通）返回 False 且不抛——调用方据此决定降级或提示用户。
        """
        if self.health():
            return True
        mjs = _resolve_openclaw_mjs()
        if not mjs:
            logger.warning("ensure_gateway: 找不到 openclaw.mjs，无法自动拉起网关")
            return False
        node = _resolve_node_bin()
        token = (token or self._token
                 or os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
                 or "aos-fabric-2026local")
        cmd = [node, mjs, "gateway", "run", "--bind", "loopback",
               "--port", str(OPENCLAW_GATEWAY_PORT), "--token", token]
        try:
            # P4-5 资源泄漏修复：原 Popen 返回值未保存，进程成为孤儿，父进程
            # 退出后仍可能继续运行。保存 PID 并注册 atexit 终止钩子。
            proc = subprocess.Popen(
                cmd, cwd=os.getcwd(), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True,
            )
            # 注册退出钩子：父进程退出时终止 gateway 子进程，避免孤儿进程
            import atexit
            atexit.register(
                lambda p=proc: p.terminate() if p.poll() is None else None
            )
            logger.info("ensure_gateway: 已拉起 gateway 子进程 PID=%d", proc.pid)
        except Exception as e:  # noqa: BLE001
            logger.warning("ensure_gateway: 启动失败: %s", e)
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.health():
                return True
            time.sleep(1.0)
        return False

    def supported_protocols(self) -> list[str]:
        # OpenClaw ships a native MCP bridge (stdio + HTTP).
        return ["MCP"]
