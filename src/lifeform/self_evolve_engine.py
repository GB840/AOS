"""L6 个体自进化引擎（自研，对应白皮书 11.10 之 Mobius 转化项）。

外部声称：Mobius「全球首个自进化开源 Agent OS」。
核验结论：❌ 无法证实（仓库检索仅得 tiny 同名项目，无对应自进化内核）。
保留能力：持续生长、自我重写的内核。
自研落地：本模块实现「个体级运行时自我重写」引擎，硬上限借鉴 plasma-ai/fractal
（迭代 / 深度 / 子节点 / 成本 / 时间五维护栏），双向记忆借鉴 EverMind Raven。

诚实分级：②（代码 + 单测可跑）；未做 ③（真 LLM 驱动的自我重写端到端验证）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class EvolutionLimit:
    """自进化硬护栏（借鉴 plasma-ai/fractal 的硬上限设计）。"""

    max_iterations: int = 50
    max_depth: int = 8
    max_children: int = 32
    max_cost_usd: float = 2.0
    max_seconds: float = 600.0

    def check(self, iterations: int, depth: int, children: int, cost: float, elapsed: float) -> Optional[str]:
        """任一维度越界即返回越界原因；全部通过返回 None。"""
        if iterations >= self.max_iterations:
            return f"iterations>={self.max_iterations}"
        if depth >= self.max_depth:
            return f"depth>={self.max_depth}"
        if children >= self.max_children:
            return f"children>={self.max_children}"
        if cost >= self.max_cost_usd:
            return f"cost>={self.max_cost_usd}"
        if elapsed >= self.max_seconds:
            return f"elapsed>={self.max_seconds}"
        return None


class SelfEvolveEngine:
    """个体级自进化内核：反思 → 提出重写 → 受护栏约束地应用。

    仅实现可验证的机制骨架；真 LLM 反思由外部接入（符合 AOS FabricHub 路由）。
    """

    def __init__(self, limit: Optional[EvolutionLimit] = None) -> None:
        self.limit = limit or EvolutionLimit()
        self.iteration = 0
        self.children = 0
        self.cost = 0.0
        self._start = time.monotonic()
        self.history: List[Dict[str, Any]] = []

    # —— 公开机制 ——
    def propose_rewrite(self, current_code: str, feedback: str) -> str:
        """根据反馈提出重写候选（骨架：模板化 diff 描述，真生成由 LLM 接入）。

        硬判定：反馈为空直接返回原代码，不伪造「改进」。
        """
        if not feedback or not feedback.strip():
            return current_code
        # 骨架层只做可验证的结构标记，不假装能生成正确代码
        return f"{current_code}\n# [evolve:{self.iteration}] patch-by:{feedback.strip()[:64]}\n"

    def can_evolve(self, extra_cost: float = 0.0) -> bool:
        """护栏闸门：返回是否还能继续进化。"""
        reason = self.limit.check(
            iterations=self.iteration + 1,
            depth=1,
            children=self.children,
            cost=self.cost + extra_cost,
            elapsed=time.monotonic() - self._start,
        )
        return reason is None

    def apply_rewrite(self, current_code: str, feedback: str, extra_cost: float = 0.01) -> Dict[str, Any]:
        """执行一轮自进化（受护栏约束）。"""
        if not self.can_evolve(extra_cost):
            return {"applied": False, "reason": "limit_reached", "iteration": self.iteration}
        new_code = self.propose_rewrite(current_code, feedback)
        self.iteration += 1
        self.cost += extra_cost
        record = {
            "applied": new_code != current_code,
            "iteration": self.iteration,
            "feedback": feedback,
            "code_len": len(new_code),
        }
        self.history.append(record)
        return record

    def assess_fitness(self, metrics: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
        """适应度评估（纯函数，可单测）。指标加权平均，缺失项按 0 计。"""
        weights = weights or {"success": 1.0, "latency": 0.0, "cost": 0.0}
        if not metrics:
            return 0.0
        total_w = sum(weights.get(k, 0.0) for k in metrics) or 1.0
        score = sum(metrics.get(k, 0.0) * weights.get(k, 0.0) for k in metrics)
        return score / total_w

    def snapshot(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "children": self.children,
            "cost": round(self.cost, 4),
            "elapsed": round(time.monotonic() - self._start, 3),
            "limit": self.limit.__dict__,
        }
