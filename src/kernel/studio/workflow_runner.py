"""工作流执行引擎 —— Studio 工作流的运行时。

把 Studio 的 Workflow 翻译成 OrchestrationChiplet 能跑的 steps，
执行并返回结果，同时更新运行统计。

设计原则：
- 复用现有能力：所有执行都走 FabricHub 路由，不重造
- 可观测：每一步都有状态、耗时、输出
- 可重入：失败了可以从失败步继续
- 自动上报：运行数据自动进 Pulse，供 Evolve 优化用
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from .workflow_models import WorkflowRun
from .workflow_store import WorkflowStore, get_workflow_store

logger = logging.getLogger(__name__)


def _default_route_fn() -> Optional[Callable]:
    """懒加载 FabricHub 的 route 函数（避免循环 import）。"""
    try:
        from kernel.plugins.fabric_hub import get_fabric_hub
        hub = get_fabric_hub()
        return hub.route
    except Exception as e:
        logger.debug("FabricHub 不可用，WorkflowRunner 将使用模拟模式: %s", e)
        return None


def _default_pulse():
    """懒加载 PulseCollector（避免循环 import）。"""
    try:
        from kernel.pulse.pulse_collector import get_pulse_collector
        return get_pulse_collector()
    except Exception:
        return None


class WorkflowRunner:
    """工作流执行器。"""

    def __init__(self, route_fn: Callable = None, store: WorkflowStore = None,
                 pulse=None):
        self._route_fn = route_fn or _default_route_fn()
        self._store = store or get_workflow_store()
        self._pulse = pulse or _default_pulse()
        self._running: Dict[str, WorkflowRun] = {}

    def set_route_fn(self, route_fn: Callable) -> None:
        self._route_fn = route_fn

    def set_pulse(self, pulse) -> None:
        self._pulse = pulse

    # ── 执行 ──

    def run(self, wf_id: str, *, input_data: Dict = None,
            context_session_id: str = "") -> WorkflowRun:
        """运行一个工作流。

        Args:
            wf_id: 工作流 ID
            input_data: 初始输入
            context_session_id: 可选——指定后启用 Context Engineering：
                - 该次运行的所有步骤结果自动灌入 ContextManager
                - 超过 max_tokens 时按优先级压缩（保最新 N 步 + 失败步）
                - 运行结束时持久化到 JSONL，可用 session_id 断点续跑
                - 不指定则不启用（保持原行为）
        """
        wf = self._store.get(wf_id)
        if not wf:
            raise ValueError(f"工作流不存在: {wf_id}")

        run = WorkflowRun.create(wf_id, wf.version)
        run.input = input_data or {}
        self._running[run.id] = run

        # Task 2: Context Engineering —— 按需创建/复用会话上下文
        ctx_manager = self._get_context_session(context_session_id, run.id)

        try:
            steps = wf.to_chiplet_steps()
            results = []
            prev_output = None

            for i, step in enumerate(steps):
                step_start = time.time()
                cap = step.get("capability", "")
                step_name = step.get("name", cap)

                logger.info("执行步骤 %d/%d: %s", i + 1, len(steps), step_name)

                # 准备 payload
                payload = step.get("payload", {}) or {}
                in_from = step.get("in_from", "previous")

                if in_from == "initial":
                    payload = {**(input_data or {}), **payload}
                elif in_from == "previous" and prev_output:
                    if isinstance(prev_output, dict):
                        payload = {**prev_output, **payload}
                    else:
                        payload["previous_output"] = prev_output

                # 如果有 prompt，加进去
                if step.get("prompt"):
                    payload["prompt"] = step["prompt"]
                    if prev_output and isinstance(prev_output, str):
                        payload["prompt"] = f"{step['prompt']}\n\n上游输出:\n{prev_output}"

                step_result = {
                    "step_index": i,
                    "step_name": step_name,
                    "capability": cap,
                    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "run_id": run.id,
                    "workflow_id": wf_id,
                }

                try:
                    if self._route_fn:
                        res = self._route_fn(cap, payload)
                        if hasattr(res, "ok") and res.ok:
                            step_result["ok"] = True
                            step_result["output"] = res.data if hasattr(res, "data") else {}
                            step_result["error"] = ""
                            if hasattr(res, "engine_id"):
                                step_result["engine"] = res.engine_id
                        else:
                            step_result["ok"] = False
                            step_result["output"] = {}
                            step_result["error"] = res.error if hasattr(res, "error") else "失败"
                    else:
                        # FabricHub 不可用时的优雅降级：模拟成功但标记 simulated
                        step_result["ok"] = True
                        step_result["output"] = {"simulated": True, "capability": cap}
                        step_result["simulated"] = True

                except Exception as e:
                    step_result["ok"] = False
                    step_result["output"] = {}
                    step_result["error"] = str(e)
                    logger.error("步骤 %s 失败: %s", step_name, e)

                step_result["duration"] = round(time.time() - step_start, 2)
                results.append(step_result)

                # Task 2: 把步骤结果灌入 ContextManager（best-effort）
                self._ctx_add_step(ctx_manager, step_result)

                # 上报单步到 Pulse
                self._report_step(wf_id, step_result)

                # 更新 prev_output
                if step_result.get("ok") and step_result.get("output"):
                    out = step_result["output"]
                    if isinstance(out, dict):
                        prev_output = out.get("content") or out.get("output") or out
                    else:
                        prev_output = out
                else:
                    # 失败了，不中断，继续下一步（OrchestrationChiplet 有更复杂的故障转移，这里简化）
                    pass

            # 总结
            ok_count = sum(1 for r in results if r.get("ok"))
            run.steps = results
            run.duration = round(time.time() - time.mktime(time.strptime(run.started_at[:19], "%Y-%m-%dT%H:%M:%S")), 2)
            run.status = "success" if ok_count == len(results) else "partial"
            run.output = {
                "success_steps": ok_count,
                "total_steps": len(results),
                "final_output": prev_output,
            }

            # Task 2: 收尾——把运行摘要灌入会话上下文 + 持久化
            self._finalize_context_session(ctx_manager, run)

        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            run.duration = round(time.time() - time.mktime(time.strptime(run.started_at[:19], "%Y-%m-%dT%H:%M:%S")), 2)
            logger.error("工作流运行失败: %s", e)

        run.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")

        # 更新工作流统计
        try:
            wf.run_count += 1
            if run.status == "success":
                success_rate = ((wf.run_count - 1) * wf.success_rate + 100) / wf.run_count
                wf.success_rate = round(success_rate, 1)
            wf.avg_duration = ((wf.run_count - 1) * wf.avg_duration + run.duration) / wf.run_count
            wf.avg_duration = round(wf.avg_duration, 2)
            self._store.save(wf)
        except Exception:
            pass

        # 保存运行记录
        self._store.save_run(run)

        # 上报到 Pulse（数据供 Evolve 优化用）
        self._report_run(wf_id, run)

        # 产品飞轮闭环：跑完自动触发 Evolve 检查
        # 低风险优化（如加 retry、调 timeout）自动应用，高风险待人工确认
        # best-effort，失败不影响主流程
        try:
            self._maybe_auto_evolve(wf_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("自动进化检查跳过: %s", e)

        # 从运行中移除
        self._running.pop(run.id, None)

        return run

    def run_by_name(self, wf_name: str, *, input_data: Dict = None) -> Optional[WorkflowRun]:
        """按名字找工作流并运行。"""
        items = self._store.list(search=wf_name, limit=1)
        if not items:
            return None
        return self.run(items[0]["id"], input_data=input_data)

    def get_running(self, run_id: str) -> Optional[WorkflowRun]:
        """获取正在运行的工作流状态。"""
        return self._running.get(run_id)

    # ── 回放调试 / what-if 分析 ──

    def replay_from_step(self, trace_id: str, step_index: int, *,
                        input_data: Dict = None,
                        override_engine: str = "",
                        override_payload: Dict = None) -> Dict[str, Any]:
        """从某个 trace 的步骤重新执行（回放调试）。

        用途（P1 Replay & Debug）：
        - 失败 trace 不想整条重跑，只从出错步起重放，验证修复是否生效
        - what-if：把某步换成另一个引擎跑，对比结果差异（不影响原工作流）
        - 单步调试：从任意步骤重放，观察该步及之后步骤的真实输出

        设计：
        - 只读原 trace + 原工作流定义，绝不修改二者（纯调试原语）
        - 复用 run() 的同款 route 调用与 prev_output 链路，保证行为一致
        - 不写 Pulse 运行统计、不触发 Evolve，避免污染正式数据
        - 与原 trace 同工作流同定义，但 steps 从 step_index 起重放

        Args:
            trace_id: 原运行记录 run_id（全局唯一）
            step_index: 从哪个步骤下标开始重放（0-based）
            input_data: 覆盖初始输入（默认沿用原 trace 的 input）
            override_engine: what-if——对该步换成此引擎（如 "ollama"）
            override_payload: what-if——对该步注入额外 payload 字段
        """
        run = self._store.get_run(trace_id)
        if run is None:
            return {"ok": False, "error": f"trace 不存在: {trace_id}"}
        wf_id = run.get("workflow_id", "")
        wf = self._store.get(wf_id)
        if wf is None:
            return {"ok": False, "error": f"工作流不存在: {wf_id}"}

        steps = wf.to_chiplet_steps()
        if not (0 <= step_index < len(steps)):
            return {"ok": False, "error": f"step_index 越界: {step_index}（共 {len(steps)} 步）"}

        # 重建 prev_output：用原 trace 中该步之前的输出作为上游上下文
        prev_output = None
        prior_steps = run.get("steps") or []
        if step_index > 0 and prior_steps:
            prior = prior_steps[step_index - 1]
            out = prior.get("output") or {}
            if isinstance(out, dict):
                prev_output = out.get("content") or out.get("output") or out
            else:
                prev_output = out

        results = []
        for i in range(step_index, len(steps)):
            step = steps[i]
            cap = step.get("capability", "")
            step_name = step.get("name", cap)
            payload = dict(step.get("payload", {}) or {})
            in_from = step.get("in_from", "previous")

            if in_from == "initial":
                payload = {**(input_data or run.get("input") or {}), **payload}
            elif in_from == "previous" and prev_output:
                if isinstance(prev_output, dict):
                    payload = {**prev_output, **payload}
                else:
                    payload["previous_output"] = prev_output

            if step.get("prompt"):
                payload["prompt"] = step["prompt"]
                if prev_output and isinstance(prev_output, str):
                    payload["prompt"] = f"{step['prompt']}\n\n上游输出:\n{prev_output}"

            # what-if：换引擎 / 注入 payload
            if i == step_index and override_engine:
                payload["engine"] = override_engine
            if i == step_index and override_payload:
                payload.update(override_payload)

            step_result: Dict[str, Any] = {
                "step_index": i,
                "step_name": step_name,
                "capability": cap,
                "replay": True,
                "from_trace": trace_id,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

            try:
                if self._route_fn:
                    res = self._route_fn(cap, payload)
                    if hasattr(res, "ok") and res.ok:
                        step_result["ok"] = True
                        step_result["output"] = res.data if hasattr(res, "data") else {}
                        if hasattr(res, "engine_id"):
                            step_result["engine"] = res.engine_id
                    else:
                        step_result["ok"] = False
                        step_result["output"] = {}
                        step_result["error"] = res.error if hasattr(res, "error") else "失败"
                else:
                    # 优雅降级：模拟成功但标记 simulated
                    step_result["ok"] = True
                    step_result["output"] = {"simulated": True, "capability": cap}
                    step_result["simulated"] = True
            except Exception as e:
                step_result["ok"] = False
                step_result["output"] = {}
                step_result["error"] = str(e)
                logger.error("重放步骤 %s 失败: %s", step_name, e)

            step_result["duration"] = 0.0
            results.append(step_result)

            # 更新上游上下文
            if step_result.get("ok") and step_result.get("output"):
                out = step_result["output"]
                if isinstance(out, dict):
                    prev_output = out.get("content") or out.get("output") or out
                else:
                    prev_output = out

        return {
            "ok": True,
            "trace_id": trace_id,
            "workflow_id": wf_id,
            "replay_from": step_index,
            "step_count": len(results),
            "all_ok": all(r.get("ok") for r in results),
            "results": results,
        }

    # ── Pulse 上报 ──

    def _report_run(self, wf_id: str, run: WorkflowRun) -> None:
        """上报工作流运行数据到 Pulse。"""
        if not self._pulse:
            return
        try:
            success = run.status == "success"

            # 汇总本次运行的 token 用量（来自各步骤的 CostTracker 记录）
            token_summary = self._aggregate_run_tokens(run)

            run_data: Dict[str, Any] = {
                "status": run.status,
                "success": success,
                "duration": run.duration,
                "version": run.workflow_version,
                "run_id": run.id,
                "step_count": len(run.steps) if run.steps else 0,
            }
            if token_summary is not None:
                run_data["token_usage"] = token_summary

            self._pulse.record_run(wf_id, run_data)
        except Exception as e:
            logger.debug("Pulse 运行上报失败: %s", e)

    def _aggregate_run_tokens(self, run: WorkflowRun) -> Optional[Dict[str, Any]]:
        """聚合本次运行所有步骤的 token 用量。

        从 CostTracker 反查本次 run_id 的记录，避免重复计算。
        """
        if not run.steps:
            return None
        run_id = run.id
        tracker = self._get_cost_tracker()
        if tracker is None:
            return None
        try:
            records = tracker.get_recent_records(limit=500, workflow_id=run.workflow_id)
            total_prompt = 0
            total_completion = 0
            models_used: Dict[str, int] = {}
            for r in records:
                if r.get("run_id") != run_id:
                    continue
                total_prompt += int(r.get("prompt_tokens", 0))
                total_completion += int(r.get("completion_tokens", 0))
                m = r.get("model", "") or "unknown"
                models_used[m] = models_used.get(m, 0) + int(r.get("total_tokens", 0))
            if total_prompt == 0 and total_completion == 0:
                return None
            return {
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "model": ",".join(models_used.keys()) if models_used else "",
                "run_id": run_id,
            }
        except Exception as e:
            logger.debug("聚合运行 token 失败: %s", e)
            return None

    def _report_step(self, wf_id: str, step_result: Dict[str, Any]) -> None:
        """上报单步数据到 Pulse。"""
        if not self._pulse:
            return
        try:
            self._pulse.record_step(wf_id, {
                "step_name": step_result.get("step_name", ""),
                "capability": step_result.get("capability", ""),
                "ok": step_result.get("ok", False),
                "duration": step_result.get("duration", 0),
                "error": step_result.get("error", ""),
                "engine": step_result.get("engine", ""),
            })
        except Exception as e:
            logger.debug("Pulse 步骤上报失败: %s", e)

        # Token 用量上报（Task 1: Cost Observability）
        # 优先使用引擎返回的 usage 字段；缺失时按输出文本估算
        try:
            tu = self._extract_token_usage(step_result)
            if tu is not None:
                tracker = self._get_cost_tracker()
                if tracker is not None:
                    tracker.record(
                        workflow_id=wf_id,
                        user_id=step_result.get("user_id", "anonymous"),
                        agent_id=step_result.get("engine", ""),
                        model=tu["model"],
                        prompt_tokens=tu["prompt_tokens"],
                        completion_tokens=tu["completion_tokens"],
                        duration_ms=step_result.get("duration", 0) * 1000,
                        run_id=step_result.get("run_id", ""),
                    )
        except Exception as e:
            logger.debug("步骤 token 用量上报失败: %s", e)

    def _extract_token_usage(self, step_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从步骤结果提取 token 用量。

        优先用引擎返回的 usage 字段（OpenAI/litellm 标准）；缺失时按输出文本估算。
        只对涉及 LLM 的步骤（capability 含 'llm' / 'chat' / 'inference'，或 output 有 usage）做。
        """
        out = step_result.get("output") or {}
        if not isinstance(out, dict):
            return None

        cap = (step_result.get("capability") or "").lower()
        engine = (step_result.get("engine") or "").lower()

        # 不是 LLM 类步骤就不报（避免对 search/code_exec 这类没 token 概念的步骤瞎报）
        is_llm_step = (
            "llm" in cap or "chat" in cap or "inference" in cap
            or "llm" in engine or "litellm" in engine or "ollama" in engine
            or "agnes" in engine or "ag2" in engine or "openclaw" in engine
            or "usage" in out  # 引擎显式返回了 usage
        )
        if not is_llm_step:
            return None

        # 1. 引擎显式返回的 usage（OpenAI 标准字段）
        usage = out.get("usage") or out.get("token_usage") or {}
        if isinstance(usage, dict) and (usage.get("prompt_tokens") or usage.get("completion_tokens")):
            return {
                "model": out.get("model", "") or step_result.get("engine", ""),
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
            }

        # 2. 从文本估算（content / output / result 字段）
        from kernel.pulse.cost_tracker import count_tokens
        text_parts = []
        for k in ("content", "output", "result", "text", "response"):
            v = out.get(k)
            if isinstance(v, str) and v:
                text_parts.append(v)
            elif isinstance(v, dict):
                # 嵌套的 content/output
                for sub_k in ("content", "output", "text"):
                    sv = v.get(sub_k)
                    if isinstance(sv, str) and sv:
                        text_parts.append(sv)

        completion_text = "\n".join(text_parts)
        if not completion_text:
            return None

        # prompt_tokens 难以精确恢复（payload 在调用方），按 completion 长度近似
        completion_tokens = count_tokens(completion_text)
        if completion_tokens == 0:
            return None

        return {
            "model": out.get("model", "") or step_result.get("engine", ""),
            "prompt_tokens": 0,  # 无法精确恢复，留 0；下游按 completion 估算
            "completion_tokens": completion_tokens,
        }

    def _get_cost_tracker(self):
        """懒加载 CostTracker（避免循环 import）。"""
        if not hasattr(self, "_cost_tracker_cache") or self._cost_tracker_cache is None:
            try:
                from kernel.pulse.cost_tracker import get_cost_tracker
                self._cost_tracker_cache = get_cost_tracker()
            except Exception:
                self._cost_tracker_cache = False
        return self._cost_tracker_cache if self._cost_tracker_cache is not False else None

    # ── Task 2: Context Engineering ──

    def _get_context_session(self, session_id: str, run_id: str):
        """按需创建/复用 ContextManager 会话。

        - session_id 显式指定：用该 ID 创建/获取会话（跨运行复用）
        - session_id 为空：返回 None，不启用上下文工程（保持原行为）
        - ContextManager 不可用时优雅降级为 None

        会话 ID 优先级：显式 session_id > 默认 'wf-{wf_id}-{run_id}'
        但只有显式传 session_id 时才启用（避免每次运行都产生 JSONL 文件，污染磁盘）。
        """
        if not session_id:
            return None
        try:
            from kernel.context.context_manager import get_session
            # max_tokens 默认 8000；可通过环境变量 AOS_CONTEXT_MAX_TOKENS 覆盖
            import os
            max_tokens = int(os.environ.get("AOS_CONTEXT_MAX_TOKENS", "8000"))
            return get_session(session_id, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            logger.debug("ContextManager 不可用: %s", e)
            return None

    @staticmethod
    def _ctx_add_step(ctx_manager, step_result: Dict[str, Any]) -> None:
        """best-effort 把步骤结果灌入 ContextManager。失败仅 debug 日志。"""
        if ctx_manager is None:
            return
        try:
            ctx_manager.add_step(step_result)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _finalize_context_session(ctx_manager, run: WorkflowRun) -> None:
        """工作流收尾：把运行摘要作为总结条目灌入 + 持久化 JSONL。"""
        if ctx_manager is None:
            return
        try:
            ctx_manager.add_step({
                "step_index": -1,
                "step_name": "workflow_summary",
                "capability": "workflow_runner",
                "ok": run.status == "success",
                "error": run.error or ("" if run.status == "success" else "工作流执行失败"),
                "output": {
                    "run_id": run.id,
                    "status": run.status,
                    "duration": run.duration,
                    "step_count": len(run.steps) if run.steps else 0,
                },
            })
            ctx_manager.persist()
        except Exception:  # noqa: BLE001
            pass

    def _maybe_auto_evolve(self, wf_id: str) -> None:
        """工作流跑完后，自动触发 Evolve 检查，低风险优化自动应用。

        这是产品飞轮闭环的核心：
        运行 → 采集数据 → 分析 → 生成优化提案 → 低风险自动应用 → 再运行

        为了避免每次跑都触发（浪费资源），用简单的节流：
        - 每 5 次运行才检查一次
        - 只应用低风险（risk_level=low）且 auto_applicable 的提案
        - 每次最多应用 1 个提案（渐进式优化，防失控）
        """
        try:
            evolve = self._get_evolve()
            if evolve is None:
                return

            # 节流：读运行次数，每 5 次才检查一次
            wf = self._store.get(wf_id)
            if wf is None:
                return
            run_count = wf.run_count
            if run_count % 5 != 0:
                return  # 还没到检查的时机

            logger.info("触发自动进化检查: wf=%s, run_count=%d", wf_id, run_count)

            # 生成优化提案
            proposals = evolve.generate_proposals(wf_id)
            if not proposals:
                return

            # 只应用第一个低风险提案
            applied_count = 0
            for prop in proposals:
                if prop.risk_level == "low" and prop.auto_applicable and not prop.applied:
                    result = evolve.apply_proposal(prop.id, self._store)
                    if result.get("ok"):
                        applied_count += 1
                        logger.info("自动优化已应用: %s -> %s", prop.id, prop.title)
                        break  # 每次只应用一个，渐进式

            if applied_count == 0:
                logger.debug("无低风险自动优化可应用: wf=%s", wf_id)

        except Exception as e:
            logger.debug("自动进化检查失败: %s", e)

    def _get_evolve(self):
        """懒加载 EvolveEngine（避免循环 import）。"""
        if not hasattr(self, "_evolve") or self._evolve is None:
            try:
                from kernel.evolve.evolve_engine import get_evolve_engine
                self._evolve = get_evolve_engine()
            except Exception:
                self._evolve = None
        return self._evolve


# 单例
_runner: Optional[WorkflowRunner] = None


def get_workflow_runner() -> WorkflowRunner:
    global _runner
    if _runner is None:
        _runner = WorkflowRunner()
    return _runner
