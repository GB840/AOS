"""L2 生命节律调度 —— 完全自研核心（生命体OS 白皮书 L2C）。

四模式：active / rest / deep_sleep / review
由 L0 生命状态（energy/debt）与时间共同驱动。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["active", "rest", "deep_sleep", "review"]


@dataclass
class RhythmDecision:
    mode: Mode
    reason: str


class RhythmScheduler:
    """生命节律：让系统像生命一样有活跃/休整/休眠/复盘节律。"""

    def __init__(self, energy_rest: float = 0.2, debt_sleep: float = 0.8):
        self.energy_rest = energy_rest
        self.debt_sleep = debt_sleep

    def tick(self, energy: float, debt: float, hour: int) -> RhythmDecision:
        # 深夜（0~6）→ 深度休眠
        if 0 <= hour < 6:
            return RhythmDecision("deep_sleep", "深夜时段，进入深度休眠")
        # 技术债过高 → 深度休眠回收资源
        if debt >= self.debt_sleep:
            return RhythmDecision("deep_sleep", f"技术债 {debt:.2f}≥阈值，回收资源")
        # 能量过低 → 休整
        if energy < self.energy_rest:
            return RhythmDecision("rest", f"能量 {energy:.2f}<阈值，休整恢复")
        # 日终（22~24）→ 复盘
        if 22 <= hour < 24:
            return RhythmDecision("review", "日终复盘时段")
        # 默认活跃
        return RhythmDecision("active", "能量充足，进入活跃执行")
