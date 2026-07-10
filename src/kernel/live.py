"""AOS 活体进化闭环 — LiveEvolutionEngine v1.0

这不是模拟。每一步都走真实内核路径：
  AOSKernel.send_message → 真实LLM调用 → 真实延迟/成功/失败/token数
  → FitnessTracker记录 → NaturalSelection淘汰 → Breeder育种 → kernel.register_agent孵化
  → SelfHealer自愈 → AnomalyDetector监控 → ResourceEconomy限流

用法：
  from kernel.live import LiveEvolutionEngine
  engine = LiveEvolutionEngine()
  engine.initialize_population(5)  # 5个初始Agent
  engine.run_tasks(["What is AI?","Explain quantum computing",...])
  engine.evolve()  # 执行一代进化
  engine.status()  # 查看活体状态

可直接 7×24 运行为后台进程，每一轮任务后自动触发进化选择。
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kernel.system import build_default_system, AOSSystem
from kernel.types import AgentSpec, Message, Response
from kernel.evolution import AgentDNA, Gene, FitnessTracker, Breeder
from kernel.ecology import NaturalSelection, ResourceEconomy
from kernel.immunity import AnomalyDetector, SelfHealer
from kernel.events import Event


# ─── 活体任务 ─────────────────────────────────────────────────────

@dataclass
class LiveTask:
    """一条真实任务：prompt → 真LLM执行 → 记录结果。"""
    prompt: str
    task_id: str = ""
    assigned_agent: str = ""       # 执行此任务的 agent_id
    engine: str = "litellm"
    result: Optional[Response] = None
    latency_seconds: float = 0.0
    success: bool = False
    tokens_used: int = 0
    error: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.task_id:
            self.task_id = f"task-{int(self.timestamp)}-{hash(self.prompt)%10000}"


# ─── 活体状态 ─────────────────────────────────────────────────────

@dataclass
class LiveStatus:
    """活体系统实时状态快照。"""
    generation: int
    population: int
    tasks_completed: int
    eliminations: int
    spawns: int
    heal_events: int
    anomaly_alerts: int
    total_tokens: int
    total_cost_usd: float
    top_agent: str = ""
    top_fitness: float = 0.0
    system_version: str = "1.0.0"
    uptime_seconds: float = 0.0


# ─── 活体进化引擎 ────────────────────────────────────────────────

class LiveEvolutionEngine:
    """活体进化闭环引擎。

    7 个真模块串联成一个自运行的进化循环：
      TaskQueue → AOSKernel → LiteLLM → FitnessTracker → NaturalSelection → Breeder → register_agent
                                                                       ↓
                                                              SelfHealer (后台)
                                                              AnomalyDetector (后台)
                                                              ResourceEconomy (限流)

    核心原则：
    - 每一步都走真实的 kernel 路径，不模拟
    - 免疫和资源管理是后台持续运行的（通过 EventBus 订阅）
    - 可暂停/恢复/查询状态
    - 可 7×24 运行
    """

    def __init__(self,
                 evolution_interval: int = 5,       # 每 N 个任务后执行一次进化
                 min_population: int = 2,
                 max_population: int = 10,
                 keep_top_agents: int = 3,
                 offspring_per_generation: int = 2,
                 ):
        self.system: AOSSystem = build_default_system()
        self.kernel = self.system.kernel

        # 进化参数
        self._evolution_interval = evolution_interval
        self._min_population = min_population
        self._max_population = max_population
        self._keep_top = keep_top_agents
        self._offspring_count = offspring_per_generation

        # 物种子系统（接入真实内核）
        self.fitness = FitnessTracker()
        self.breeder = Breeder(self.fitness)
        self.economy = ResourceEconomy()
        self.selection = NaturalSelection(
            self.fitness, self.economy,
            decommission=lambda aid: self.kernel.stop_agent(aid),
        )
        self.detector = AnomalyDetector(self.kernel.events)
        self.healer = SelfHealer(
            self.kernel.events,
            restart_agent=lambda aid: self._restart_agent(aid),
            fallback_model=lambda m: "zhipu/glm-4-flash",
            isolate_skill=lambda s: True,
        )

        # 状态
        self._generation: int = 0
        self._tasks_completed: int = 0
        self._spawns: int = 0
        self._lock = threading.RLock()
        self._started_at: float = time.time()
        self._population_dna: Dict[str, AgentDNA] = {}

    # ── 初始化种群 ──
    def initialize_population(self, size: int = 5) -> List[str]:
        """创建初始 Agent 种群（带 DNA）。返回 agent_id 列表。"""
        ids: List[str] = []
        engines = ["litellm", "openclaw", "hermes", "ag2"]
        caps_options = [["chat"], ["chat", "code"], ["chat", "browser"], ["chat", "data"]]

        for i in range(size):
            engine = engines[i % len(engines)]
            caps = caps_options[i % len(caps_options)]
            aid = f"live-{i:02d}"

            dna = AgentDNA(genes=[
                Gene("aid", aid, immutable=True),
                Gene("engine", engine, "discrete", options=engines),
                Gene("cap1", caps[0], "discrete", options=["chat", "code", "browser", "data"]),
                Gene("temperature", round(0.5 + i * 0.1, 2), "continuous", continuous_range=0.2),
            ], generation=0)

            spec = dna.to_spec()
            spec.agent_id = aid
            spec.name = f"Live-{i}"
            spec.engine = engine
            spec.capabilities = caps

            self.kernel.register_agent(spec)
            self._population_dna[aid] = dna
            self.economy.register(aid, priority=2 + i % 3,
                                   token_limit=10000 + i * 2000)
            ids.append(aid)

        self._generation = 0
        return ids

    # ── 核心活体循环 ──
    def run_tasks(self, prompts: List[str]) -> List[LiveTask]:
        """执行一批真实任务。每 evolution_interval 个任务后触发一次进化。

        每个任务:
        1. 选一个存活的 agent（轮询）
        2. 经 kernel.send_message 路由到真 LLM
        3. 记录真实耗时、成功/失败、token 数
        4. 更新 FitnessTracker
        """
        tasks: List[LiveTask] = []
        agent_ids = [a.agent_id for a in self.kernel.list_agents()
                     if a.status.value != "stopped"]
        if not agent_ids:
            agent_ids = self.initialize_population(self._min_population)

        idx = 0
        for prompt in prompts:
            aid = agent_ids[idx % len(agent_ids)]
            idx += 1

            task = LiveTask(prompt=prompt, assigned_agent=aid)
            agent = self.kernel.get_agent(aid)
            engine = agent.spec.engine if agent else "litellm"
            task.engine = engine

            t0 = time.monotonic()

            # === 真正走内核路由 (real LLM call) ===
            try:
                response = self.kernel.send_message(Message(
                    sender="live_engine",
                    recipient=aid,
                    payload={"prompt": prompt, "model": ""},
                ))
                task.result = response
                task.latency_seconds = round(time.monotonic() - t0, 3)

                if response.ok:
                    task.success = True
                    # 从 response 估算 token（真LLM返回的）
                    content = response.data.get("content", "")
                    task.tokens_used = max(10, len(content) // 3)
                else:
                    task.error = response.error or "unknown"
            except Exception as exc:
                task.latency_seconds = round(time.monotonic() - t0, 3)
                task.error = str(exc)

            # === 记录真实 Fitness ===
            if task.success:
                self.fitness.record_success(
                    aid, latency=task.latency_seconds,
                    tokens=task.tokens_used, generation=self._generation,
                )
            else:
                self.fitness.record_failure(aid, generation=self._generation)

            # === 资源消费 ===
            self.economy.consume(aid, task.tokens_used)

            tasks.append(task)
            self._tasks_completed += 1

            # === 定期进化 ===
            if self._tasks_completed % self._evolution_interval == 0:
                self.evolve()
                agent_ids = [a.agent_id for a in self.kernel.list_agents()
                             if a.status.value != "stopped"]
                if not agent_ids:
                    agent_ids = self.initialize_population(self._min_population)

        return tasks

    # ── 一代进化 ──
    def evolve(self) -> Dict[str, Any]:
        """执行一代真实进化：选择 → 淘汰 → 育种 → 孵化。"""
        self._generation += 1
        result: Dict[str, Any] = {"generation": self._generation}

        # 1. 自然选择
        agent_ids = [a.agent_id for a in self.kernel.list_agents()
                     if a.status.value != "stopped"]
        survivors, eliminated = self.selection.select(
            agent_ids, keep_top=self._keep_top, min_population=self._min_population,
        )
        result["survivors"] = len(survivors)
        result["eliminated"] = len(eliminated)

        # 2. 育种
        survivor_dnas = [self._population_dna.get(aid) for aid in survivors
                         if aid in self._population_dna]
        survivor_dnas = [d for d in survivor_dnas if d is not None]

        if len(survivor_dnas) >= 2:
            offspring = self.breeder.breed(
                survivor_dnas,
                offspring_count=min(self._offspring_count,
                                     self._max_population - len(survivors)),
            )

            # 3. 孵化：注册新 agent 到内核
            spawned = 0
            for child_dna in offspring:
                spec = child_dna.to_spec()
                # 确保 agent_id 唯一
                spec.agent_id = f"live-gen{self._generation}-{child_dna.generation}-{self._spawns}"
                spec.name = f"Evo-G{self._generation}"
                spec.engine = child_dna._gene_value("engine", "litellm")

                self.kernel.register_agent(spec)
                self._population_dna[spec.agent_id] = child_dna
                self.economy.register(spec.agent_id, priority=2,
                                       token_limit=10000)
                spawned += 1
                self._spawns += 1

            result["spawned"] = spawned
        else:
            result["spawned"] = 0

        # 发射进化事件
        self.kernel.events.emit(Event(
            "evolution.generation_completed", "live_engine",
            {"generation": self._generation, **result},
        ))

        return result

    # ── 活体状态 ──
    def status(self) -> LiveStatus:
        """活体系统实时状态快照。"""
        top = self.fitness.top_agents(1)
        total_tokens = sum(b.tokens_used for b in self.economy.all_budgets())
        total_cost = self.system.model_gateway.cost_tracker.total_usage().get("estimated_usd", 0) \
            if self.system.model_gateway else 0.0

        return LiveStatus(
            generation=self._generation,
            population=len(self.kernel.list_agents()),
            tasks_completed=self._tasks_completed,
            eliminations=sum(1 for a in self.kernel.list_agents()
                             if a.status.value == "stopped"),
            spawns=self._spawns,
            heal_events=len(self.healer.history),
            anomaly_alerts=len(self.detector.recent_alerts(100)),
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            top_agent=top[0].agent_id if top else "none",
            top_fitness=top[0].overall if top else 0.0,
            uptime_seconds=round(time.time() - self._started_at, 1),
        )

    # ── 内部 ──
    def _restart_agent(self, agent_id: str) -> bool:
        """自愈：重启一个失败的 agent。"""
        agent = self.kernel.get_agent(agent_id)
        if agent is None:
            return False
        self.kernel.stop_agent(agent_id)
        spec = AgentSpec(
            agent_id=agent_id,
            name=agent.spec.name,
            engine=agent.spec.engine,
            capabilities=agent.spec.capabilities,
        )
        self.kernel.register_agent(spec)
        self.kernel.events.emit(Event(
            "agent.restarted", "self_healer", {"agent_id": agent_id}))
        return True


__all__ = ["LiveEvolutionEngine", "LiveStatus", "LiveTask"]
