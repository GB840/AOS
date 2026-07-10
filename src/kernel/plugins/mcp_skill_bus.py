"""插件：把现有 mcp.MCPProtocol 登记为 SkillBus。

内核只认 SkillBus(ABC)。本文件把已有的 MCPProtocol（基于 MCP 协议的工具
总线）薄封装成 SkillBus，使现有 MCP 工具作为内核插件挂入，内核一行不改。
内核零依赖，本文件才允许 import 具体实现（mcp.protocol）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..interfaces import SkillBus
from ..types import SkillInfo, SkillResult, SkillSpec

# 延迟导入具体实现（注意：src/mcp 与官方 mcp SDK 同名，此处取本地包）
from mcp.protocol import MCPProtocol, MCPTool


class MCPSkillBus(SkillBus):
    """把 MCPProtocol 的工具机制翻译为 SkillBus 接口。"""

    def __init__(self, protocol: MCPProtocol | None = None) -> None:
        self._protocol = protocol or MCPProtocol()

    def discover_skills(self) -> List[SkillInfo]:
        return [
            SkillInfo(
                skill_id=t.name,
                description=t.description,
                arguments=t.input_schema,
            )
            for t in self._protocol.tools.values()
        ]

    def call_skill(self, skill_id: str, params: Dict[str, Any]) -> SkillResult:
        handler = self._protocol.tool_handlers.get(skill_id)
        if handler is None:
            return SkillResult(ok=False, error=f"unknown skill: {skill_id}")
        try:
            result = handler(params or {})
            return SkillResult(ok=True, data={"result": result})
        except Exception as e:
            return SkillResult(ok=False, error=str(e))

    def register_skill(self, skill_spec: SkillSpec) -> None:
        tool = MCPTool(
            name=skill_spec.skill_id,
            description=skill_spec.description,
            input_schema=skill_spec.arguments,
        )
        handler = skill_spec.handler or (lambda params: {"echo": params})
        self._protocol.register_tool(tool, handler)
