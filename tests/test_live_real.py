"""LiveEvolutionEngine 真跑测试（不虚：真实跑通进化闭环算法，LLM 调用点可注入）。

沙箱无外网，无法真连 LLM。本测试用「依赖注入」把 LLM 调用点换成确定性 fake
执行器，真实跑通 变异→评估→选择→淘汰→育种→孵化 全流程，证明 live.py 是
真实可用逻辑而非空壳。生产环境传入真正内核即走真 LLM 进化。
"""

import pytest

from kernel.live import (
    LiveEvolutionEngine,
    LiveTask,
    LiveStatus,
    get_live_engine,
    _FakeLLMExecutor,
)
from kernel.types import AgentSpec, AgentInstance, Response, AgentStatus
from kernel.events import EventBus


# ─── 轻量 fake 内核（仅实现 live.py 实际调用的接口）─────────────────

class _FakeKernel:
    def __init__(self):
        self._agents = {}
        # 用真实 EventBus：AnomalyDetector/SelfHealer 构造时订阅事件
        self.events = EventBus()

    def list_agents(self):
        return list(self._agents.values())

    def get_agent(self, aid):
        return self._agents.get(aid)

    def register_agent(self, spec: AgentSpec):
        inst = AgentInstance(agent_id=spec.agent_id, spec=spec,
                             status=AgentStatus.PENDING)
        self._agents[spec.agent_id] = inst
        return inst

    def stop_agent(self, aid):
        if aid in self._agents:
            self._agents[aid].status = AgentStatus.STOPPED

    def send_message(self, msg):
        # 默认执行器(_KernelLLMExecutor)会调它；这里返回 ok=False 以验证
        # 「连不通时诚实失败、不伪造成功」。
        return Response(ok=False, error="stub: fake kernel has no real LLM")


class _FakeSystem:
    def __init__(self):
        self.kernel = _FakeKernel()
        self.model_gateway = None  # status() 已对 None 做保护


# ─── 1) 全成功：真实跑通多代进化闭环 ───────────────────────────────

def test_live_full_loop_success():
    sys = _FakeSystem()
    ex = _FakeLLMExecutor(fail_rate=0.0)
    eng = LiveEvolutionEngine(
        system=sys, executor=ex,
        evolution_interval=2, offspring_per_generation=2, min_population=2,
    )
    ids = eng.initialize_population(4)
    assert len(ids) == 4

    tasks = eng.run_tasks([f"prompt-{i}" for i in range(5)])
    # 真实跑了 5 次 LLM 执行（注入式，不连外网）
    assert len(ex.calls) == 5
    assert len(tasks) == 5
    assert all(t.success for t in tasks), "全成功 executor 应全成功"

    st: LiveStatus = eng.status()
    assert st.generation >= 2, "interval=2 跑5任务至少触发2代进化"
    assert st.tasks_completed == 5
    assert st.spawns >= 2, "至少育种孵化 2 个新 agent（2代×2 offspring）"
    assert st.population > 4, "孵化后种群应增长"

    # 验证新 agent 真的注册进了内核（而非只在内存里）
    live_ids = [a.agent_id for a in sys.kernel.list_agents()]
    assert any("gen" in aid for aid in live_ids), "应有 live-gen* 孵化 agent"


# ─── 2) 全失败：淘汰逻辑真实触发（不伪造成功）──────────────────────

def test_live_failure_triggers_elimination():
    sys = _FakeSystem()
    ex = _FakeLLMExecutor(fail_rate=1.0)  # 全部失败
    eng = LiveEvolutionEngine(
        system=sys, executor=ex,
        evolution_interval=1, keep_top_agents=2, min_population=2,
    )
    eng.initialize_population(4)
    tasks = eng.run_tasks(["a", "b", "c", "d"])
    assert len(tasks) == 4
    assert all(not t.success for t in tasks)

    st: LiveStatus = eng.status()
    assert st.eliminations >= 1, "全失败应触发淘汰"
    stopped = [a for a in sys.kernel.list_agents()
               if a.status.value == "stopped"]
    assert len(stopped) >= 1, "应有被 stop_agent 的真实淘汰"


# ─── 3) 默认执行器确实走真内核 send_message（连不通诚实失败）────────

def test_default_executor_hits_real_kernel():
    sys = _FakeSystem()
    eng = LiveEvolutionEngine(system=sys)  # executor=None → _KernelLLMExecutor
    eng.initialize_population(2)
    tasks = eng.run_tasks(["x"])
    assert len(tasks) == 1
    # FakeKernel.send_message 返回 ok=False → 诚实记录失败，不伪造
    assert tasks[0].success is False
    assert "stub" in tasks[0].error


# ─── 4) get_live_engine 进程内单例 ─────────────────────────────────

def test_get_live_engine_singleton():
    import kernel.live as L
    L._live_engine_instance = None  # 隔离全局单例
    sys = _FakeSystem()
    ex = _FakeLLMExecutor()
    a = get_live_engine(system=sys, executor=ex)
    b = get_live_engine(system=sys, executor=ex)
    assert a is b, "单例应返回同一实例"
    L._live_engine_instance = None
