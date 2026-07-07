"""OpenClaw 子智能体 — 通过 ACP 协议桥接 jiuwenswarm.

!!! DEPRECATED (2026-07-08) — 此自研桥接依赖 external/ 中并不存在的 OpenClaw 源码
(detect_openclaw_path 实际返回 None，桥接悬空)，违反“用真实开源、不自己写”铁律。
改用 src/core/fabric/adapters/openclaw_adapter.py 调用真实部署的 OpenClaw Gateway。
本文件仅保留作兼容参考。
"""

import asyncio
import logging
import sys
from typing import Any, Dict, Optional

from utils.config import config
from deerflow.path_detect import detect_openclaw_path

logger = logging.getLogger(__name__)

OPENCLAW_PATH = detect_openclaw_path()

if OPENCLAW_PATH:
    logger.info(f"OpenClaw: 源码路径已检测到: {OPENCLAW_PATH}")
else:
    logger.warning("OpenClaw: 源码路径未检测到")


def _ensure_openclaw_importable() -> None:
    """将 OpenClaw 源码路径加入 sys.path."""
    if OPENCLAW_PATH and OPENCLAW_PATH not in sys.path:
        sys.path.insert(0, OPENCLAW_PATH)


class OpenClawSubAgent:
    """封装 OpenClaw 的 ACP 客户端，提供同步调用接口.

    核心能力:
    - 浏览器自动化 (playwright)
    - 代码生成 / 审查
    - 团队协作任务
    - Web 搜索与内容抓取
    """

    NAME = "openclaw"
    DESCRIPTION = "OpenClaw 智能体 — 浏览器自动化、代码生成、团队协作"
    CAPABILITIES = [
        "browser_automation",
        "code_generation",
        "code_review",
        "web_search",
        "team_collaboration",
        "file_operations",
    ]

    def __init__(self, command: str = "npx", args: Optional[list] = None, cwd: Optional[str] = None) -> None:
        self._command = command
        self._args = args or ["-y", "@anthropic-ai/claude-code"]
        self._cwd = cwd
        self._client = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        _ensure_openclaw_importable()
        logger.info("OpenClawSubAgent 初始化完成 (command=%s)", command)

    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _ensure_connected(self) -> None:
        """同步方式确保 ACP 客户端已连接."""
        if self._client is not None:
            return
        loop = self._get_or_create_loop()
        from jiuwenswarm.acp import AcpStdioClient

        self._client = AcpStdioClient(
            command=self._command,
            args=self._args,
            cwd=self._cwd,
        )
        loop.run_until_complete(self._client.connect())
        logger.info("OpenClaw ACP 连接成功 (session=%s)", self._client.session_id)

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步调用入口 — 供 SubAgentRegistry.invoke() 使用."""
        message = input_data.get("message", "")
        if not message:
            return {"error": "缺少 message 字段"}

        try:
            self._ensure_connected()
            loop = self._get_or_create_loop()
            timeout = input_data.get("timeout", 600)
            reply = loop.run_until_complete(self._client.chat(message, timeout=float(timeout)))
            return {"reply": reply, "agent": self.NAME}
        except Exception as exc:
            logger.error("OpenClaw 调用失败: %s", exc, exc_info=True)
            raise

    async def async_handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """异步调用入口."""
        message = input_data.get("message", "")
        if not message:
            return {"error": "缺少 message 字段"}

        try:
            if self._client is None:
                from jiuwenswarm.acp import AcpStdioClient

                self._client = AcpStdioClient(
                    command=self._command,
                    args=self._args,
                    cwd=self._cwd,
                )
                await self._client.connect()

            timeout = input_data.get("timeout", 600)
            reply = await self._client.chat(message, timeout=float(timeout))
            return {"reply": reply, "agent": self.NAME}
        except Exception as exc:
            logger.error("OpenClaw 异步调用失败: %s", exc, exc_info=True)
            raise

    def close(self) -> None:
        if self._client is not None and self._loop is not None:
            try:
                self._loop.run_until_complete(self._client.close())
            except Exception as exc:
                logger.warning("OpenClaw 关闭时出错: %s", exc)
            finally:
                self._client = None
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
            self._loop = None
        logger.info("OpenClawSubAgent 已关闭")

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected
