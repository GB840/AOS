"""UI-TARS 子智能体 — 通过子进程/MCP 桥接字节跳动的 GUI 自动化 Agent."""

import json
import logging
import subprocess
import sys
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from utils.config import config
from deerflow.path_detect import detect_uitars_path

UITARS_PATH = detect_uitars_path() or config.UITARS_CWD


class UITarsSubAgent:
    """封装 UI-TARS Desktop 的 GUI 自动化能力.

    UI-TARS 是 TypeScript/Electron 应用，无法直接 Python 导入.
    通过以下方式桥接:
    1. 子进程调用 UI-TARS CLI (npx @anthropic-ai/ui-tars 或自构建 CLI)
    2. 或通过 MCP 协议桥接 (UI-TARS 作为 MCP Server)

    核心能力:
    - GUI 桌面自动化 — 截屏识别、鼠标键盘操作
    - 浏览器自动化
    - 视觉问答 (VQA)
    """

    NAME = "uitars"
    DESCRIPTION = "UI-TARS 智能体 — GUI 桌面自动化、截屏识别、鼠标键盘操作"
    CAPABILITIES = [
        "gui_automation",
        "screen_capture",
        "mouse_keyboard_control",
        "browser_automation",
        "visual_qa",
    ]

    def __init__(self, cli_command: Optional[str] = None, use_mcp: bool = False, mcp_port: int = 8090) -> None:
        self._cli_command = cli_command or "npx"
        self._cli_args = ["-y", "@anthropic-ai/ui-tars"]
        self._use_mcp = use_mcp
        self._mcp_port = mcp_port
        self._mcp_base_url = f"http://localhost:{mcp_port}"
        logger.info("UITarsSubAgent 初始化完成 (mcp=%s, port=%d)", use_mcp, mcp_port)

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """同步调用入口 — 供 SubAgentRegistry.invoke() 使用."""
        task = input_data.get("task", input_data.get("message", ""))
        if not task:
            return {"error": "缺少 task 或 message 字段"}

        if self._use_mcp:
            return self._handle_via_mcp(task, input_data)
        return self._handle_via_cli(task, input_data)

    def _handle_via_cli(self, task: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过子进程调用 UI-TARS CLI."""
        timeout = input_data.get("timeout", 300)
        cmd_args = {
            "task": task,
            "model": input_data.get("model", ""),
            "maxSteps": input_data.get("max_steps", 20),
        }

        cmd = [self._cli_command] + self._cli_args + ["--json", json.dumps(cmd_args, ensure_ascii=False)]
        logger.info("UI-TARS CLI 调用: %s", " ".join(cmd[:4]))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=UITARS_PATH,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                logger.warning("UI-TARS CLI 退出码: %d, stderr: %s", result.returncode, result.stderr[:500])
                return {
                    "reply": result.stdout or "UI-TARS CLI 执行完成",
                    "exit_code": result.returncode,
                    "stderr": result.stderr[:500] if result.stderr else "",
                    "agent": self.NAME,
                }

            output = result.stdout.strip()
            try:
                parsed = json.loads(output)
                return {"reply": parsed, "agent": self.NAME}
            except json.JSONDecodeError:
                return {"reply": output, "agent": self.NAME}

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"UI-TARS CLI 超时 ({timeout}s)")
        except FileNotFoundError:
            raise RuntimeError(f"UI-TARS CLI 命令不存在: {self._cli_command}，请确保已安装 Node.js 和 @anthropic-ai/ui-tars")

    def _handle_via_mcp(self, task: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """通过 MCP HTTP 桥接调用 UI-TARS."""
        import requests

        timeout = input_data.get("timeout", 300)
        payload = {
            "jsonrpc": "2.0",
            "id": "aos-uitars-1",
            "method": "tools/call",
            "params": {
                "name": "gui_automation",
                "arguments": {
                    "task": task,
                    "max_steps": input_data.get("max_steps", 20),
                },
            },
        }

        try:
            resp = requests.post(
                f"{self._mcp_base_url}/mcp",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP 错误: {data['error']}")
            return {"reply": data.get("result", {}), "agent": self.NAME}
        except requests.ConnectionError:
            raise RuntimeError(f"无法连接 UI-TARS MCP Server ({self._mcp_base_url})，请确保已启动")

    @property
    def is_available(self) -> bool:
        """检查 UI-TARS 是否可用."""
        if self._use_mcp:
            try:
                import requests
                resp = requests.get(f"{self._mcp_base_url}/health", timeout=3)
                return resp.status_code == 200
            except Exception:
                return False
        # CLI 模式下检查 npx 是否可用
        try:
            subprocess.run(
                ["where" if sys.platform == "win32" else "which", self._cli_command],
                capture_output=True, timeout=5,
            )
            return True
        except Exception:
            return False
