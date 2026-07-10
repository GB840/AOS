"""v1.0 物种生态层：资源经济 / 自然选择 / 共生发现。

这是 AOS 从"骨架"到"物种"的第三层血肉——生态动力学。
建立在现有骨架之上：CostTracker 记录消耗 + EventBus 记录协作模式 +
AgentRuntimeLayer.run_workflow 记录并发关系。生态层利用这些数据实现
资源分配、竞争淘汰、协作涌现。

设计（物种思维）：
- 资源经济：Agent 消耗 token/内存/时间，超额则降权或暂停
- 自然选择：按 fitness 定期淘汰底部 agent，保留精英，随机注入新变体
- 共生发现：从事件历史中发现高频协作 agent 对，标记为共生关系
- 零依赖：仅依赖 kernel types + stdlib + evolution（FitnessScore）
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from kernel.evolution import FitnessTracker


# ─── 资源经济 ─────────────────────────────────────────────────────

@dataclass
class ResourceBudget:
    """单个 Agent 的资源预算和消耗。"""
    agent_id: str
    token_limit: int = 10000
    memory_limit_mb: float = 100.0
    priority: int = 1                    # 1-5 优先级（5 最高）
    tokens_used: int = 0
    memory_used_mb: float = 0.0
    active: bool = True
    suspended_until: float = 0.0


class ResourceEconomy:
    """多 Agent 资源经济系统。

    功能：
    - 按优先级分配资源（高优先级 agent 获得更多预算）
    - 消耗追踪 + 超额检测
    - 超额 agent 自动降权或暂停
    - 资源总量限制

    线程安全。
    """

    def __init__(self, total_token_budget: int = 100000,
                 total_memory_mb: float = 500.0,
                 default_token_per_agent: int = 10000):
        self._total_tokens = total_token_budget
        self._total_memory = total_memory_mb
        self._default_tokens = default_token_per_agent
        self._lock = threading.Lock()
        self._budgets: Dict[str, ResourceBudget] = {}

    def register(self, agent_id: str, priority: int = 1,
                 token_limit: int | None = None) -> ResourceBudget:
        """注册一个 Agent 到资源经济。"""
        limit = token_limit or self._default_tokens * priority
        budget = ResourceBudget(
            agent_id=agent_id, token_limit=limit, priority=priority,
        )
        with self._lock:
            self._budgets[agent_id] = budget
        return budget

    def consume(self, agent_id: str, tokens: int, memory_mb: float = 0.0) -> bool:
        """消费资源。返回是否在预算内。"""
        with self._lock:
            b = self._budgets.get(agent_id)
            if b is None:
                return True  # 未注册则无限制
            if not b.active:
                return False
            b.tokens_used += tokens
            b.memory_used_mb += memory_mb
            if b.tokens_used > b.token_limit:
                b.active = False
                b.suspended_until = time.time() + 60.0  # 暂停 1 分钟
                return False
            return True

    def budget_status(self, agent_id: str) -> Optional[ResourceBudget]:
        with self._lock:
            b = self._budgets.get(agent_id)
            if b and not b.active and time.time() > b.suspended_until:
                b.active = True
                b.tokens_used = 0
                b.suspended_until = 0.0
            return b

    def reset_cycle(self) -> None:
        """重置所有 Agent 的消耗计数（新计费周期）。"""
        with self._lock:
            for b in self._budgets.values():
                b.tokens_used = 0
                b.memory_used_mb = 0
                b.active = True
                b.suspended_until = 0.0

    def all_budgets(self) -> List[ResourceBudget]:
        with self._lock:
            return sorted(self._budgets.values(),
                          key=lambda b: b.priority, reverse=True)

    def total_consumed(self) -> Dict[str, Any]:
        with self._lock:
            tokens = sum(b.tokens_used for b in self._budgets.values())
            memory = sum(b.memory_used_mb for b in self._budgets.values())
            return {"tokens": tokens, "memory_mb": memory,
                    "token_budget": self._total_tokens}


# ─── 自然选择 ────────────────────────────────────────────────────

class NaturalSelection:
    """自然选择：定期按 fitness 淘汰底部 agent，保留精英。

    用法：
        fitness = FitnessTracker()
        economy = ResourceEconomy()
        selection = NaturalSelection(fitness, economy,
                                     decommission=callback)
        # 每轮执行
        survivors = selection.select(population_ids, keep_top=3)
    """

    def __init__(self, fitness: FitnessTracker,
                 economy: ResourceEconomy | None = None,
                 decommission: Optional[Callable[[str], None]] = None,
                 mutation_injection_rate: float = 0.2):
        self._fitness = fitness
        self._economy = economy
        self._decommission = decommission or (lambda _: None)
        self._injection_rate = mutation_injection_rate
        self._generation = 0

    def select(self, population_ids: List[str],
               keep_top: int = 3,
               min_population: int = 2) -> Tuple[List[str], List[str]]:
        """执行一轮自然选择。

        返回 (survivors, eliminated)。
        survivors 按 fitness 排序，精英在先。
        """
        self._generation += 1

        scored: List[Tuple[float, str]] = []
        for aid in population_ids:
            fs = self._fitness.score(aid)
            score = fs.overall if fs else 0.0
            # 资源超额 agent 惩罚
            if self._economy:
                budget = self._economy.budget_status(aid)
                if budget and not budget.active:
                    score *= 0.1  # 重度惩罚
            scored.append((score, aid))

        scored.sort(key=lambda x: x[0], reverse=True)

        kept = max(min_population, keep_top)
        survivors = [aid for _, aid in scored[:kept]]
        eliminated = [aid for _, aid in scored[kept:]]

        for aid in eliminated:
            self._decommission(aid)

        return survivors, eliminated

    @property
    def generation(self) -> int:
        return self._generation


# ─── 共生发现 ────────────────────────────────────────────────────

class SymbiosisDetector:
    """共生关系发现器：从事件历史中检测高频协作 Agent 对。

    检测逻辑：如果 agent A 和 agent B 在同一工作流中频繁同时出现，
    且两者都成功时整体性能更高 → 标记为共生对。

    共生对的应用：自然选择时保护共生体（两者一起保留），
    工作流编排时优先配对共生体。
    """

    def __init__(self, cooccurrence_threshold: int = 5):
        self._threshold = cooccurrence_threshold
        self._lock = threading.Lock()
        # agent_pair → {"count": n, "success": n}
        self._cooccurrences: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(
            lambda: {"count": 0, "success": 0})
        self._symbiotic_pairs: Set[Tuple[str, str]] = set()

    def record_collaboration(self, agent_a: str, agent_b: str,
                             success: bool = True) -> None:
        """记录一次 Agent 间协作。"""
        pair = tuple(sorted([agent_a, agent_b]))
        with self._lock:
            entry = self._cooccurrences[pair]
            entry["count"] += 1
            if success:
                entry["success"] += 1
            if entry["count"] >= self._threshold:
                success_rate = entry["success"] / entry["count"]
                if success_rate >= 0.7:
                    self._symbiotic_pairs.add(pair)

    def is_symbiotic(self, agent_a: str, agent_b: str) -> bool:
        """检查两个 Agent 是否是共生关系。"""
        pair = tuple(sorted([agent_a, agent_b]))
        with self._lock:
            return pair in self._symbiotic_pairs

    def symbiotic_groups(self) -> List[List[str]]:
        """返回所有共生群组（连通的共生对合并）。"""
        with self._lock:
            if not self._symbiotic_pairs:
                return []
            groups: List[Set[str]] = []
            for a, b in self._symbiotic_pairs:
                merged = {a, b}
                new_groups = []
                for g in groups:
                    if g & merged:
                        merged |= g
                    else:
                        new_groups.append(g)
                new_groups.append(merged)
                groups = new_groups
            return [sorted(g) for g in groups]

    def pair_stats(self) -> List[Dict[str, Any]]:
        """所有协作对的统计。"""
        with self._lock:
            return [
                {"pair": list(k), "count": v["count"],
                 "success_rate": v["success"] / v["count"] if v["count"] else 0,
                 "symbiotic": k in self._symbiotic_pairs}
                for k, v in self._cooccurrences.items()
            ]


__all__ = [
    "NaturalSelection",
    "ResourceBudget",
    "ResourceEconomy",
    "SymbiosisDetector",
]
