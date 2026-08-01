"""L2 柔性目标演化引擎 —— 完全自研核心（生命体OS 白皮书 L2H）。

目标随成败/时效自动升维(promote)/降级(demote)/搁置(shelve)/置换(swap)。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PROMOTED = "promoted"
    DEMOTED = "demoted"
    SHELVED = "shelved"
    SWAPPED = "swapped"


@dataclass
class Goal:
    text: str
    priority: float = 0.5
    successes: int = 0
    failures: int = 0
    age: int = 0
    status: GoalStatus = GoalStatus.ACTIVE


class GoalEvolution:
    """柔性目标演化：目标不是写死的，会随真实成败自然流动。"""

    def evolve(self, goals: List[Goal], outcome: Optional[dict] = None) -> List[Goal]:
        """根据最近一次 outcome 演化目标队列。

        outcome: {"text": str, "ok": bool}
        """
        if outcome:
            for g in goals:
                if g.text == outcome.get("text"):
                    if outcome.get("ok"):
                        g.successes += 1
                        g.priority = min(1.0, g.priority + 0.1)
                        if g.priority >= 0.9:
                            g.status = GoalStatus.PROMOTED
                    else:
                        g.failures += 1
                        g.priority = max(0.0, g.priority - 0.15)
                        if g.failures >= 3:
                            g.status = GoalStatus.SHELVED
        # 时效老化：长期未动 → 降权/置换
        for g in goals:
            g.age += 1
            if g.age >= 10 and g.status == GoalStatus.ACTIVE:
                g.priority = max(0.0, g.priority - 0.05)
                if g.priority <= 0.1:
                    g.status = GoalStatus.SWAPPED
        return goals
