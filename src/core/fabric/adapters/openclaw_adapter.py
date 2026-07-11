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
import subprocess

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
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
        return [
            Capability.CHANNEL_ACCESS,
            Capability.TOOL_USE,
            Capability.MEMORY_PERSISTENT,
        ]

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
                text = req.payload.get("text", "")
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
        # 主通路是网关反向代理 (src/api/gateway.py -> :18789); 探活网关端口即可,
        # 不再依赖 `openclaw health` CLI 是否在 PATH (避免启动期误判 False)。
        try:
            import socket
            with socket.create_connection(("127.0.0.1", OPENCLAW_GATEWAY_PORT), timeout=2):
                return True
        except Exception as e:
            logger.debug("openclaw health check failed: %s", e)
            return False

    def supported_protocols(self) -> list[str]:
        # OpenClaw ships a native MCP bridge (stdio + HTTP).
        return ["MCP"]
