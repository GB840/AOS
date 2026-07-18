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


# ═══════════════════════════════════════════════════════════════════
#  数据集 / 用例 / 运行报告 API（Task 3: Eval Framework 完整版）
#  与上方「轨迹评分」共存：轨迹评分用于从真实运行提炼的任务集评测；
#  下方数据集 API 用于人工/自动维护的结构化评测集，二者互不冲突。
# ═══════════════════════════════════════════════════════════════════

def _eval_dir() -> str:
    base = os.environ.get("AOS_EVAL_DIR",
                          os.path.join("data", "workspaces", "fabric", "eval"))
    os.makedirs(base, exist_ok=True)
    return base


def _datasets_dir() -> str:
    d = os.path.join(_eval_dir(), "datasets")
    os.makedirs(d, exist_ok=True)
    return d


def _baselines_dir() -> str:
    d = os.path.join(_eval_dir(), "baselines")
    os.makedirs(d, exist_ok=True)
    return d


def _runs_dir() -> str:
    d = os.path.join(_eval_dir(), "runs")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class EvalCase:
    """一个评测用例（期望 + 输入）。"""
    id: str = ""
    name: str = ""
    task: str = ""                      # 任务描述（喂给 inference）
    workflow_id: str = ""               # 工作流 ID（与 task 二选一）
    input_data: Dict[str, Any] = field(default_factory=dict)
    expected_keywords: List[str] = field(default_factory=list)
    expected_success: bool = True
    expected_min_steps: int = 0
    expected_max_duration: float = 0.0
    expected_max_cost_usd: float = 0.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "task": self.task,
            "workflow_id": self.workflow_id, "input_data": self.input_data,
            "expected_keywords": self.expected_keywords,
            "expected_success": self.expected_success,
            "expected_min_steps": self.expected_min_steps,
            "expected_max_duration": self.expected_max_duration,
            "expected_max_cost_usd": self.expected_max_cost_usd,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvalCase":
        return cls(
            id=d.get("id", ""), name=d.get("name", ""),
            task=d.get("task", ""), workflow_id=d.get("workflow_id", ""),
            input_data=d.get("input_data") or {},
            expected_keywords=d.get("expected_keywords") or [],
            expected_success=d.get("expected_success", True),
            expected_min_steps=d.get("expected_min_steps", 0) or 0,
            expected_max_duration=d.get("expected_max_duration", 0.0) or 0.0,
            expected_max_cost_usd=d.get("expected_max_cost_usd", 0.0) or 0.0,
            tags=d.get("tags") or [],
        )


@dataclass
class CaseResult:
    """单用例执行结果（含 6 类 check）。"""
    case_id: str = ""
    name: str = ""
    ok: bool = False
    success: bool = False
    output: str = ""
    duration: float = 0.0
    ok_steps: int = 0
    failed_steps: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id, "name": self.name, "ok": self.ok,
            "success": self.success, "output": self.output,
            "duration": self.duration, "ok_steps": self.ok_steps,
            "failed_steps": self.failed_steps,
            "total_tokens": self.total_tokens, "cost_usd": self.cost_usd,
            "checks": self.checks,
        }


@dataclass
class EvalRun:
    """一次数据集运行的完整报告。"""
    id: str = ""
    dataset_name: str = ""
    started_at: str = ""
    ended_at: str = ""
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    pass_rate: float = 0.0
    avg_duration: float = 0.0
    avg_cost_usd: float = 0.0
    total_tokens: int = 0
    results: List[CaseResult] = field(default_factory=list)
    baseline_diff: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "run_id": self.id, "dataset_name": self.dataset_name,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "total_cases": self.total_cases, "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases, "pass_rate": self.pass_rate,
            "avg_duration": self.avg_duration, "avg_cost_usd": self.avg_cost_usd,
            "total_tokens": self.total_tokens,
            "results": [r.to_dict() for r in self.results],
            "baseline_diff": self.baseline_diff, "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvalRun":
        return cls(
            id=d.get("id", ""), dataset_name=d.get("dataset_name", ""),
            started_at=d.get("started_at", ""), ended_at=d.get("ended_at", ""),
            total_cases=d.get("total_cases", 0), passed_cases=d.get("passed_cases", 0),
            failed_cases=d.get("failed_cases", 0), pass_rate=d.get("pass_rate", 0.0),
            avg_duration=d.get("avg_duration", 0.0), avg_cost_usd=d.get("avg_cost_usd", 0.0),
            total_tokens=d.get("total_tokens", 0),
            results=[CaseResult(**r) if isinstance(r, dict) else r
                     for r in d.get("results", [])],
            baseline_diff=d.get("baseline_diff") or {},
            error=d.get("error", ""),
        )


_eval_singleton: Optional["EvalHarness"] = None


def get_eval_harness() -> "EvalHarness":
    """全局单例（与其他内核单例一致）。"""
    global _eval_singleton
    if _eval_singleton is None:
        _eval_singleton = EvalHarness()
    return _eval_singleton


# ── 文本提取（供 _run_case 判定关键词/非空）──

def _extract_text(self, obj: Any) -> str:
    """从多种输出形态提取纯文本（best-effort）。"""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        return "\n".join(self._extract_text(x) for x in obj)
    if isinstance(obj, dict):
        parts: List[str] = []
        for k in ("content", "output", "result", "text", "response", "answer"):
            v = obj.get(k)
            if isinstance(v, str) and v:
                parts.append(v)
            elif isinstance(v, dict):
                for sub_k in ("content", "output", "text"):
                    sv = v.get(sub_k)
                    if isinstance(sv, str) and sv:
                        parts.append(sv)
        if not parts:
            try:
                s = json.dumps(obj, ensure_ascii=False)
                return s if len(s) <= 2000 else s[:2000] + "..."
            except Exception:
                return str(obj)
        return "\n".join(parts)
    return str(obj)


# 把实例方法挂到类上（保持 EvalHarness 定义紧凑，避免大段缩进）
EvalHarness._extract_text = _extract_text  # type: ignore[attr-defined]


# ── 数据集 CRUD ──

def _create_dataset(self, name: str, cases: List[EvalCase]) -> str:
    path = os.path.join(_datasets_dir(), f"{name}.json")
    payload = {"name": name, "cases": [c.to_dict() for c in cases]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _list_datasets(self) -> List[Dict[str, Any]]:
    d = _datasets_dir()
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
            out.append({
                "name": data.get("name", fn[:-5]),
                "cases": len(data.get("cases", [])),
                "path": os.path.join(d, fn),
            })
        except Exception:
            continue
    return out


def _get_dataset(self, name: str) -> Optional[List[EvalCase]]:
    path = os.path.join(_datasets_dir(), f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [EvalCase.from_dict(c) for c in data.get("cases", [])]
    except Exception:
        return None


def _delete_dataset(self, name: str) -> bool:
    path = os.path.join(_datasets_dir(), f"{name}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception:
            return False
    return False


EvalHarness.create_dataset = _create_dataset  # type: ignore[attr-defined]
EvalHarness.list_datasets = _list_datasets  # type: ignore[attr-defined]
EvalHarness.get_dataset = _get_dataset  # type: ignore[attr-defined]
EvalHarness.delete_dataset = _delete_dataset  # type: ignore[attr-defined]
# 私有名也绑：_run_dataset 内部经 self._get_dataset 调用
EvalHarness._get_dataset = _get_dataset  # type: ignore[attr-defined]


# ── 执行：任务 / 工作流 ──

def _exec_task(self, case: EvalCase, prefix: str):
    """通过 FabricHub 执行一个任务用例。best-effort：hub 不可用不阻塞。"""
    started = time.time()
    try:
        from core.fabric.hub import FabricHub
        from core.fabric.capability import Capability
        hub = FabricHub.get_instance()
        cap = getattr(Capability, "INFERENCE", None) or "inference.llm"
        res = hub.route(cap, {"prompt": case.task, "task": case.task})
        duration = time.time() - started
        ok = getattr(res, "ok", False)
        data = getattr(res, "data", {}) or {}
        data = data if isinstance(data, dict) else {"result": data}
        usage = data.get("usage") or {}
        tok = int(usage.get("total_tokens", 0) or 0)
        cost = float(usage.get("cost_usd", 0.0) or 0.0)
        return (data, {
            "success": bool(ok), "duration": duration,
            "ok_steps": 1 if ok else 0, "failed_steps": 0 if ok else 1,
            "total_tokens": tok, "cost_usd": cost,
        })
    except Exception as e:
        duration = time.time() - started
        return ({}, {
            "success": False, "duration": duration, "ok_steps": 0,
            "failed_steps": 1, "total_tokens": 0, "cost_usd": 0.0,
            "error": str(e),
        })


def _exec_workflow(self, case: EvalCase, prefix: str):
    """通过 WorkflowRunner 执行一个工作流用例。best-effort。"""
    started = time.time()
    runner = _default_runner()
    if runner is None:
        return ({}, {
            "success": False, "duration": 0.0, "ok_steps": 0,
            "failed_steps": 1, "total_tokens": 0, "cost_usd": 0.0,
            "error": "WorkflowRunner 不可用",
        })
    try:
        wf = runner.run(case.workflow_id, input_data=case.input_data or {})
        status = getattr(wf, "status", None)
        ok = status in ("success", "partial")
        steps = getattr(wf, "steps", None) or []
        ok_steps = sum(1 for s in steps if getattr(s, "ok", True))
        duration = time.time() - started
        return ({"status": status}, {
            "success": ok, "duration": duration,
            "ok_steps": ok_steps, "failed_steps": len(steps) - ok_steps,
            "total_tokens": 0, "cost_usd": 0.0,
        })
    except Exception as e:
        duration = time.time() - started
        return ({}, {
            "success": False, "duration": duration, "ok_steps": 0,
            "failed_steps": 1, "total_tokens": 0, "cost_usd": 0.0,
            "error": str(e),
        })


EvalHarness._exec_task = _exec_task  # type: ignore[attr-defined]
EvalHarness._exec_workflow = _exec_workflow  # type: ignore[attr-defined]


# ── 单用例评分（6 类 check）──

def _run_case(self, case: EvalCase, prefix: str) -> CaseResult:
    data, info = self._exec_task(case, prefix)
    success = bool(info.get("success"))
    output_text = self._extract_text(data)
    duration = float(info.get("duration", 0.0) or 0.0)
    ok_steps = int(info.get("ok_steps", 0) or 0)
    cost = float(info.get("cost_usd", 0.0) or 0.0)

    checks: List[Dict[str, Any]] = []

    # 1. expected_success
    exp_ok = (success == case.expected_success)
    checks.append({
        "name": "expected_success", "passed": exp_ok,
        "detail": f"success={success}, expected={case.expected_success}",
    })

    # 2. expected_keywords
    out_lower = output_text.lower()
    missing = [k for k in case.expected_keywords if k and k.lower() not in out_lower]
    checks.append({
        "name": "expected_keywords", "passed": len(missing) == 0,
        "detail": ("全部命中" if not missing else f"缺失关键词: {missing}"),
    })

    # 3. min_success_steps
    step_ok = True
    step_detail = "未设置最低步数"
    if case.expected_min_steps > 0:
        step_ok = ok_steps >= case.expected_min_steps
        step_detail = f"ok_steps={ok_steps}, expected>={case.expected_min_steps}"
    checks.append({"name": "min_success_steps", "passed": step_ok, "detail": step_detail})

    # 4. max_duration
    dur_ok = True
    dur_detail = "未设置最大耗时"
    if case.expected_max_duration > 0:
        dur_ok = duration <= case.expected_max_duration
        dur_detail = f"duration={duration:.3f}s, max={case.expected_max_duration}s"
    checks.append({"name": "max_duration", "passed": dur_ok, "detail": dur_detail})

    # 5. max_cost
    cost_ok = True
    cost_detail = "未设置最大成本"
    if case.expected_max_cost_usd > 0:
        cost_ok = cost <= case.expected_max_cost_usd
        cost_detail = f"cost=${cost:.6f}, max=${case.expected_max_cost_usd}"
    checks.append({"name": "max_cost", "passed": cost_ok, "detail": cost_detail})

    # 6. output_not_empty
    nonempty = len(output_text.strip()) > 0
    checks.append({
        "name": "output_not_empty", "passed": nonempty,
        "detail": f"输出长度={len(output_text)}",
    })

    ok = all(c["passed"] for c in checks)
    return CaseResult(
        case_id=case.id, name=case.name, ok=ok, success=success,
        output=output_text, duration=duration, ok_steps=ok_steps,
        failed_steps=int(info.get("failed_steps", 0) or 0),
        total_tokens=int(info.get("total_tokens", 0) or 0),
        cost_usd=cost, checks=checks,
    )


EvalHarness._run_case = _run_case  # type: ignore[attr-defined]


# ── 基线管理 + 退化检测 ──

def _set_baseline(self, name: str, run: EvalRun) -> str:
    path = os.path.join(_baselines_dir(), f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def _get_baseline(self, name: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_baselines_dir(), f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _delete_baseline(self, name: str) -> bool:
    path = os.path.join(_baselines_dir(), f"{name}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception:
            return False
    return False


def _compare_baseline(self, name: str, run: EvalRun) -> Dict[str, Any]:
    bl = self._get_baseline(name)
    if bl is None:
        return {"has_baseline": False, "regressions": [], "improvements": []}
    regressions: List[str] = []
    improvements: List[str] = []

    bp = float(bl.get("pass_rate", 0.0) or 0.0)
    if run.pass_rate < bp - 1e-6:
        regressions.append(f"pass_rate 退化: {bp:.3f}→{run.pass_rate:.3f}")
    elif run.pass_rate > bp + 1e-6:
        improvements.append(f"pass_rate 改善: {bp:.3f}→{run.pass_rate:.3f}")

    bd = float(bl.get("avg_duration", 0.0) or 0.0)
    if bd > 0 and run.avg_duration > bd * 1.5:
        regressions.append(f"avg_duration 退化: {bd:.3f}→{run.avg_duration:.3f}")
    elif bd > 0 and run.avg_duration < bd * 0.67:
        improvements.append(f"avg_duration 改善: {bd:.3f}→{run.avg_duration:.3f}")

    bc = float(bl.get("avg_cost_usd", 0.0) or 0.0)
    if bc > 0 and run.avg_cost_usd > bc * 1.5:
        regressions.append(f"avg_cost 退化: {bc:.6f}→{run.avg_cost_usd:.6f}")
    elif bc > 0 and run.avg_cost_usd < bc * 0.67:
        improvements.append(f"avg_cost 改善: {bc:.6f}→{run.avg_cost_usd:.6f}")

    return {"has_baseline": True, "regressions": regressions,
            "improvements": improvements}


EvalHarness.set_baseline = _set_baseline  # type: ignore[attr-defined]
EvalHarness.get_baseline = _get_baseline  # type: ignore[attr-defined]
EvalHarness.delete_baseline = _delete_baseline  # type: ignore[attr-defined]
EvalHarness._compare_baseline = _compare_baseline  # type: ignore[attr-defined]
# 私有名也绑：_compare_baseline 内部经 self._get_baseline 调用；
# 一并补 _set_baseline/_delete_baseline 私有名，防内部 self._xxx 调用漏绑
EvalHarness._get_baseline = _get_baseline  # type: ignore[attr-defined]
EvalHarness._set_baseline = _set_baseline  # type: ignore[attr-defined]
EvalHarness._delete_baseline = _delete_baseline  # type: ignore[attr-defined]


# ── 运行报告持久化 ──

def _save_run(self, run: EvalRun) -> str:
    path = os.path.join(_runs_dir(), f"{run.id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def _list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
    d = _runs_dir()
    if not os.path.isdir(d):
        return []
    files = sorted(os.listdir(d), reverse=True)
    out: List[Dict[str, Any]] = []
    for fn in files[:limit]:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out


def _get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_runs_dir(), f"{run_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


EvalHarness._save_run = _save_run  # type: ignore[attr-defined]
EvalHarness.list_runs = _list_runs  # type: ignore[attr-defined]
EvalHarness.get_run = _get_run  # type: ignore[attr-defined]


# ── 端到端跑数据集 ──

def _run_dataset(self, name: str, context_session_prefix: str = "") -> EvalRun:
    cases = self._get_dataset(name)
    if cases is None:
        return EvalRun(id="error", dataset_name=name,
                       error=f"数据集不存在: {name}")
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    results: List[CaseResult] = []
    for case in cases:
        cr = self._run_case(case, context_session_prefix)
        results.append(cr)
        # 可选：把每次用例灌入 ContextManager（启用 Context Engineering）
        if context_session_prefix:
            try:
                from kernel.context.context_manager import get_session
                sid = f"{context_session_prefix}_{case.id}"
                cm = get_session(sid, max_tokens=20000)
                cm.add_step({
                    "step_index": 0, "step_name": "eval_run",
                    "capability": "eval.case", "ok": cr.ok, "error": "",
                    "output": {"content": cr.output},
                })
            except Exception:
                pass
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    durations = [r.duration for r in results if r.duration > 0]
    avg_dur = sum(durations) / len(durations) if durations else 0.0
    avg_cost = sum(r.cost_usd for r in results) / total if total else 0.0
    total_tok = sum(r.total_tokens for r in results)
    run = EvalRun(
        id=f"run_{int(time.time()*1000)}",
        dataset_name=name, started_at=started,
        ended_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_cases=total, passed_cases=passed, failed_cases=failed,
        pass_rate=(passed / total) if total else 0.0,
        avg_duration=avg_dur, avg_cost_usd=avg_cost, total_tokens=total_tok,
        results=results, baseline_diff={"has_baseline": False},
    )
    run.baseline_diff = self._compare_baseline(name, run)
    self._save_run(run)
    return run


EvalHarness.run_dataset = _run_dataset  # type: ignore[attr-defined]
