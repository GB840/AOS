"""v1.0 物种进化层：Agent DNA / 变异 / Fitness / 育种。

这是 AOS 从"骨架"到"物种"的核心——自进化能力。
每个 Agent 拥有一组 DNA（基因组），可以通过变异产生新特征，
通过 Fitness 被自然选择，通过育种产生下一代。

设计（物种思维）：
- DNA 是 Agent 的"遗传物质"：包含 capabilities/model/temperature/system_prompt 等可遗传特征
- 变异算子：交叉（取双亲特征混合）、扰动（小幅调参）、随机（探索新区域）
- Fitness 函数：三维评分（延迟权重 / 成功率 / 成本效率）
- 育种器：选亲 → 交叉变异 → 孵化新 Agent → 注册进内核

零依赖：仅依赖 kernel.types + stdlib。
"""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kernel.types import AgentSpec


# ─── Agent DNA — 基因组 ──────────────────────────────────────────

@dataclass
class Gene:
    """基因：一个可遗传和可变异的值。

    变异规则（per-gene）：
    - discrete: 从 options 列表中按概率随机切换
    - continuous: 在当前值 ± range 范围内随机扰动
    - immutable: 不可变异（如 agent_id）
    """
    name: str
    value: Any
    mutation_type: str = "discrete"
    options: List[Any] = field(default_factory=list)
    mutation_probability: float = 0.15
    continuous_range: float = 0.0   # 连续型基因的扰动范围
    immutable: bool = False


@dataclass
class AgentDNA:
    """Agent 的完整基因组。

    所有可遗传和可变异的特征，编码为 Gene 列表。
    支持交叉（取两个 DNA 的混合）、变异（对单个基因应用随机改变）、
    克隆（深度复制）。
    """
    genes: List[Gene]
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)
    mutation_history: List[str] = field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: AgentSpec) -> AgentDNA:
        """从 AgentSpec 解码 DNA。"""
        genes = [
            Gene("agent_id", spec.agent_id, immutable=True),
            Gene("engine", spec.engine, "discrete",
                 options=["litellm", "openclaw", "hermes", "ag2", "deerflow"]),
            Gene("capabilities", spec.capabilities, "discrete",
                 options=_cap_options(spec.capabilities)),
            Gene("version", spec.version),
        ]
        for k, v in spec.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                genes.append(Gene(k, v))
        return cls(genes=genes)

    def to_spec(self) -> AgentSpec:
        """编码回 AgentSpec。"""
        agent_id = self._gene_value("agent_id", "evo-" + str(random.randint(1000, 9999)))
        engine = self._gene_value("engine", "litellm")
        capabilities = self._gene_value("capabilities", ["chat"])
        version = self._gene_value("version", "0.1.0")
        metadata = {}
        for g in self.genes:
            if g.name not in ("agent_id", "engine", "capabilities", "version"):
                metadata[g.name] = g.value
        return AgentSpec(
            agent_id=agent_id,
            name=f"Gen{self.generation}-{agent_id}",
            engine=engine,
            capabilities=capabilities,
            version=version,
            metadata=metadata,
        )

    def _gene_value(self, name: str, default: Any) -> Any:
        for g in self.genes:
            if g.name == name:
                return g.value
        return default

    # ── 变异 ──
    def mutate(self) -> AgentDNA:
        """对基因组进行一次随机变异，返回新 DNA（原 DNA 不变）。"""
        child = self.clone()
        child.generation = self.generation + 1
        child.parent_ids = [f"{self.generation}"]
        mutated = []
        for i, gene in enumerate(child.genes):
            if gene.immutable:
                continue
            if random.random() < gene.mutation_probability:
                new_val = _apply_mutation(gene)
                if new_val is not None:
                    child.genes[i] = Gene(
                        name=gene.name, value=new_val,
                        mutation_type=gene.mutation_type,
                        options=gene.options,
                        mutation_probability=gene.mutation_probability,
                        continuous_range=gene.continuous_range,
                    )
                    mutated.append(gene.name)
        child.mutation_history = self.mutation_history + [f"mut:{','.join(mutated)}"]
        return child

    def crossover(self, other: AgentDNA) -> AgentDNA:
        """与另一个 DNA 交叉：随机取每个基因的来源，产生子代。"""
        child_genes = []
        for g1 in self.genes:
            g2 = next((g for g in other.genes if g.name == g1.name), None)
            winner = g1 if random.random() < 0.5 else (g2 or g1)
            child_genes.append(deepcopy(winner))
        child = AgentDNA(
            genes=child_genes,
            generation=max(self.generation, other.generation) + 1,
            parent_ids=[f"gen{self.generation}", f"gen{other.generation}"],
            mutation_history=[],
        )
        return child.mutate()  # 交叉后必然轻微变异（引入多样性）

    def clone(self) -> AgentDNA:
        return AgentDNA(
            genes=deepcopy(self.genes),
            generation=self.generation,
            parent_ids=list(self.parent_ids),
            mutation_history=list(self.mutation_history),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "genes": {g.name: g.value for g in self.genes},
            "generation": self.generation,
            "parent_ids": self.parent_ids,
        }


def _apply_mutation(gene: Gene) -> Optional[Any]:
    if gene.mutation_type == "discrete" and gene.options:
        return random.choice(gene.options)
    elif gene.mutation_type == "continuous" and isinstance(gene.value, (int, float)):
        delta = gene.value * gene.continuous_range * random.uniform(-1, 1)
        return gene.value + delta
    elif gene.mutation_type == "random":
        return random.uniform(0, gene.continuous_range or 1.0)
    return None


def _cap_options(current: List[str]) -> List[str]:
    base = ["chat", "code", "browser", "search", "image", "audio", "video", "data"]
    if not current:
        return base
    return list(set(base + current))


# ─── Fitness 评分 ────────────────────────────────────────────────

@dataclass
class FitnessScore:
    """三维 Fitness 评分。"""
    agent_id: str
    generation: int = 0
    success_rate: float = 0.5       # 成功率 0-1
    latency_score: float = 0.5      # 延迟评分 0-1（越短越高）
    cost_efficiency: float = 0.5    # 成本效率 0-1（越省越高）
    tasks_completed: int = 0
    overall: float = 0.0

    def __post_init__(self):
        # 综合评分：成功率 40% + 延迟 30% + 成本 30%
        self.overall = (
            0.4 * self.success_rate +
            0.3 * self.latency_score +
            0.3 * self.cost_efficiency
        )


class FitnessTracker:
    """Agent Fitness 追踪器：记录每个 agent 的性能统计，计算三维评分。

    用法：
        ft = FitnessTracker()
        ft.record_success("a1", latency=0.5, tokens=100)
        ft.record_failure("a1")
        print(ft.score("a1"))  # FitnessScore
        top = ft.top_agents(n=5)  # 按 overall 排序
    """

    def __init__(self):
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._latency_baseline = 2.0
        self._token_baseline = 500

    def record_success(self, agent_id: str, latency: float = 0.0,
                       tokens: int = 0, generation: int = 0) -> None:
        s = self._ensure(agent_id, generation)
        s["successes"] += 1
        s["total_latency"] += latency
        s["total_tokens"] += tokens
        s["tasks"] += 1

    def record_failure(self, agent_id: str, generation: int = 0) -> None:
        s = self._ensure(agent_id, generation)
        s["failures"] += 1
        s["tasks"] += 1

    def score(self, agent_id: str) -> Optional[FitnessScore]:
        s = self._stats.get(agent_id)
        if s is None or s["tasks"] == 0:
            return None
        total = s["tasks"]
        success_rate = s["successes"] / total
        avg_latency = s["total_latency"] / total if total > 0 else self._latency_baseline
        latency_score = max(0.0, 1.0 - avg_latency / self._latency_baseline)
        avg_tokens = s["total_tokens"] / total if total > 0 else self._token_baseline
        cost_eff = max(0.0, 1.0 - avg_tokens / self._token_baseline)
        return FitnessScore(
            agent_id=agent_id, generation=s.get("generation", 0),
            success_rate=success_rate, latency_score=latency_score,
            cost_efficiency=cost_eff, tasks_completed=total,
        )

    def top_agents(self, n: int = 5) -> List[FitnessScore]:
        scores = []
        for aid in self._stats:
            s = self.score(aid)
            if s:
                scores.append(s)
        scores.sort(key=lambda x: x.overall, reverse=True)
        return scores[:n]

    def bottom_agents(self, n: int = 5) -> List[FitnessScore]:
        scores = []
        for aid in self._stats:
            s = self.score(aid)
            if s:
                scores.append(s)
        scores.sort(key=lambda x: x.overall)
        return scores[:n]

    def all_scores(self) -> List[FitnessScore]:
        return [s for aid in self._stats if (s := self.score(aid))]

    def _ensure(self, agent_id: str, gen: int) -> Dict[str, Any]:
        if agent_id not in self._stats:
            self._stats[agent_id] = {
                "successes": 0, "failures": 0, "total_latency": 0.0,
                "total_tokens": 0, "tasks": 0, "generation": gen,
            }
        return self._stats[agent_id]


# ─── 育种器 ──────────────────────────────────────────────────────

class Breeder:
    """进化育种器：选亲 → 交叉变异 → 孵化新 Agent。

    用法：
        ft = FitnessTracker()
        breeder = Breeder(ft)
        # 记录几轮表现
        ft.record_success("a1", 0.3, 100)
        ft.record_failure("a2")
        # 育种：选 top 2 交叉 + 变异 → 产生 3 个子代
        specs = breeder.breed(population=[dna1, dna2], offspring_count=3)
    """

    def __init__(self, fitness: FitnessTracker,
                 crossover_rate: float = 0.7,
                 elite_count: int = 1):
        self._fitness = fitness
        self._crossover_rate = crossover_rate
        self._elite_count = elite_count

    def breed(self, population: List[AgentDNA],
              offspring_count: int = 3) -> List[AgentDNA]:
        """从种群中育种，返回子代 DNA 列表。"""
        if len(population) < 2:
            return [d.mutate() for d in population]

        # 选亲：按 fitness 排序，取 top 作为精英池
        scored = []
        for dna in population:
            aid = dna._gene_value("agent_id", "unknown")
            fs = self._fitness.score(aid)
            score = fs.overall if fs else 0.0
            scored.append((score, dna))
        scored.sort(key=lambda x: x[0], reverse=True)

        elite = scored[:max(1, len(scored) // 2)]
        offspring: List[AgentDNA] = []

        # 精英保留
        for i in range(min(self._elite_count, len(elite))):
            offspring.append(elite[i][1].mutate())

        # 交叉 + 变异 产生子代
        while len(offspring) < offspring_count:
            if len(elite) >= 2 and random.random() < self._crossover_rate:
                p1 = random.choice(elite)[1]
                p2 = random.choice(elite)[1]
                child = p1.crossover(p2)
            else:
                child = random.choice(elite)[1].mutate()
            offspring.append(child)

        return offspring[:offspring_count]

    def evolve_generation(self, population: List[AgentDNA],
                          generations: int = 1,
                          population_size: int = 5) -> List[AgentDNA]:
        """多代进化：反复选亲→育种→替换，返回最终种群。"""
        pop = list(population)
        for _ in range(generations):
            pop = self.breed(pop, offspring_count=population_size)
        return pop


__all__ = [
    "AgentDNA",
    "Breeder",
    "FitnessScore",
    "FitnessTracker",
    "Gene",
]
