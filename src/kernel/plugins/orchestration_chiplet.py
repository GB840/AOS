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
    ],
    # 可选：并行 DAG。每组内的步骤经线程池并发执行，组间保持顺序；
    # 未被任何组覆盖的步骤在全部组跑完后顺序补跑。
    "parallel_groups": [[0, 1], [2, 3]]
    #   组内元素可为步骤下标(int)，或步骤 id / capability 字符串。
  }

输出（InvokeResult.data）：
  {"ok_steps": N, "failed_steps": M, "final": <最后成功步输出>,
   "trace": [每步 engine_id+输出摘要], "parallel": true?}

注：并发模式下 `in_from:"previous"` 在步骤实际执行时读取「截至此刻最近一次
成功输出」（组间/组内并发下不保证顺序）。需要严格先后依赖的步骤请放进同一
顺序补跑段，或拆到不同 parallel_group。
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability


def _as_str(cap) -> str:
    return cap.value if hasattr(cap, "value") else str(cap)


class _RunState:
    """顺序/并发共享的执行状态；所有写操作加锁，保证线程安全。"""

    def __init__(self, initial: Dict[str, Any]) -> None:
        self.lock = threading.Lock()
        self.initial = initial
        self.last_success_out: Optional[Dict[str, Any]] = None
        self.context: Optional[Dict[str, Any]] = None
        self.ok_steps = 0
        self.failed_steps = 0
        self.trace: List[Dict[str, Any]] = []


class OrchestrationChiplet(BaseAgentAdapter):
    """把多芯粒按序/并行串联成流水线的编排芯粒（用户态，非内核）。"""

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

        parallel_groups = spec.get("parallel_groups")
        if parallel_groups:
            return self._invoke_parallel(steps, spec, parallel_groups)

        # —— 顺序路径（既有行为，保持不变）——
        state = _RunState(spec.get("initial") or {})
        for idx, step in enumerate(steps):
            self._run_step(idx, step, state)
        return self._finalize(state)

    def _invoke_parallel(self, steps, spec, parallel_groups) -> InvokeResult:
        state = _RunState(spec.get("initial") or {})
        covered: set[int] = set()
        for group in parallel_groups:
            idxs = self._resolve_group(group, steps)
            if not idxs:
                continue
            covered.update(idxs)
            # 组内并发：提交到线程池，等本组全部完成再进下一组（组间顺序）
            with ThreadPoolExecutor(max_workers=max(1, len(idxs))) as ex:
                futures = [ex.submit(self._run_step, i, steps[i], state) for i in idxs]
                for _ in as_completed(futures):
                    pass  # 结果已在 _run_step 内写入 state
        # 跑未被任何 parallel_group 覆盖的步骤（顺序补跑）
        for idx, step in enumerate(steps):
            if idx in covered:
                continue
            self._run_step(idx, step, state)
        return self._finalize(state, parallel=True)

    @staticmethod
    def _resolve_group(group, steps) -> List[int]:
        """把一组描述解析为步骤下标。支持 int 下标 / 步骤 id / capability 字符串。"""
        idxs: List[int] = []
        for g in group:
            if isinstance(g, int):
                if 0 <= g < len(steps):
                    idxs.append(g)
            else:
                for i, s in enumerate(steps):
                    if s.get("id") == g or _as_str(s.get("capability")) == g:
                        idxs.append(i)
                        break
        return idxs

    def _run_step(self, idx: int, step: Dict[str, Any], state: _RunState) -> None:
        """执行单步并就地更新 state（线程安全）。无返回值。"""
        cap = step.get("capability")
        if not cap:
            with state.lock:
                state.failed_steps += 1
                state.trace.append({"step": idx, "capability": None,
                                    "ok": False, "error": "缺 capability"})
            return
        # 解析本步入参
        if "in" in step:
            payload = step["in"]
        elif step.get("in_from") == "previous":
            with state.lock:
                if state.last_success_out is None:
                    # 上游从未成功产出 → 依赖断裂，本步无法获取真实输入，判为依赖失败
                    state.failed_steps += 1
                    state.trace.append({"step": idx, "capability": _as_str(cap),
                                        "ok": False,
                                        "error": "依赖的上游步骤尚未成功产出，本步无法获取输入（语义空转已阻止）"})
                    return
                payload = state.last_success_out
        elif step.get("in_from") == "initial":
            field = step.get("field")
            with state.lock:
                payload = {field: state.initial.get(field)} if field else dict(state.initial)
        else:
            payload = {}
        # 委派给下游芯粒（经同一路由层，故障隔离同样生效）
        res = self._route_fn(_as_str(cap), payload)
        if isinstance(res, InvokeResult) and not res.ok:
            # 单步容错：记录失败、保留上一次成功输出作为后续入参、继续跑
            with state.lock:
                state.failed_steps += 1
                state.trace.append({"step": idx, "capability": _as_str(cap),
                                    "ok": False, "error": res.error})
            return
        step_out = res.data if isinstance(res, InvokeResult) else res
        out_ctx = step_out if isinstance(step_out, dict) else {"result": step_out}
        with state.lock:
            state.last_success_out = out_ctx  # 供后续 in_from:previous 依赖
            state.context = out_ctx
            state.ok_steps += 1
            state.trace.append({"step": idx, "capability": _as_str(cap),
                                "ok": True, "out": _brief(step_out)})

    @staticmethod
    def _finalize(state: _RunState, parallel: bool = False) -> InvokeResult:
        if state.ok_steps == 0:
            return InvokeResult(
                ok=False,
                error="orchestrator: 所有步骤均失败（见 trace）",
                data={"ok_steps": 0, "failed_steps": state.failed_steps, "trace": state.trace},
            )
        return InvokeResult(
            ok=True,
            data={"ok_steps": state.ok_steps, "failed_steps": state.failed_steps,
                  "final": state.context, "trace": state.trace,
                  **({"parallel": True} if parallel else {})},
        )


def _brief(obj: Any, limit: int = 200) -> Any:
    """输出摘要，避免把大对象塞进 trace。"""
    if isinstance(obj, dict):
        return {k: _brief(v, limit) for k, v in list(obj.items())[:8]}
    s = str(obj)
    return s if len(s) <= limit else s[:limit] + "…"
