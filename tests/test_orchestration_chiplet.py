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
from kernel.plugins.orchestration_chiplet import OrchestrationChiplet


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


def test_pipeline_aborts_on_step_failure():
    hub, _ = _hub_with_orchestrator()
    spec = {
        "initial": {},
        "steps": [
            {"capability": "bench.doubler", "in": {"x": 5}},
            {"capability": "bench.nonexistent", "in_from": "previous"},  # 无此芯粒
        ],
    }
    res = hub.route("system.workflow", spec)
    assert res.ok is False
    assert "步骤#1" in (res.error or "")
