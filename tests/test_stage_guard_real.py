"""环节级隔离 + 高重度 + 动态恢复 —— ② 级离线真跑实证。

验证用户诉求「一次死了后面都挨这死」已被结构性消除：
- 隔离：任何环节抛异常被本地捕获，不级联杀整轮；
- 高重度：关键链路(如 execute)死亡必写入共享失败记忆 + 触发稳态；
- 动态：非关键链路(如 reflect/evolve)死亡降级续跑，后续环节照常执行。

诚实分级：本测试为②级（代码 + 单测实证，不连真 LLM）。③级需主机真 LLM 端到端。
"""
from __future__ import annotations

import os
import tempfile

from kernel.adaptive import AdaptiveCore, StageGuard, get_adaptive_core
from kernel.live import LiveEvolutionEngine, _FakeLLMExecutor
from kernel.types import AgentSpec, AgentInstance, AgentStatus, Response
from kernel.events import EventBus


def _boom(*a, **k):
    raise RuntimeError("环节死亡：boom")


# ───────────────────────── 单元：隔离 + 高重度 ─────────────────────────
def test_stage_guard_isolates_high_severity_and_records_memory(tmp_path):
    mem = os.path.join(str(tmp_path), "fm.json")
    core = AdaptiveCore(memory_path=mem)
    g = StageGuard(core, "execute")

    ok, val, err = g.run(_boom, severity="high", max_retry=0)

    # 隔离：返回结构化失败，绝不抛出
    assert ok is False
    assert val is None
    assert isinstance(err, RuntimeError)
    # 高重度：失败必写入共享失败记忆 + 稳态
    health = core.stage_health()
    assert health["execute"]["failed"] == 1
    assert core.memory_stats["total_patterns"] >= 1
    # 记忆按 stage.execute 维度聚合（可后续按环节取根因）
    hints = core.fix_hints(capability="stage.execute")
    assert isinstance(hints, list)


# ───────────────────────── 单元：动态降级 + 后续环节照跑 ─────────────────────────
def test_stage_guard_dynamic_fallback_lets_later_stages_run(tmp_path):
    mem = os.path.join(str(tmp_path), "fm.json")
    core = AdaptiveCore(memory_path=mem)
    order: list = []

    # 环节A：动态，会死 → 降级产出，不阻断
    g_a = StageGuard(core, "reflect")
    ok_a, val_a, _ = g_a.run(_boom, severity="dynamic",
                             fallback=lambda e: "A-fallback", max_retry=0)
    assert ok_a is False
    assert val_a == "A-fallback"

    # 后续环节B：必须照常执行（证明没有级联死）
    order.append("B ran")

    assert "B ran" in order
    assert core.stage_health()["reflect"]["failed"] == 1


# ───────────────────────── 集成：live 真实循环里 evolve 死不杀整轮 ─────────────────────────
class _FK:
    def __init__(self):
        self._a = {}
        self.events = EventBus()

    def list_agents(self):
        return list(self._a.values())

    def get_agent(self, aid):
        return self._a.get(aid)

    def register_agent(self, spec):
        self._a[spec.agent_id] = AgentInstance(
            agent_id=spec.agent_id, spec=spec, status=AgentStatus.PENDING)
        return self._a[spec.agent_id]

    def stop_agent(self, aid):
        if aid in self._a:
            self._a[aid].status = AgentStatus.STOPPED

    def send_message(self, m):
        return Response(ok=False, error="stub")


class _FS:
    def __init__(self):
        self.kernel = _FK()
        self.model_gateway = None


def test_live_loop_survives_evolve_stage_death(tmp_path):
    """evolve 环节每轮都死，但 run_tasks 仍跑完全部任务、不级联、记忆记录 evolve 失败。"""
    mem = os.path.join(str(tmp_path), "fm.json")
    sys = _FS()
    ex = _FakeLLMExecutor(fail_rate=0.0)  # 任务本身全成功，孤立测 evolve 环节
    eng = LiveEvolutionEngine(
        system=sys, executor=ex,
        adaptive_memory_path=mem,
        evolution_interval=1,        # 每轮都触发 evolve
        offspring_per_generation=2, min_population=2,
    )
    eng.initialize_population(3)

    # 让 evolve 环节必死（模拟进化子系统崩溃）
    def _evolve_dead():
        raise RuntimeError("evolve 子系统崩了")
    eng.evolve = _evolve_dead

    # 关键断言：整轮不崩，正常返回全部任务
    tasks = eng.run_tasks([f"prompt-{i}" for i in range(6)])
    assert len(tasks) == 6
    assert all(t.prompt for t in tasks)

    # 动态降级生效：evolve 失败被记录，且不阻断任务循环
    health = eng.adaptive.stage_health()
    assert health.get("evolve", {}).get("failed", 0) >= 1
    # 任务级自适应仍正常（任务全成功 → 记忆里 task 维度不增长，但 stage 维度增长）
    assert core_memory_has_stage(eng.adaptive, "stage.evolve")


def core_memory_has_stage(core: AdaptiveCore, stage_prefix: str) -> bool:
    # 失败记忆按 FailureRecord.failed_step 维度聚合（= "stage.{name}"）
    return any(getattr(rec, "failed_step", "").startswith(stage_prefix)
               for rec in core.memory._records.values())


# ───────────────────────── 集成：autopilot 执行环节死 → 结构化收尾不崩 ─────────────────────────
def test_autopilot_execute_stage_death_does_not_cascade(tmp_path):
    """monkeypatch 掉 _execute 使其必死，autopilot.run 仍以结构化失败收尾（不抛异常）。"""
    import kernel.autopilot as ap
    import kernel.adaptive as kad

    original = ap._execute
    ap._execute = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("execute 死"))

    # 注入临时 core，避免污染生产失败记忆库
    mem = os.path.join(str(tmp_path), "fm.json")
    tmp_core = AdaptiveCore(memory_path=mem)
    orig_get = kad.get_adaptive_core
    kad.get_adaptive_core = lambda: tmp_core

    before = sum(tmp_core.stage_health().get(s, {}).get("failed", 0)
                 for s in tmp_core.stage_health())

    try:
        # heuristic 规划离线可用，不触真 LLM
        result = ap.run("写一个 hello world 程序", planner="heuristic")
    finally:
        ap._execute = original
        kad.get_adaptive_core = orig_get

    # 不崩：返回 dict，且含结构化失败标记
    assert isinstance(result, dict)
    assert "error" in result or (result.get("execution", {}) or {}).get("trace") == []
    after = sum(tmp_core.stage_health().get(s, {}).get("failed", 0)
                for s in tmp_core.stage_health())
    # 高重度：execute 环节死亡已被记录
    assert after > before
