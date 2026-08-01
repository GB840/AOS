"""L3 情感状态机：mood 真实影响决策权重（低落时降低冒险，白皮书 L3）。

与 L0 的 mood 字段对齐：L0 输出 mood，本模块把它映射为可消费的冒险权重。
"""
from __future__ import annotations


class EmotionState:
    def __init__(self, mood: float = 0.5):
        self.mood = max(0.0, min(1.0, mood))

    def risk_weight(self) -> float:
        """mood 0 -> 0.2，mood 1 -> 1.0，线性映射。"""
        return round(0.2 + 0.8 * self.mood, 4)

    def adjust_for(self, life_risk: float) -> float:
        """把 L0 的生命体自身冒险容忍度与本情绪权重叠加。"""
        return round(self.risk_weight() * max(0.0, life_risk), 4)
