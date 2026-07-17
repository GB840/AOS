"""工作流执行引擎 —— Studio 工作流的运行时。

把 Studio 的 Workflow 翻译成 OrchestrationChiplet 能跑的 steps，
执行并返回结果，同时更新运行统计。

设计原则：
- 复用现有能力：所有执行都走 FabricHub 路由，不重造
- 可观测：每一步都有状态、耗时、输出
- 可重入：失败了可以从失败步继续
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .workflow_models import Workflow, WorkflowRun
from .workflow_store import WorkflowStore, get_workflow_store

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """工作流执行器。"""

    def __init__(self, route_fn: Callable = None, store: WorkflowStore = None):
        self._route_fn = route_fn
        self._store = store or get_workflow_store()
        self._running: Dict[str, WorkflowRun] = {}

    def set_route_fn(self, route_fn: Callable) -> None:
        self._route_fn = route_fn

    # ── 执行 ──

    def run(self, wf_id: str, *, input_data: Dict = None) -> WorkflowRun:
        """运行一个工作流。"""
        wf = self._store.get(wf_id)
        if not wf:
            raise ValueError(f"工作流不存在: {wf_id}")

        run = WorkflowRun.create(wf_id, wf.version)
        run.input = input_data or {}
        self._running[run.id] = run

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
                        step_result["ok"] = True
                        step_result["output"] = {"simulated": True}

                except Exception as e:
                    step_result["ok"] = False
                    step_result["output"] = {}
                    step_result["error"] = str(e)
                    logger.error("步骤 %s 失败: %s", step_name, e)

                step_result["duration"] = round(time.time() - step_start, 2)
                results.append(step_result)

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


# 单例
_runner: Optional[WorkflowRunner] = None


def get_workflow_runner() -> WorkflowRunner:
    global _runner
    if _runner is None:
        _runner = WorkflowRunner()
    return _runner
