"""编排芯粒（Orchestration Chiplet）—— 用户态工作流引擎，非内核一部分。

架构原则（Day15-21 核心交付）：
  工作流引擎 = 一个普通的 fabric 适配器，注册进枢纽(hub)，与 litellm /
  mem0 / ag2 等芯粒平级；它**不进 AOSKernel**，也不碰内核内部状态。
  它只通过「fabric 路由层」(route_fn，即枢纽的 route) 把任务委派给下游芯粒，
  把上一步的输出作为下一步的输入，串成 3D 堆叠式流水线。

这正是 Chiplet 先进封装的「堆叠引擎」在软件里的对应：堆叠的内容
（工作流）是用户态芯粒，不是封装基座（内核）本身。内核只做路由/隔离/
资源调度，编排逻辑全部外置。

输入报文（InvokeRequest.payload）：
  {
    "initial": {...},                     # 流水线初始上下文
    "steps": [                            # 有序步骤
      {"capability": "bench.ping",
       "in": {"k": "v"}},                 # 固定入参
      # 或把上一步输出作为本步入参：
      {"capability": "bench.ping2",
       "in_from": "previous"},
      # 或把 initial 的某字段取出作为入参：
      {"capability": "bench.ping3",
       "in_from": "initial", "field": "seed"}
    ]
  }

输出（InvokeResult.data）：
  {"ok_steps": N, "final": <最后一步输出>, "trace": [每步 engine_id+输出摘要]}
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability


def _as_str(cap) -> str:
    return cap.value if hasattr(cap, "value") else str(cap)


class OrchestrationChiplet(BaseAgentAdapter):
    """把多芯粒按序串联成流水线的编排芯粒（用户态，非内核）。"""

    engine_id = "orchestrator"

    def __init__(self, route_fn: Optional[Callable[[str, Dict[str, Any]], Any]] = None) -> None:
        # route_fn: 路由层委派函数，签名 (capability:str, payload:dict) -> InvokeResult
        # 由枢纽在注册时注入（见 FabricHub.add_orchestrator），使本芯粒复用
        # 与所有芯粒相同的「单一可信路由」，而非自己再造一套调度。
        self._route_fn = route_fn

    def advertise_capabilities(self):
        return [Capability.WORKFLOW_EXECUTE]

    def health(self) -> bool:
        # 编排芯粒自身无外部依赖；只要路由层可用即健康。
        return self._route_fn is not None

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if self._route_fn is None:
            return InvokeResult(ok=False, error="orchestrator: route_fn 未注入（枢纽未装配）")
        spec = req.payload or {}
        steps = spec.get("steps")
        if not isinstance(steps, list) or not steps:
            return InvokeResult(ok=False, error="orchestrator: 缺少 steps[] 流水线定义")
        initial = spec.get("initial") or {}
        context = dict(initial)
        trace: list[Dict[str, Any]] = []

        for idx, step in enumerate(steps):
            cap = step.get("capability")
            if not cap:
                return InvokeResult(ok=False, error=f"orchestrator: 步骤#{idx} 缺 capability")
            # 解析本步入参
            if "in" in step:
                payload = step["in"]
            elif step.get("in_from") == "previous":
                payload = context
            elif step.get("in_from") == "initial":
                field = step.get("field")
                payload = {field: context[field]} if field else dict(initial)
            else:
                payload = {}
            # 委派给下游芯粒（经同一路由层，故障隔离同样生效）
            res = self._route_fn(_as_str(cap), payload)
            if isinstance(res, InvokeResult) and not res.ok:
                return InvokeResult(
                    ok=False,
                    error=f"orchestrator: 步骤#{idx}({cap}) 失败: {res.error}",
                )
            step_out = res.data if isinstance(res, InvokeResult) else res
            context = step_out if isinstance(step_out, dict) else {"result": step_out}
            trace.append({"step": idx, "capability": _as_str(cap), "out": _brief(step_out)})

        return InvokeResult(
            ok=True,
            data={"ok_steps": len(steps), "final": context, "trace": trace},
        )


def _brief(obj: Any, limit: int = 200) -> Any:
    """输出摘要，避免把大对象塞进 trace。"""
    if isinstance(obj, dict):
        return {k: _brief(v, limit) for k, v in list(obj.items())[:8]}
    s = str(obj)
    return s if len(s) <= limit else s[:limit] + "…"
