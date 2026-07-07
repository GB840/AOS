"""LobsterAI 子智能体 — 通过 OpenClaw ACP 桥接网易有道 LobsterAI 的办公自动化能力."""

import json
import logging
import subprocess
import sys
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from utils.config import config
from deerflow.path_detect import detect_openclaw_path

LOBSTERAI_PATH = config.LOBSTER_PATH or str(Path(config.BASE_DIR) / "external" / "lobster")
OPENCLAW_PATH = detect_openclaw_path() or config.OPENCLAW_CWD


class LobsterSubAgent:
    """封装 LobsterAI 的办公自动化能力.

    LobsterAI 本身使用 OpenClaw 作为唯一 Agent Runtime，因此集成路径:
    - 通过 OpenClaw ACP 协议桥接 LobsterAI 的能力
    - 或直接启动 LobsterAI Electron 进程并调用其 API

    核心能力:
    - 办公自动化 (文档处理、数据分析、PPT制作)
    - 浏览器自动化
    - 定时任务
    - MCP 工具调用
    - 子智能体管理
    """

    NAME = "lobster"
    DESCRIPTION = "LobsterAI 智能体 — 办公自动化、文档处理、数据分析、浏览器自动化"
    CAPABILITIES = [
        "document_processing",
        "data_analysis",
        "presentation_creation",
        "browser_automation",
        "scheduled_tasks",
        "mcp_tools",
        "sub_agent_management",
    ]

    def __init__(
        self,
        mode: str = "openclaw_bridge",
        openclaw_command: str = "npx",
        lobster_port: int = 8091,
    ) -> None:
        self._mode = mode  # "openclaw_bridge" 或 "electron"
        self._openclaw_command = openclaw_command
        self._lobster_port = lobster_port
        self._lobster_base_url = f"http://localhost:{lobster_port}"
        self._acp_client = None
        self._loop = None
        logger.info("LobsterSubAgent 初始化完成 (mode=%s)", mode)

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步调用入口 — 供 SubAgentRegistry.invoke() 使用."""
        task = input_data.get("task", input_data.get("message", ""))
        if not task:
            return {"error": "缺少 task 或 message 字段"}

        if self._mode == "electron":
            return self._handle_via_electron(task, input_data)
        return self._handle_via_openclaw(task, input_data)

    def _handle_via_openclaw(self, task: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过 OpenClaw ACP 协议桥接 LobsterAI.

        LobsterAI 使用 OpenClaw 作为后端，所以我们启动 OpenClaw ACP 会话,
        通过带有 LobsterAI skills 提示的消息来调用 LobsterAI 的能力.
        """
        import asyncio

        timeout = input_data.get("timeout", 600)

        # 构造带有 LobsterAI 上下文的消息
        enhanced_message = (
            f"[LobsterAI Office Automation]\n"
            f"请执行以下办公自动化任务:\n{task}"
        )

        try:
            if self._acp_client is None:
                sys.path.insert(0, OPENCLAW_PATH)
                from jiuwenswarm.acp import AcpStdioClient

                self._loop = asyncio.new_event_loop()
                self._acp_client = AcpStdioClient(
                    command=self._openclaw_command,
                    args=["-y", "@anthropic-ai/claude-code"],
                    cwd=LOBSTERAI_PATH,
                )
                self._loop.run_until_complete(self._acp_client.connect())
                logger.info("LobsterAI (via OpenClaw) ACP 连接成功")

            loop = self._loop or asyncio.new_event_loop()
            reply = loop.run_until_complete(
                self._acp_client.chat(enhanced_message, timeout=float(timeout))
            )
            return {"reply": reply, "agent": self.NAME, "mode": "openclaw_bridge"}

        except Exception as exc:
            logger.error("LobsterAI (OpenClaw桥接) 调用失败: %s", exc, exc_info=True)
            raise

    def _handle_via_electron(self, task: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过 LobsterAI Electron 进程的 HTTP API 调用."""
        import requests

        timeout = input_data.get("timeout", 300)
        payload = {
            "task": task,
            "skill": input_data.get("skill", "general"),
            "options": {
                "maxSteps": input_data.get("max_steps", 30),
                "computerUse": input_data.get("computer_use", True),
            },
        }

        try:
            resp = requests.post(
                f"{self._lobster_base_url}/api/agent/run",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"reply": data, "agent": self.NAME, "mode": "electron"}
        except requests.ConnectionError:
            raise RuntimeError(
                f"无法连接 LobsterAI ({self._lobster_base_url})，请确保 LobsterAI Electron 应用已启动"
            )

    def close(self) -> None:
        if self._acp_client is not None and self._loop is not None:
            try:
                import asyncio
                self._loop.run_until_complete(self._acp_client.close())
            except Exception as exc:
                logger.warning("LobsterAI 关闭时出错: %s", exc)
            finally:
                self._acp_client = None
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
            self._loop = None
        logger.info("LobsterSubAgent 已关闭")

    @property
    def is_connected(self) -> bool:
        if self._mode == "openclaw_bridge":
            return self._acp_client is not None and self._acp_client.is_connected
        try:
            import requests
            resp = requests.get(f"{self._lobster_base_url}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False
