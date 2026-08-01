"""L2 内生欲望引擎 —— 完全自研核心（生命体OS 白皮书 L2B）。

不靠外部指令，基于好奇心 + 认知缺口自主生成目标队列。
能量（来自 L0 生命状态）低于阈值时，只产出低成本目标，避免"累死"。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class GoalCandidate:
    text: str
    cost: float          # 预估资源成本 0~1
    source: str          # curiosity / cognitive_gap / maintenance
    novelty: float       # 新鲜度 0~1
    created_at: float = field(default_factory=time.time)


class DesireEngine:
    """内生欲望引擎：把"我想做什么"从被动响应变成主动涌现。"""

    def __init__(self, energy_floor: float = 0.25):
        self.energy_floor = energy_floor

    def propose(
        self,
        energy: float,
        recent_goals: List[str],
        memory_gaps: List[str],
        failed_topics: List[str],
    ) -> List[GoalCandidate]:
        """生成候选目标队列。

        energy: 来自 life_state 的能量 0~1
        recent_goals: 最近已做目标文本（去重/降温）
        memory_gaps: 已知认知缺口（如"不会 X"）
        failed_topics: 近期失败主题（认知缺口驱动换思路重试）
        """
        cands: List[GoalCandidate] = []
        # 1) 好奇心：认知缺口 → 探索
        for g in memory_gaps:
            cands.append(GoalCandidate(
                text=f"学习并掌握：{g}", cost=0.4,
                source="curiosity", novelty=0.9))
        # 2) 认知缺口驱动的重试（失败即训练：换做法而非原地重跑）
        for t in failed_topics:
            if t not in recent_goals:
                cands.append(GoalCandidate(
                    text=f"换思路重试：{t}", cost=0.5,
                    source="cognitive_gap", novelty=0.6))
        # 3) 维护型（低 novelty，保持系统运行）
        cands.append(GoalCandidate(
            text="整理今日记忆与反思", cost=0.1,
            source="maintenance", novelty=0.1))

        # 能量门控：低于 floor 只保留低成本目标（知道累不累）
        if energy < self.energy_floor:
            cands = [c for c in cands if c.cost <= 0.15]
        # 去重：剔除最近刚做过的
        cands = [c for c in cands if c.text not in recent_goals]
        # 排序：高新鲜 / 低成本的优先
        cands.sort(key=lambda c: c.novelty / max(c.cost, 0.05), reverse=True)
        return cands
