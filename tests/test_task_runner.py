"""FabricHub.run_task 自主执行闭环的集成测试（真实 hub 路由，无外部依赖）。

用进程内 bench 适配器构造真实 FabricHub 实例，跑通「规划 → 解析成 steps →
编排芯粒逐跳执行 → trace」全链路。bench 适配器返回固定字符串，不依赖任何
外部 LLM/服务，因此可确定性真跑（非 mock 路由）。
"""
from __future__ import annotations

from typing import Any

from kernel.plugins.fabric_hub import FabricHub
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from kernel.plugins.plan_bridge import heuristic_plan, parse_plan_to_steps


class _PlanBench(BaseAgentAdapter):
    engine_id = "planner_bench"

    def advertise_capabilities(self):
        return [Capability.PLANNING]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if req.capability == Capability.PLANNING.value:
            plan = "Step 1: search the web for a cat photo\nStep 2: draw a picture of the cat"
            return InvokeResult(ok=True, data={"plan": plan})
        return InvokeResult(ok=False, error="bad cap")


class _PlanFail(BaseAgentAdapter):
    """提供 PLANNING 但 invoke 必失败，用于验证降级到 heuristic。"""
    engine_id = "planner_fail"

    def advertise_capabilities(self):
        return [Capability.PLANNING]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=False, error="simulated planner failure")


class _SearchBench(BaseAgentAdapter):
    engine_id = "search_bench"

    def advertise_capabilities(self):
        return [Capability.WEB_SEARCH]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=True, data={"result": f"searched:{req.payload}"})


class _ImageBench(BaseAgentAdapter):
    engine_id = "image_bench"

    def advertise_capabilities(self):
        return [Capability.MEDIA_IMAGE]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=True, data={"result": f"image:{req.payload}"})


class _MemoryBench(BaseAgentAdapter):
    engine_id = "memory_bench"

    def advertise_capabilities(self):
        return [Capability.MEMORY_SEMANTIC]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=True, data={"result": f"stored:{req.payload}"})


def _build(*adapters) -> FabricHub:
    hub = FabricHub(adapters=adapters)
    hub.add_orchestrator()
    return hub


def test_run_task_with_planner_end_to_end():
    hub = _build(_PlanBench, _SearchBench, _ImageBench)
    out = hub.run_task("make a cat poster")
    assert out["planner"] == "planner_bench"  # AG2/规划引擎被选用
    assert out["plan"] and "draw" in out["plan"]
    steps = out["steps"]
    assert len(steps) == 2
    assert steps[0]["capability"] == "web.search"         # search → web.search (dgg)
    assert steps[1]["capability"] == "media.image"       # draw → image
    assert "in" in steps[0] and "task" in steps[0]["in"]
    assert steps[1].get("in_from") == "previous"
    # 执行：逐跳真实跑通
    exec_data = out["execution"]
    assert isinstance(exec_data, dict)
    assert exec_data["ok_steps"] == 2
    assert len(exec_data["trace"]) == 2
    assert exec_data["trace"][0]["capability"] == "web.search"
    assert exec_data["trace"][1]["capability"] == "media.image"


def test_run_task_heuristic_fallback_when_no_planner():
    # 没有 PLANNING 引擎 → 必须降级到 heuristic，且端到端仍能跑通
    hub = _build(_SearchBench, _MemoryBench)
    out = hub.run_task("search the web then save to memory")
    assert out["planner"] == "heuristic"
    assert len(out["steps"]) >= 1
    exec_data = out["execution"]
    assert exec_data["ok_steps"] >= 1


def test_run_task_falls_back_when_planner_fails():
    # 规划引擎 invoke 失败 → 透明降级 heuristic，不抛不崩
    hub = _build(_PlanFail, _SearchBench)
    out = hub.run_task("search the web")
    assert out["planner"] == "heuristic"
    assert out["execution"]["ok_steps"] >= 1


def test_parse_plan_to_steps_maps_capabilities():
    text = "1. search the web for docs\n2. draw a diagram\n3. store it in memory"
    caps = ["web.search", "media.image", "memory.semantic", "inference.llm"]
    steps = parse_plan_to_steps(text, caps)
    assert len(steps) == 3
    assert steps[0]["capability"] == "web.search"
    assert steps[1]["capability"] == "media.image"
    assert steps[2]["capability"] == "memory.semantic"
    assert "in" in steps[0] and "task" in steps[0]["in"]
    assert steps[1].get("in_from") == "previous"


def test_parse_plan_fallback_to_available_cap():
    # 步骤语义无匹配关键词 → 兜底到 available 中存在的兜底能力
    text = "Step 1: do an unspecified thing"
    caps = ["inference.llm", "system.workflow"]
    steps = parse_plan_to_steps(text, caps)
    assert steps[0]["capability"] in caps


def test_heuristic_plan_splits_on_conjunction():
    caps = ["action.aci", "memory.semantic"]
    steps = heuristic_plan("search the web then save to memory", caps)
    assert len(steps) == 2
    assert steps[0]["capability"] == "action.aci"
    assert steps[1]["capability"] == "memory.semantic"


class _FailBench(BaseAgentAdapter):
    """提供 ACI 但 invoke 必失败，用于验证编排芯粒单步容错（C）。"""
    engine_id = "fail_bench"

    def advertise_capabilities(self):
        return [Capability.ACI]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(ok=False, error="simulated engine failure")


class _MemBench(BaseAgentAdapter):
    """提供 MEMORY_SEMANTIC 的记忆 bench，记录写入，用于验证 B 记忆门面。"""
    engine_id = "mem_bench"
    calls: list = []  # 类级记录，测试开头清空

    def advertise_capabilities(self):
        return [Capability.MEMORY_SEMANTIC]

    def health(self) -> bool:
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        action = req.payload.get("action", "search")
        if action == "add":
            _MemBench.calls.append(req.payload.get("text", ""))
            return InvokeResult(ok=True, data={"result": {"id": "m1"}})
        if action == "search":
            return InvokeResult(ok=True, data={"result": [{"memory": "prior"}]})
        return InvokeResult(ok=False, error=f"bad action {action}")


def test_orchestrator_continues_after_step_failure():
    # C：单步失败不中断整条流水线，继续跑后续步，逐条报状态。
    # 用直接 steps（而非 heuristic）避免依赖映射漂移：步0成功、步1(依赖步0)自身失败。
    hub = _build(_FailBench, _ImageBench)  # action.aci 必挂，media.image 正常
    spec = {
        "initial": {},
        "steps": [
            {"capability": "media.image", "in": {"prompt": "cat"}},  # 成功
            {"capability": "action.aci", "in_from": "previous"},     # 依赖步0(已成功)，自身必挂
        ],
    }
    res = hub.route("system.workflow", spec)
    assert res.ok is True                 # 有步成功 → 整条仍 ok
    assert res.data["ok_steps"] == 1
    assert res.data["failed_steps"] == 1
    assert len(res.data["trace"]) == 2
    assert res.data["trace"][0]["ok"] is True
    assert res.data["trace"][0]["capability"] == "media.image"
    assert res.data["trace"][1]["ok"] is False
    assert res.data["trace"][1]["capability"] == "action.aci"


def test_memory_facade_routes_to_engine():
    # B：hub.memory_store / memory_recall 经 fabric 路由到记忆引擎
    _MemBench.calls.clear()
    hub = _build(_MemBench)
    assert hub.memory_store("用户喜欢红色") is True
    assert len(_MemBench.calls) == 1
    recalled = hub.memory_recall("用户偏好")
    assert isinstance(recalled, list) and len(recalled) == 1


def test_run_task_persists_memory_after_execution():
    # B：run_task 执行后会把任务结果写入记忆（best-effort）
    _MemBench.calls.clear()
    hub = _build(_MemBench, _ImageBench)
    out = hub.run_task("画一张图", planner="heuristic")
    # 执行前 recall 命中（非空）→ initial 注入了 memory；执行后 store 了一次
    assert out["memory"]["recalled"] >= 1
    assert out["memory"]["stored"] is True
    assert any("task" in c for c in _MemBench.calls)


def test_memory_facade_graceful_without_engine():
    # B：无记忆引擎时门面干净降级（不抛、返回空/False）
    hub = _build(_SearchBench, _ImageBench)  # 无 MEMORY_SEMANTIC 引擎
    assert hub.memory_recall("anything") == []
    assert hub.memory_store("anything") is False
