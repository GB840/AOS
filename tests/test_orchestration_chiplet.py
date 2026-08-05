"""编排芯粒测试（Day15-21）：工作流串联 + 「编排是用户态芯粒」原则。

验证：
1. OrchestrationChiplet 是普通 fabric 适配器，能经路由层把多芯粒串成流水线，
   上一步输出自动成为下一步入参（3D 堆叠式链路）。
2. 它复用枢纽的 route() 作为路由层，自身**不进内核**——证明工作流引擎是
   封装内容而非封装基座。
3. 流水线中某步失败时，编排芯粒干净中止并报错（故障隔离沿用到流水线）。

不依赖真实 OSS 引擎；下游用合成芯粒（plain-string 能力，不污染 Capability 枚举）。
"""
from __future__ import annotations

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from kernel.plugins.fabric_hub import FabricHub


class _Doubler(BaseAgentAdapter):
    engine_id = "doubler"

    def advertise_capabilities(self):
        return ["bench.doubler"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        x = req.payload.get("x", 0)
        return InvokeResult(ok=True, data={"x": x * 2})


class _Incrementer(BaseAgentAdapter):
    engine_id = "incrementer"

    def advertise_capabilities(self):
        return ["bench.increment"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        x = req.payload.get("x", 0)
        return InvokeResult(ok=True, data={"x": x + 1})


class _Failer(BaseAgentAdapter):
    engine_id = "failer"

    def advertise_capabilities(self):
        return ["bench.fail"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=False, error="boom")


_PARALLEL_THREADS: list[str] = []


class _SlowEcho(BaseAgentAdapter):
    """故意 sleep 并记录线程名，用于证明 parallel_groups 真·并发。"""
    engine_id = "slow"

    def advertise_capabilities(self):
        return ["bench.slow"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        import threading, time
        _PARALLEL_THREADS.append(threading.current_thread().name)
        time.sleep(0.05)
        return InvokeResult(ok=True, data={"x": req.payload.get("x", 0)})


def _hub_with_orchestrator():
    hub = FabricHub(adapters=(_Doubler, _Incrementer))
    orch_id = hub.add_orchestrator()
    return hub, orch_id


def test_orchestrator_is_registered_as_user_space_chiplet():
    hub, orch_id = _hub_with_orchestrator()
    assert orch_id == "orchestrator"
    # 它和真实芯粒平级注册进枢纽，而非进内核
    assert "orchestrator" in hub._registry._adapters
    assert hub.resolve_engine("system.workflow") == "orchestrator"


def test_pipeline_chains_steps_passing_output():
    hub, _ = _hub_with_orchestrator()
    # 5 ->(dbl) 10 ->(inc) 11
    spec = {
        "initial": {},
        "steps": [
            {"capability": "bench.doubler", "in": {"x": 5}},
            {"capability": "bench.increment", "in_from": "previous"},
        ],
    }
    res = hub.route("system.workflow", spec)
    assert res.ok is True
    assert res.data["ok_steps"] == 2
    assert res.data["final"] == {"x": 11}
    assert len(res.data["trace"]) == 2


def test_pipeline_tolerates_step_failure_and_continues():
    """Fix C：单步失败不中断整条流水线——记录失败、保留上一步成功输出、继续跑。"""
    hub, _ = _hub_with_orchestrator()
    spec = {
        "initial": {},
        "steps": [
            {"capability": "bench.doubler", "in": {"x": 5}},
            {"capability": "bench.nonexistent", "in_from": "previous"},  # 无此芯粒
        ],
    }
    res = hub.route("system.workflow", spec)
    # 成功步(0)照常跑出结果，整条不因步1失败而 abort
    assert res.ok is True
    assert res.data["ok_steps"] == 1
    assert res.data["failed_steps"] == 1
    # trace 必须逐条标注 ok/error
    assert res.data["trace"][0]["ok"] is True
    assert res.data["trace"][1]["ok"] is False
    assert "no live provider" in (res.data["trace"][1]["error"] or "")


def test_pipeline_blocks_dependent_step_when_upstream_failed():
    """修复语义空转：上游从未成功产出时，in_from:"previous" 的下游步必须判为
    依赖失败，不能拿 stale/initial 冒充输入去跑（否则出现『图生成成功但没真去
    搜索』的假成功）。"""
    hub = FabricHub(adapters=(_Failer,))
    hub.add_orchestrator()
    spec = {
        "initial": {"task": "搜索天气并画示意图"},
        "steps": [
            {"capability": "bench.fail", "in": {"x": 1}},
            {"capability": "bench.fail", "in_from": "previous"},
        ],
    }
    res = hub.route("system.workflow", spec)
    # 没有任何步骤成功 → 整条失败，不应有假成功
    assert res.ok is False
    assert res.data["ok_steps"] == 0
    assert res.data["failed_steps"] == 2
    # step1 必须被标记为依赖失败，而非拿着 stale input 冒充当成功
    assert "依赖" in (res.data["trace"][1]["error"] or "")


def test_parallel_groups_run_concurrently():
    """SwarmFlow 的 execute_parallel 其实是顺序循环（swarm_flow.py:266-274）。
    移植到 FabricHub 的价值在于真·并发：组内步骤经线程池并行执行。"""
    hub = FabricHub(adapters=(_SlowEcho,))
    hub.add_orchestrator()
    _PARALLEL_THREADS.clear()
    spec = {
        "initial": {},
        "steps": [
            {"capability": "bench.slow", "in": {"x": 1}},
            {"capability": "bench.slow", "in": {"x": 2}},
            {"capability": "bench.slow", "in": {"x": 3}},
            {"capability": "bench.slow", "in": {"x": 4}},
        ],
        "parallel_groups": [[0, 1], [2, 3]],
    }
    res = hub.route("system.workflow", spec)
    assert res.ok is True
    assert res.data["ok_steps"] == 4
    assert res.data.get("parallel") is True
    # 并发证据：4 步在 >=2 个不同线程上跑；若退化成顺序，则全在同一线程
    assert len(set(_PARALLEL_THREADS)) >= 2


def test_parallel_groups_then_sequential_remainder():
    """组间顺序 + 未被组覆盖的步骤在全部组跑完后顺序补跑，且 in_from:previous
    能正确拿到上游成功输出。"""
    hub = FabricHub(adapters=(_Doubler, _Incrementer))
    hub.add_orchestrator()
    spec = {
        "initial": {},
        "steps": [
            {"capability": "bench.doubler", "in": {"x": 5}},    # 0: 组内
            {"capability": "bench.increment", "in": {"x": 1}},  # 1: 组内
            {"capability": "bench.doubler", "in_from": "previous"},  # 2: 顺序补跑
        ],
        "parallel_groups": [[0, 1]],
    }
    res = hub.route("system.workflow", spec)
    assert res.ok is True
    assert res.data["ok_steps"] == 3
    assert res.data["failed_steps"] == 0
    # 步2 拿到的 previous 是某成功步输出（dict 含 x）
    assert isinstance(res.data["final"], dict) and "x" in res.data["final"]


def test_parallel_failure_isolated():
    """并发组内某步失败不影响同组其他步（单步容错在并发下同样生效）。"""
    hub = FabricHub(adapters=(_Doubler, _Failer))
    hub.add_orchestrator()
    spec = {
        "initial": {},
        "steps": [
            {"capability": "bench.doubler", "in": {"x": 5}},  # ok
            {"capability": "bench.fail", "in": {"x": 1}},     # fail
        ],
        "parallel_groups": [[0, 1]],
    }
    res = hub.route("system.workflow", spec)
    assert res.ok is True
    assert res.data["ok_steps"] == 1
    assert res.data["failed_steps"] == 1
    # 并发组内 trace 的 append 顺序取决于谁先完成（_Failer 可能先于 _Doubler 返回），
    # 故按 capability 查找而非按索引断言，避免误判并发完成顺序。
    trace = res.data["trace"]
    doubler_step = next(t for t in trace if t.get("capability") == "bench.doubler")
    failer_step = next(t for t in trace if t.get("capability") == "bench.fail")
    assert doubler_step["ok"] is True
    assert failer_step["ok"] is False
