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
from kernel.adaptive import AdaptiveCore, StageGuard, get_adaptive_core
from kernel.events import Event
from typing import Protocol, runtime_checkable


# ─── LLM 执行器（可注入：生产走真内核→真LLM，离线注入 fake 真跑闭环） ──

@runtime_checkable
class LLMExecutor(Protocol):
    """封装「一次真实 LLM 调用」。默认走真内核，可注入 fake 离线真跑验证。"""
    def __call__(self, prompt: str, agent_id: str, engine: str) -> "Response": ...


class _KernelLLMExecutor:
    """默认执行器：经真实内核路由到真 LLM（生产路径）。"""
    def __init__(self, kernel):
        self.kernel = kernel

    def __call__(self, prompt: str, agent_id: str, engine: str) -> "Response":
        return self.kernel.send_message(Message(
            sender="live_engine", recipient=agent_id,
            payload={"prompt": prompt, "model": ""}))


class _FakeLLMExecutor:
    """离线/测试执行器：不调真 LLM，返回确定性模拟 Response。

    用于真跑验证整个进化算法闭环（变异→评估→选择→育种→孵化），
    不伪造成功——fail_rate>0 时如实返回 ok=False，淘汰逻辑仍真实触发。
    """
    def __init__(self, fail_rate: float = 0.0, latency: float = 0.001):
        self.fail_rate = fail_rate
        self.latency = latency
        self.calls: list = []

    def __call__(self, prompt: str, agent_id: str, engine: str) -> "Response":
        self.calls.append((prompt, agent_id, engine))
        if self.latency:
            time.sleep(self.latency)
        if self.fail_rate and (abs(hash(prompt)) % 1000) / 1000.0 < self.fail_rate:
            return Response(ok=False, error="simulated transient failure")
        return Response(ok=True, data={"content": ("answer " + prompt + " ") * 8})


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
    adaptive_snapshot: Dict[str, Any] = field(default_factory=dict)
    max_concurrency: int = 0        # 当前真实并发上限（会被稳态动态压低/回升）
    tenant_id: Optional[str] = None  # 多租户隔离标识（None=自用模式）


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
                 max_concurrency: int = 3,          # 每批投入的活跃 agent 工作集上限
                 system: Optional[AOSSystem] = None,    # 可注入（离线测试用轻量内核）
                 executor: Optional[LLMExecutor] = None, # 可注入（离线测试用 fake LLM）
                 adaptive_memory_path: Optional[str] = None,  # 可注入（离线测试用临时记忆库）
                 tenant_id: Optional[str] = None,   # 多租户隔离（None=自用模式）
                 ):
        # 依赖注入：默认走真实内核 + 真实 LLM；离线/沙箱可注入 fake 真跑闭环。
        self.system: AOSSystem = system or build_default_system()
        self.kernel = self.system.kernel
        self._executor: LLMExecutor = executor or _KernelLLMExecutor(self.kernel)

        # 进化参数
        self._evolution_interval = evolution_interval
        self._min_population = min_population
        self._max_population = max_population
        self._keep_top = keep_top_agents
        self._offspring_count = offspring_per_generation
        # 真实并发旋钮：每批任务真正投入的活跃 agent 工作集上限。
        # 稳态判失稳 → reduce_concurrency → 这个值真降 → 下一批真的少铺开。
        # 诚实边界：run_tasks 当前为顺序执行，本值语义是「活跃工作集宽度」
        # （真实裁剪，可从 status() 观测），不是线程并行度。
        self._max_concurrency = max(1, int(max_concurrency))

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

        # 内核自适应中枢：稳态 + 失败学习（理念接活点，零引用死代码已在此接电）
        self.tenant_id = tenant_id
        self.adaptive = AdaptiveCore(memory_path=adaptive_memory_path,
                                     concurrency_base=self._max_concurrency,
                                     tenant_id=tenant_id)

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
        # 真实并发裁剪：稳态压下来的 _max_concurrency 真的收窄本批工作集
        agent_ids = agent_ids[:max(1, self._max_concurrency)]

        idx = 0
        for prompt in prompts:
            aid = agent_ids[idx % len(agent_ids)]
            idx += 1

            task = LiveTask(prompt=prompt, assigned_agent=aid)
            agent = self.kernel.get_agent(aid)
            engine = agent.spec.engine if agent else "litellm"
            task.engine = engine

            t0 = time.monotonic()

            # === 真正走 LLM 执行器（默认真内核→真LLM；注入 fake 则离线真跑）===
            try:
                response = self._executor(prompt, aid, engine)
                task.result = response
                task.latency_seconds = round(time.monotonic() - t0, 3)

                if response.ok:
                    task.success = True
                    # 从 response 估算 token（真LLM返回的）
                    content = response.data.get("content", "")
                    task.tokens_used = max(10, len(content) // 3)
                else:
                    task.error = response.error or "unknown"
                    # 失败也真烧了 prompt token（请求真的发出去了）——不记的话
                    # energy 体征会误以为「失败不耗资源」，永远看不到白烧成本。
                    task.tokens_used = max(1, len(prompt) // 3)
            except Exception as exc:
                task.latency_seconds = round(time.monotonic() - t0, 3)
                task.error = str(exc)
                task.tokens_used = max(1, len(prompt) // 3)

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

            # === 自适应中枢：稳态 + 失败学习（每轮任务真观测、真纠偏）===
            try:
                self.adaptive.observe(
                    success=task.success,
                    task=prompt,
                    error=task.error,
                    capability=engine,
                    latency_ms=task.latency_seconds * 1000.0,
                    # 真实运行时指标：体征取自真实延迟/真实 token/真实并发宽度，
                    # 不再由「成败率」一个数折算出五个体征（见 adaptive._derive_readings）
                    runtime_metrics={
                        "latency_ms": task.latency_seconds * 1000.0,
                        "tokens": float(task.tokens_used),
                        "concurrency": float(len(agent_ids)),
                    },
                )
                self.adaptive.apply_corrections(self)
            except Exception:
                # 自适应失败绝不破坏主进化闭环
                logger.warning("LiveEvolutionEngine: 自适应中枢异常，已跳过", exc_info=True)

            tasks.append(task)
            self._tasks_completed += 1

            # === 定期进化（动态——进化环节死则降级跳过本轮进化，不杀整轮）===
            if self._tasks_completed % self._evolution_interval == 0:
                StageGuard(self.adaptive, "evolve").run(
                    self.evolve, severity="dynamic",
                    fallback=lambda e: {"error": f"evolve 环节失败: {e}"}, max_retry=0,
                )
                agent_ids = [a.agent_id for a in self.kernel.list_agents()
                             if a.status.value != "stopped"]
                if not agent_ids:
                    agent_ids = self.initialize_population(self._min_population)
                # 进化换血后重新按当前（可能已被稳态压低的）并发上限裁剪
                agent_ids = agent_ids[:max(1, self._max_concurrency)]

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
            adaptive_snapshot=self.adaptive.snapshot(),
            max_concurrency=self._max_concurrency,
            tenant_id=self.tenant_id,
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


# ─── 进程内单例（接电用） ───────────────────────────────────────────

_live_engine_instance: Optional["LiveEvolutionEngine"] = None


def get_live_engine(system=None,
                    executor=None) -> "LiveEvolutionEngine":
    """返回活体进化引擎单例。

    - 默认构造会 build_default_system() 并接入真实内核（生产：真 LLM 进化）。
    - 离线/沙箱可注入 system + executor 真跑闭环而不连外网。
    - 构造失败（如沙箱无内核/网络）时**原样抛出**，由调用方 best-effort 捕获，
      绝不伪造成功。
    """
    global _live_engine_instance
    if _live_engine_instance is None:
        _live_engine_instance = LiveEvolutionEngine(system=system, executor=executor)
    return _live_engine_instance


__all__ = ["LiveEvolutionEngine", "LiveStatus", "LiveTask", "get_live_engine",
           "LLMExecutor", "_KernelLLMExecutor", "_FakeLLMExecutor"]
