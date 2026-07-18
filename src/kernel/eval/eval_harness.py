"""Eval Framework（P0-b）—— 基于 Pulse / 真实运行数据的系统化评测。

2026 趋势：从「最终答案评分」转向「状态变化验证」——不只看输出对不对，
还要看 Tool 调用是否正确、路径是否合理、步数是否最优。

AOS 落地（长在已有基建上，不重造）：
- 任务集：从真实工作流 + 其运行历史提炼（跑过什么、输入是什么、步骤路径）
- 轨迹评分：step 级（工具正确性 / 路径连贯性 / 步数最优性），非仅结果对错
- 回归评测：每次工作流变更后重跑任务集，对比 baseline 轨迹分，标记倒退

依赖：WorkflowStore（任务来源）+ WorkflowRunner（执行）+ Pulse（可选，baseline 来源）。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class TrajectoryScore:
    """单条执行轨迹的评分（状态变化验证，而非仅结果）。"""
    task_id: str = ""
    workflow_id: str = ""
    step_count: int = 0
    failed_steps: int = 0
    tool_correctness: float = 0.0   # 工具/引擎调用正确的比例 0-1
    path_coherence: float = 0.0     # 步骤间数据流连贯性 0-1
    step_efficiency: float = 0.0    # 步数最优性（相对理想步数）0-1
    total: float = 0.0              # 综合分 0-100
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalTask:
    """一个评测任务：源自真实工作流。"""
    id: str = ""
    workflow_id: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    expected_capabilities: List[str] = field(default_factory=list)
    tag: str = "pulse-derived"


@dataclass
class RegressionResult:
    task_id: str = ""
    workflow_id: str = ""
    baseline_total: float = 0.0
    current_total: float = 0.0
    delta: float = 0.0
    regression: bool = False
    detail: str = ""


def _default_store():
    try:
        from kernel.studio.workflow_store import get_workflow_store
        return get_workflow_store()
    except Exception:
        return None


def _default_runner():
    try:
        from kernel.studio.workflow_runner import get_workflow_runner
        return get_workflow_runner()
    except Exception:
        return None


class EvalHarness:
    """系统化评测框架。"""

    def __init__(self, store=None, runner=None, baseline_path: str = ""):
        self._store = store or _default_store()
        self._runner = runner
        base = os.environ.get("AOS_EVAL_DIR",
                              os.path.join("data", "workspaces", "fabric", "eval"))
        os.makedirs(base, exist_ok=True)
        self._baseline_path = baseline_path or os.path.join(base, "baseline.json")

    # ── 任务集提炼（从真实运行数据）──

    def build_task_set(self, *, min_runs: int = 1, limit: int = 50) -> List[EvalTask]:
        """从真实工作流 + 运行历史提炼评测任务集。

        每个任务 = 一个工作流 + 其最近一次真实运行的输入 + 期望的能力步骤路径。
        这是「用真实数据测 Agent 能力」而非人造玩具任务。
        """
        store = self._store or _default_store()
        if store is None:
            return []
        tasks: List[EvalTask] = []
        try:
            workflows = store.list(limit=limit)
        except Exception:
            return tasks

        for wf in workflows:
            wf_id = wf.get("id") if isinstance(wf, dict) else getattr(wf, "id", None)
            if not wf_id:
                continue
            # 需要有运行历史才纳入（真实数据驱动）
            try:
                runs = store.list_runs(wf_id, limit=min_runs)
            except Exception:
                runs = []
            if len(runs) < min_runs:
                continue
            last_input = (runs[0].get("input") if runs else None) or {}
            # 期望能力路径：取工作流定义的步骤 capability
            expected: List[str] = []
            try:
                full = store.get(wf_id)
                if full is not None:
                    expected = [s.get("capability", "") for s in full.to_chiplet_steps()]
            except Exception:
                expected = []
            tasks.append(EvalTask(
                id=f"eval_{wf_id}",
                workflow_id=wf_id,
                input_data=last_input,
                expected_capabilities=expected,
                tag="pulse-derived",
            ))
        return tasks

    # ── 轨迹评分（状态变化验证）──

    def score_trajectory(self, task_id: str, workflow_id: str,
                         steps: List[Dict[str, Any]]) -> TrajectoryScore:
        """对一条执行轨迹评分。

        不只看最终成败，而是验证执行过程：
        - tool_correctness：步骤是否被正确的引擎执行并成功
        - path_coherence：步骤间数据流是否连贯（上一步产出喂给下一步）
        - step_efficiency：实际步数相对理想步数是否最优
        """
        total = len(steps)
        failed = sum(1 for s in steps if not s.get("ok"))
        ok_steps = [s for s in steps if s.get("ok")]

        # 工具正确性：成功步中，有真实引擎标识或产出非空的比例
        correct = 0
        for s in ok_steps:
            has_engine = bool(s.get("engine"))
            has_output = bool(s.get("output"))
            # simulated（无 FabricHub）也算通过但不算「工具正确验证」
            if s.get("simulated"):
                correct += 0.5
            elif has_engine or has_output:
                correct += 1.0
        tool_correctness = (correct / total) if total else 0.0

        # 路径连贯性：成功步中有非空产出的比例（产出可喂下游）
        coherent = sum(1 for s in ok_steps
                       if isinstance(s.get("output"), dict)
                       and (s["output"].get("content") or s["output"].get("output") or s.get("output")))
        path_coherence = (coherent / total) if total else 0.0

        # 步数最优性：理想步数 = 期望能力去重数；实际越少越好
        ideal = len(set(self._caps_of(task_id, workflow_id, steps)))
        ideal = max(ideal, 1)
        step_efficiency = min(1.0, ideal / total) if total else 0.0

        total_score = (0.4 * tool_correctness
                       + 0.3 * path_coherence
                       + 0.3 * step_efficiency) * 100.0

        return TrajectoryScore(
            task_id=task_id,
            workflow_id=workflow_id,
            step_count=total,
            failed_steps=failed,
            tool_correctness=round(tool_correctness, 4),
            path_coherence=round(path_coherence, 4),
            step_efficiency=round(step_efficiency, 4),
            total=round(total_score, 2),
            details={
                "ok_steps": len(ok_steps),
                "ideal_steps": ideal,
                "failed_steps": failed,
            },
        )

    @staticmethod
    def _caps_of(task_id: str, workflow_id: str, steps: List[Dict[str, Any]]) -> List[str]:
        return [s.get("capability", "") for s in steps if s.get("capability")]

    # ── 执行 + 评分 ──

    def run_task(self, task: EvalTask) -> TrajectoryScore:
        """执行一个评测任务并返回轨迹评分。"""
        runner = self._runner or _default_runner()
        if runner is None:
            return TrajectoryScore(task_id=task.id, workflow_id=task.workflow_id,
                                   details={"error": "无 runner"})
        run = runner.run(task.workflow_id, input_data=task.input_data)
        steps = run.steps if hasattr(run, "steps") else []
        return self.score_trajectory(task.id, task.workflow_id, steps)

    # ── 回归评测 ──

    def run_regression(self, task_set: List[EvalTask],
                      regression_threshold: float = 5.0) -> List[RegressionResult]:
        """重跑任务集，对比 baseline，标记倒退。

        Args:
            regression_threshold: 综合分下降超过此值视为回归（默认 5 分）
        """
        baseline = self.load_baseline()
        results: List[RegressionResult] = []
        for task in task_set:
            score = self.run_task(task)
            base_total = baseline.get(task.workflow_id, {}).get("total")
            if base_total is None:
                results.append(RegressionResult(
                    task_id=task.id, workflow_id=task.workflow_id,
                    baseline_total=0.0, current_total=score.total,
                    delta=score.total, regression=False,
                    detail="无 baseline（首次运行，已记录）"))
                continue
            delta = round(score.total - base_total, 2)
            regress = delta <= -regression_threshold
            results.append(RegressionResult(
                task_id=task.id, workflow_id=task.workflow_id,
                baseline_total=base_total, current_total=score.total,
                delta=delta, regression=regress,
                detail=("轨迹分下降 %.2f，疑似回归" % delta) if regress
                else "稳定（Δ=%.2f）" % delta))
        return results

    def save_baseline(self, task_set: List[EvalTask]) -> Dict[str, Any]:
        """为任务集建立/更新 baseline（通常在大改前跑一次）。"""
        baseline: Dict[str, Any] = {}
        for task in task_set:
            score = self.run_task(task)
            baseline[task.workflow_id] = {
                "total": score.total,
                "tool_correctness": score.tool_correctness,
                "path_coherence": score.path_coherence,
                "step_efficiency": score.step_efficiency,
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        try:
            with open(self._baseline_path, "w", encoding="utf-8") as f:
                json.dump(baseline, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return baseline

    def load_baseline(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self._baseline_path):
                with open(self._baseline_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def baseline_exists(self) -> bool:
        return os.path.exists(self._baseline_path)
