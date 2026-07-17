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
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult, extract_text
from core.fabric.capability import Capability
from core.fabric import a2ui as _a2ui


def _as_str(cap) -> str:
    return cap.value if hasattr(cap, "value") else str(cap)


class _RunState:
    """顺序/并发共享的执行状态；所有写操作加锁，保证线程安全。"""

    def __init__(self, initial: Dict[str, Any], task_id: Optional[str] = None,
                 auto_handoff: bool = False, seed_context: Optional[Dict[str, Any]] = None) -> None:
        self.lock = threading.Lock()
        self.initial = initial
        self.task_id = task_id or str(uuid.uuid4())[:8]
        self.auto_handoff = auto_handoff
        # 上下文续接（求是引擎式反思）：反思轮把上轮已成功步的真实产出
        # 作为起点，使「重设计下一步」的首步能拿到正确上游输入，且不再重跑
        # 已成功的步（避免回归 + 省步数）。seed=None 时行为不变。
        self.last_success_out: Optional[Dict[str, Any]] = seed_context
        self.context: Optional[Dict[str, Any]] = seed_context
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
        state = _RunState(spec.get("initial") or {}, task_id=spec.get("task_id"),
                          auto_handoff=spec.get("auto_handoff", False),
                          seed_context=spec.get("seed_context"))
        for idx, step in enumerate(steps):
            self._run_step(idx, step, state)
        return self._finalize(state)

    def _invoke_parallel(self, steps, spec, parallel_groups) -> InvokeResult:
        state = _RunState(spec.get("initial") or {}, task_id=spec.get("task_id"),
                          auto_handoff=spec.get("auto_handoff", False),
                          seed_context=spec.get("seed_context"))
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
                                    "engine": None, "ok": False,
                                    "error": "缺 capability"})
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
                                        "engine": None, "ok": False,
                                        "error": "依赖的上游步骤尚未成功产出，本步无法获取输入（语义空转已阻止）"})
                    return
                payload = state.last_success_out
            # 投影：把上游产出里可读的文本喂给「文本消费型」下游
            # （openclaw 要 text / mem0 要 text+query）。不覆盖上游已有的显式字段，
            # 只在缺失时补全，避免「上游有真实产出却被当成空消息 → 假失败」。
            if isinstance(payload, dict):
                txt = extract_text(payload)
                if txt and "text" not in payload:
                    payload = dict(payload)
                    payload["text"] = txt
            # 桥接 prompt：当步骤带 "prompt" 字段时，把 prompt 指令与上游产出
            # 合并成 LLM 可消费的 payload。这是 think→do 闭环里「想」的接缝——
            # 让 LLM 能看到上游搜索/执行结果，并按指令为下游生成代码/消息等。
            step_prompt = step.get("prompt")
            if step_prompt:
                prev_text = extract_text(payload) if isinstance(payload, dict) else str(payload)
                payload = {"prompt": f"{step_prompt}\n\n上游产出:\n{prev_text}"}
            # 如果步骤带 instruction（ag2 规划的干净指令），注入 payload
            # 供下游（如 code_exec）优先使用，因为 in_from:previous 给的是
            # 上一步的原始输出（如搜索结果），不一定是可执行命令。
            instruction = step.get("instruction")
            if instruction and isinstance(payload, dict) and "instruction" not in payload:
                payload = dict(payload)
                payload["instruction"] = instruction
            # 把原始任务带下去，供推理步知道要产出什么（否则只能看到上游材料，
            # 容易把搜索结果原样回显而非合成报告）。
            if isinstance(payload, dict) and state.initial.get("task") and "original_task" not in payload:
                payload = dict(payload)
                payload["original_task"] = state.initial.get("task")
        elif step.get("in_from") == "initial":
            field = step.get("field")
            with state.lock:
                payload = {field: state.initial.get(field)} if field else dict(state.initial)
        else:
            payload = {}
        # 委派给下游芯粒（经同一路由层，故障隔离同样生效）
        res = self._route_fn(_as_str(cap), payload)
        _eng = res.engine_id if isinstance(res, InvokeResult) else None
        if isinstance(res, InvokeResult) and not res.ok:
            # 单步容错：记录失败、保留上一次成功输出作为后续入参、继续跑
            with state.lock:
                state.failed_steps += 1
                state.trace.append({"step": idx, "capability": _as_str(cap),
                                    "engine": _eng, "ok": False, "error": res.error})
            return
        step_out = res.data if isinstance(res, InvokeResult) else res
        out_ctx = step_out if isinstance(step_out, dict) else {"result": step_out}
        with state.lock:
            state.last_success_out = out_ctx  # 供后续 in_from:previous 依赖
            state.context = out_ctx
            state.ok_steps += 1
            _rm = step_out.get("real_metrics") if isinstance(step_out, dict) else None
            state.trace.append({"step": idx, "capability": _as_str(cap),
                                "engine": _eng, "ok": True, "out": _brief(step_out),
                                **({"real_metrics": _rm} if _rm is not None else {})})

    @staticmethod
    def _finalize(state: _RunState, parallel: bool = False) -> InvokeResult:
        if state.ok_steps == 0:
            return InvokeResult(
                ok=False,
                error="orchestrator: 所有步骤均失败（见 trace）",
                data={"ok_steps": 0, "failed_steps": state.failed_steps, "trace": state.trace},
            )
        if state.auto_handoff:
            _auto_store_handoff(state)
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


def orchestration_result_to_a2ui(result: InvokeResult) -> Optional[Dict[str, Any]]:
    """把编排执行结果转为 A2UI surface（agent 画界面闭环）。

    仅当 result.ok 且含 trace 时返回合并 surface；否则返回 None（不伪造）。
    返回的 surface 可直接交给前端 /api/a2ui/render 渲染。
    """
    if not isinstance(result, InvokeResult) or not result.ok:
        return None
    data = result.data or {}
    trace = data.get("trace")
    if not isinstance(trace, list):
        return None
    return _a2ui.build_a2ui_report(
        trace,
        ok_steps=data.get("ok_steps", 0),
        failed_steps=data.get("failed_steps", 0),
        final=data.get("final"),
    )


def render_orchestration_result(result: InvokeResult, standalone: bool = True) -> str:
    """把编排执行结果渲染为 A2UI 安全 HTML（失败诚实降级，不伪造）。

    成功且含 trace → build_a2ui_report 报告；失败或无 trace → 渲染错误
    surface（不把失败包装成「成功报告」）。返回的 HTML 可直接浏览器查看。
    """
    surface = orchestration_result_to_a2ui(result)
    if surface is None:
        # 诚实降级：编排失败时不伪造成功报告，渲染错误 surface。
        # root 必须是单个组件 id（契约），多组件用 Column 包裹后 root 其上。
        err = getattr(result, "error", None) or "编排未产生可用 trace"
        b = _a2ui.A2UIBuilder(surface_id="aos-orch-fail",
                              theme={"primaryColor": "#b3402f"})
        b.add("title", _a2ui.text("编排流水线执行失败", variant="h2"))
        b.add("err", _a2ui.text(str(err), variant="body"))
        b.add("root", _a2ui.column(["title", "err"]))
        b.root("root")
        surface = b.surface()
    return _a2ui.render_html(surface, standalone=standalone)


def _auto_store_handoff(state: "_RunState") -> None:
    """流水线收尾：把执行结果汇成结构化交接信封，自动存 IMA（opt-in）。

    仅当 state.auto_handoff=True 时由 _finalize 调用。失败仅告警、不阻断
    主流程返回——交接是「增强」而非「必需」步骤。
    若 IMA 未配置，store_handoff 返回 success=False 且无副作用。
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from core.fabric.handoff import HandoffEnvelope, store_handoff

        confirmed: List[str] = []
        risks: List[str] = []
        for t in state.trace:
            cap = t.get("capability") or "?"
            if t.get("ok"):
                confirmed.append(f"步骤{t.get('step')}({cap}): {_brief(t.get('out'))}")
            else:
                risks.append(f"步骤{t.get('step')}({cap}) 失败: {t.get('error')}")

        envelope = HandoffEnvelope(
            task_id=state.task_id,
            title=f"Orchestration 交接-{state.task_id}",
            summary=f"完成 {state.ok_steps} 步，失败 {state.failed_steps} 步",
            confirmed_facts=confirmed,
            risk_boundary=risks,
            source="OrchestrationChiplet",
            tags=["handoff", "orchestration"],
        )
        res = store_handoff(envelope)  # skill=None → 自建 IMASkill（未配置则无副作用）
        if not res.get("success"):
            logger.warning("流水线交接自动存 IMA 未成功（可能未配置 IMA）：%s", res.get("error"))
    except Exception as e:
        logger.warning("流水线交接自动存 IMA 异常（已忽略）：%s", e)
