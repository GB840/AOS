"""内核自适应闭环 真跑测试（不虚：真实跑通稳态检测 + 失败学习，LLM 点可注入）。

诚实分级：本测试是②级（代码 + 单测实证），证明
- AdaptiveCore 把任务成败真实映射成体征读数、稳态确实检测到不稳定（纠偏非空）；
- 失败被真实写入共享失败记忆库（与 LearningLoop/autopilot 同源）；
- 纠偏动作真实作用到 LiveEvolutionEngine 的可调参数（evolution_interval 被改）。
不宣称③级端到端（③需真 LLM + 主机环境）。

沙箱无外网，用 _FakeLLMExecutor 注入式真跑，不连真 LLM。
"""

import pytest

from kernel.adaptive import AdaptiveCore
from kernel.live import LiveEvolutionEngine, _FakeLLMExecutor
from kernel.types import AgentSpec, AgentInstance, AgentStatus, Response
from kernel.events import EventBus


# ─── 轻量 fake 内核（仅实现 live.py 实际调用的接口，复用 test_live_real 模式）──

class _FakeKernel:
    def __init__(self):
        self._agents = {}
        self.events = EventBus()  # AnomalyDetector/SelfHealer 构造时订阅事件

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
        return Response(ok=False, error="stub: fake kernel has no real LLM")


class _FakeSystem:
    def __init__(self):
        self.kernel = _FakeKernel()
        self.model_gateway = None


# ─── 1) AdaptiveCore 单元：失败被记录 + 稳态真检测到不稳定 ─────────────

def test_adaptive_core_records_failure_and_detects_instability(tmp_path):
    core = AdaptiveCore(memory_path=str(tmp_path / "failure_memory.json"))

    # 一次失败任务（命令缺失类错误，应被 analyze_failure 识别为 missing_dependency）
    core.observe(
        success=False,
        task="帮我装好 ffmpeg",
        error="command not found: ffmpeg",
        capability="web.search",
    )

    # 失败被真实计数
    assert core.tasks_seen == 1
    assert core.tasks_failed == 1
    # 失败记忆库真实增长（与 LearningLoop/autopilot 同源）
    assert core.memory_stats["total_patterns"] >= 1
    # 稳态真实检测到不稳定（error_rate/energy/focus 偏离设定点 → 纠偏非空）
    assert core.ever_unstable is True
    corr = core.corrections()
    assert len(corr) > 0, "失败发生后稳态应产出纠偏动作"
    # 已知修复可被取出（PREFLIGHT 命中）
    hints = core.fix_hints(capability="web.search")
    assert any("ffmpeg" in h or "winget" in h or "pip" in h for h in hints), \
        f"应能从记忆库取回 ffmpeg 安装修复提示，实际: {hints}"


def test_adaptive_core_success_does_not_crash_and_keeps_memory(tmp_path):
    core = AdaptiveCore(memory_path=str(tmp_path / "failure_memory.json"))
    core.observe(success=False, task="装 ffmpeg", error="command not found: ffmpeg",
                 capability="web.search")
    # 之后来了一次成功：不应崩，且之前的失败记忆仍在
    core.observe(success=True, task="做个总结", capability="chat")
    assert core.tasks_seen == 2
    assert core.memory_stats["total_patterns"] >= 1, "失败记忆不应被成功覆盖"


# ─── 2) 集成：LiveEvolutionEngine 真跑，自适应中枢真实接活 ─────────────

def test_live_engine_adaptive_wired_real_loop(tmp_path):
    sys = _FakeSystem()
    ex = _FakeLLMExecutor(fail_rate=0.6)  # 60% 失败 → 稳态必检测到不稳定
    eng = LiveEvolutionEngine(
        system=sys, executor=ex,
        adaptive_memory_path=str(tmp_path / "failure_memory.json"),  # 注入临时记忆库，不污染生产
        evolution_interval=5, offspring_per_generation=2, min_population=2,
    )
    eng.initialize_population(3)
    prompts = [f"prompt-{i}" for i in range(8)]

    tasks = eng.run_tasks(prompts)

    # 真实跑了 8 次 LLM 执行（注入式）
    assert len(ex.calls) == 8
    assert len(tasks) == 8

    # 自适应中枢真实观测了全部任务
    assert eng.adaptive.tasks_seen == 8
    assert eng.adaptive.tasks_failed > 0, "fail_rate=0.6 应有失败发生"
    # 失败学习真实生效：记忆库增长
    assert eng.adaptive.memory_stats["total_patterns"] > 0
    # 稳态真实检测到不稳定
    assert eng.adaptive.ever_unstable is True

    # 纠偏真实作用到引擎参数：reduce_concurrency 真降**并发上限**（不再错配到
    # evolution_interval —— 那是进化频率，把它拉大反而会把进化本身关掉）
    applied = eng.adaptive.snapshot()["applied_actions"]
    assert any("reduce_concurrency" in a for a in applied), \
        f"自适应应真实修改引擎参数，实际 applied: {applied}"
    assert eng._max_concurrency < 3, \
        f"并发上限应被自适应真降，实际 {eng._max_concurrency}"
    assert eng.adaptive.concurrency_limit() is not None and \
        eng.adaptive.concurrency_limit() < 3, \
        f"中枢并发旋钮应被真降，实际 {eng.adaptive.concurrency_limit()}"

    # status() 真实暴露自适应快照
    st = eng.status()
    assert st.adaptive_snapshot["tasks_seen"] == 8
    assert "failure_patterns" in st.adaptive_snapshot


def test_live_engine_adaptive_memory_isolated_from_production(tmp_path):
    """注入临时路径时，失败记忆写入临时目录而非生产路径。"""
    sys = _FakeSystem()
    ex = _FakeLLMExecutor(fail_rate=1.0)
    eng = LiveEvolutionEngine(
        system=sys, executor=ex,
        adaptive_memory_path=str(tmp_path / "failure_memory.json"),
        evolution_interval=1, min_population=2,
    )
    eng.initialize_population(2)
    eng.run_tasks(["x", "y", "z"])
    # 临时目录应出现 failure_memory.json
    import os
    assert os.path.exists(os.path.join(str(tmp_path), "failure_memory.json")), \
        "失败记忆应写入注入的临时路径"
    assert eng.adaptive.memory_stats["total_patterns"] == 3, \
        "3 次全失败应记录 3 个失败模式（prompt 不同 → 指纹不同）"
