"""L6 行动规划仲裁器 —— 完全自研核心（生命体OS 白皮书 L6D）。

分级审核：低风险自动放行；中风险标记需确认；高风险永久禁止全自动。
宪法优先：任何可能造成人身/财产伤害的规划，直接拦截（不可配置放行）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

Risk = Literal["low", "mid", "high"]


class Verdict(str, Enum):
    AUTO = "auto"          # 自动放行
    CONFIRM = "confirm"    # 需人类确认
    BLOCK = "block"        # 拦截


@dataclass
class ActionPlan:
    description: str
    risk: Risk
    physical: bool = False        # 是否涉及物理世界执行
    harm_potential: bool = False  # 是否可能造成人身/财产伤害


class ActionArbiter:
    """行动仲裁：物理世界安全闸门，分级 + 宪法优先。"""

    def judge(self, plan: ActionPlan) -> Verdict:
        # 宪法优先：潜在伤害永远拦截（不可配置放行）
        if plan.harm_potential:
            return Verdict.BLOCK
        # 物理世界执行，中高风险一律需确认/拦截
        if plan.physical and plan.risk in ("mid", "high"):
            return Verdict.BLOCK if plan.risk == "high" else Verdict.CONFIRM
        # 纯数字低风险自动放行；中风险需确认
        if plan.risk == "low":
            return Verdict.AUTO
        return Verdict.CONFIRM
