"""
intent_skill_router.py —— Skill 化意图路由（② 级轻量原型）

借鉴来源：OpenHarmony 小艺 **HMAF 2.0**
（系统能力 **Skill 化** + **意图即服务** + **MCP 兼容工具**）。
对齐 AOS 现有：OPC 五岗位 + SkillManage + MCP 连接器 + FabricHub 统一路由。

诚实边界（必读）：
- 原型骨架：意图 → Skill 的本地前缀匹配，不接真 LLM 意图理解，
  不拉真实 MCP 服务。仅验证「意图即服务」控制流（② 级）。
- 不等同 OpenHarmony 在 2000+ 鸿蒙智能体上的端云 A2A / 系统鉴权能力（③ 级）。
- 生产化路径：把 `route()` 的前缀匹配换成 FabricHub 统一路由的
  语义/向量意图理解，把 `mcp_tools()` 接真实 MCP 连接器即可对齐。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class Skill:
    """系统能力 Skill 化单元（可暴露为 MCP 工具）。"""

    name: str
    intent_prefix: str  # 意图前缀，用于「意图即服务」路由
    handler: Callable[..., str]
    mcp_compatible: bool = True


class IntentSkillRouter:
    """意图即服务路由器（原型）。

    对齐 OpenHarmony 的「系统能力 Skill 化 + 意图即服务分发 + MCP 兼容」：
    把用户/系统意图按前缀路由到对应 Skill，并暴露 MCP 工具清单。
    """

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def route(self, intent: str) -> Optional[Skill]:
        """意图即服务：按意图前缀匹配 Skill（最长前缀优先）。"""
        best: Optional[Skill] = None
        best_len = -1
        for sk in self._skills.values():
            if intent.startswith(sk.intent_prefix) and len(sk.intent_prefix) > best_len:
                best, best_len = sk, len(sk.intent_prefix)
        return best

    def mcp_tools(self) -> List[Dict[str, str]]:
        """兼容 MCP 的工具清单（供 MCP 连接器消费）。"""
        return [
            {"name": s.name, "intent": s.intent_prefix}
            for s in self._skills.values()
            if s.mcp_compatible
        ]

    def dispatch(self, intent: str, **kwargs: str) -> str:
        sk = self.route(intent)
        if sk is None:
            raise LookupError(f"无匹配 Skill 的意图：{intent}")
        return sk.handler(**kwargs)
