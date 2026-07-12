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
import shutil
import socket
import subprocess
import time
from pathlib import Path

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
    except Exception:
        pass
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
        # 本适配器只实现 CHANNEL_ACCESS（经 openclaw CLI 把消息交给网关背后的
        # LLM）。TOOL_USE / MEMORY_PERSISTENT 由 AOS 其它芯粒（ag2 / mem0）
        # 真实承载，故此处不虚报，避免路由优先选中却立刻 ok=False 再降级。
        return [Capability.CHANNEL_ACCESS]

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
                    return InvokeResult(
                        ok=False, error=proc.stderr.strip() or "openclaw agent failed"
                    )
                data = json.loads(proc.stdout)
                if data.get("status") != "ok":
                    return InvokeResult(ok=False, error=str(data.get("summary")))
                payloads = (data.get("result") or {}).get("payloads") or []
                reply = payloads[0].get("text", "") if payloads else ""
                return InvokeResult(
                    ok=True, data={"reply": reply, "agent": self._agent}
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

    def health(self) -> bool:
        return self.health_detail()["status"] == "ok"

    def health_detail(self) -> dict:
        """结构化自检：区分「网关端口不通」与「二进制缺失」，并给出可操作修复动作。

        返回 {"status": "ok"|"port_down"|"binary_missing",
              "reason": str|None, "action": str|None}
        """
        try:
            with socket.create_connection(("127.0.0.1", OPENCLAW_GATEWAY_PORT), timeout=2):
                return {"status": "ok", "reason": None, "action": None}
        except Exception as e:  # noqa: BLE001
            port_err = e
        have_cli = bool(shutil.which("openclaw")) or os.path.exists(OPENCLAW_DEFAULT_CLI)
        if _resolve_openclaw_mjs() is None and not have_cli:
            return {
                "status": "binary_missing",
                "reason": "OpenClaw 网关未运行，且未找到 openclaw 二进制（npm -g openclaw / openclaw.cmd）",
                "action": "npm i -g openclaw   或   运行 python scripts/aos_supervisor.py --only openclaw 拉起网关(:18789)",
            }
        return {
            "status": "port_down",
            "reason": f"OpenClaw 网关未监听 127.0.0.1:{OPENCLAW_GATEWAY_PORT}（{type(port_err).__name__}）",
            "action": "启动网关：openclaw gateway --allow-unconfigured   或   python scripts/aos_supervisor.py --only openclaw",
        }

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
            subprocess.Popen(
                cmd, cwd=os.getcwd(), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True,
            )
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
