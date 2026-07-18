"""Eval Framework API —— 评估框架的 HTTP 接口（Task 3: Eval Framework）。

提供：
- 数据集 CRUD：/api/eval/datasets
- 跑评估：POST /api/eval/datasets/{name}/run
- 基线管理：/api/eval/baselines
- 运行历史：/api/eval/runs

设计原则：
- 非侵入：跑评估不修改被测系统状态
- 诚实量化：每条 case 评分附带原始指标（duration/tokens/cost）
- 回归告警：与基线对比，pass_rate/duration/cost 退化即标记
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval", tags=["eval"])


# ── Pydantic 模型 ──

class EvalCaseModel(BaseModel):
    id: str = Field("", description="用例 ID（空则用 name")
    name: str = Field(..., description="用例名")
    task: str = Field("", description="任务描述（喂给 inference.llm）")
    workflow_id: str = Field("", description="工作流 ID（与 task 二选一）")
    input_data: Dict[str, Any] = Field(default_factory=dict)
    expected_keywords: List[str] = Field(default_factory=list)
    expected_success: bool = Field(True)
    expected_min_steps: int = Field(0, ge=0)
    expected_max_duration: float = Field(0.0, ge=0.0)
    expected_max_cost_usd: float = Field(0.0, ge=0.0)
    tags: List[str] = Field(default_factory=list)


class CreateDatasetRequest(BaseModel):
    name: str = Field(..., description="数据集名（同一名字将覆盖）")
    cases: List[EvalCaseModel] = Field(...)


class RunDatasetRequest(BaseModel):
    context_session_prefix: str = Field(
        "", description="非空时为每个用例生成上下文会话 ID（启用 Context Engineering）"
    )


# ── 工具函数 ──

def _get_harness():
    try:
        from kernel.eval.eval_harness import get_eval_harness
        return get_eval_harness()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"EvalHarness 不可用: {e}")


# ═══════════════════════════════════════════
#  数据集管理
# ═══════════════════════════════════════════

@router.get("/datasets")
async def list_datasets():
    """列出所有评估数据集。"""
    harness = _get_harness()
    try:
        return {"status": "ok", "datasets": harness.list_datasets()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets")
async def create_dataset(body: CreateDatasetRequest):
    """创建/覆盖一个数据集。"""
    harness = _get_harness()
    try:
        from kernel.eval.eval_harness import EvalCase
        cases = [
            EvalCase(
                id=c.id or c.name,
                name=c.name,
                task=c.task,
                workflow_id=c.workflow_id,
                input_data=c.input_data,
                expected_keywords=c.expected_keywords,
                expected_success=c.expected_success,
                expected_min_steps=c.expected_min_steps,
                expected_max_duration=c.expected_max_duration,
                expected_max_cost_usd=c.expected_max_cost_usd,
                tags=c.tags,
            )
            for c in body.cases
        ]
        path = harness.create_dataset(body.name, cases)
        return {"status": "ok", "name": body.name, "path": path, "case_count": len(cases)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{name}")
async def get_dataset(name: str):
    """读取数据集详情。"""
    harness = _get_harness()
    cases = harness.get_dataset(name)
    if cases is None:
        raise HTTPException(status_code=404, detail=f"数据集不存在: {name}")
    return {"status": "ok", "name": name, "cases": [c.to_dict() for c in cases]}


@router.delete("/datasets/{name}")
async def delete_dataset(name: str):
    """删除数据集。"""
    harness = _get_harness()
    ok = harness.delete_dataset(name)
    return {"status": "ok" if ok else "not_found", "name": name}


@router.post("/datasets/{name}/run")
async def run_dataset(name: str, body: RunDatasetRequest):
    """跑一个数据集的所有用例。返回运行报告（含基线对比）。"""
    harness = _get_harness()
    try:
        run = harness.run_dataset(name, context_session_prefix=body.context_session_prefix)
        return {"status": "ok", "run": run.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  基线管理
# ═══════════════════════════════════════════

@router.get("/baselines")
async def list_baselines():
    """列出所有数据集的基线。"""
    harness = _get_harness()
    try:
        from kernel.eval.eval_harness import _baselines_dir
        import os
        result = []
        d = _baselines_dir()
        if os.path.exists(d):
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".json"):
                    continue
                bl = harness.get_baseline(fn[:-5])
                if bl:
                    result.append(bl)
        return {"status": "ok", "baselines": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/baselines/{name}")
async def get_baseline(name: str):
    """获取指定数据集的基线。"""
    harness = _get_harness()
    bl = harness.get_baseline(name)
    if bl is None:
        raise HTTPException(status_code=404, detail=f"基线不存在: {name}")
    return {"status": "ok", "baseline": bl}


@router.delete("/baselines/{name}")
async def delete_baseline(name: str):
    """删除基线。"""
    harness = _get_harness()
    ok = harness.delete_baseline(name)
    return {"status": "ok" if ok else "not_found", "name": name}


@router.post("/baselines/{name}/set/{run_id}")
async def set_baseline(name: str, run_id: str):
    """把某次运行设为基线。"""
    harness = _get_harness()
    run_dict = harness.get_run(run_id)
    if run_dict is None:
        raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
    try:
        from kernel.eval.eval_harness import EvalRun
        # 把 dict 重建为 EvalRun（只取基线需要的字段）
        run = EvalRun(
            id=run_dict.get("id", run_id),
            dataset_name=run_dict.get("dataset_name", name),
            pass_rate=run_dict.get("pass_rate", 0.0),
            avg_duration=run_dict.get("avg_duration", 0.0),
            avg_cost_usd=run_dict.get("avg_cost_usd", 0.0),
            total_tokens=run_dict.get("total_tokens", 0),
            total_cases=run_dict.get("total_cases", 0),
            passed_cases=run_dict.get("passed_cases", 0),
        )
        path = harness.set_baseline(name, run)
        return {"status": "ok", "name": name, "run_id": run_id, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  运行历史
# ═══════════════════════════════════════════

@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=200)):
    """列出最近的评估运行。"""
    harness = _get_harness()
    try:
        return {"status": "ok", "runs": harness.list_runs(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """获取某次运行的完整报告。"""
    harness = _get_harness()
    run = harness.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}")
    return {"status": "ok", "run": run}


# ═══════════════════════════════════════════
#  模块挂载
# ═══════════════════════════════════════════

def mount_eval_api(app) -> None:
    """把 Eval Framework API 挂载到 FastAPI app。"""
    app.include_router(router)
