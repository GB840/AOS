"""Human-in-the-Loop 审批 API（Task 4）。

提供：
- /api/approvals            —— 列出/创建审批
- /api/approvals/{id}       —— 获取详情
- /api/approvals/{id}/approve   —— 批准
- /api/approvals/{id}/reject    —— 拒绝
- /api/approvals/{id} DELETE    —— 删除
- /api/approvals/stats          —— 统计
- /api/approvals/runs/{run_id}/resume —— 工作流暂停后恢复执行

设计原则：
- 单一真相：所有审批（Evolve 提案 / WorkflowRunner 步骤 / Autopilot 操作）统一走此 API
- 非侵入：不修改被审批系统的运行时状态，仅记录决策
- 可审计：所有决策持久化到 JSONL，可追溯
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ── Pydantic 模型 ──

class CreateApprovalRequest(BaseModel):
    source: str = Field(..., description="发起方：evolve/workflow_runner/autopilot/autoskill")
    title: str = Field(...)
    description: str = ""
    risk_level: str = Field("medium", description="low/medium/high")
    payload: Dict[str, Any] = Field(default_factory=dict)
    workflow_id: str = ""
    run_id: str = ""
    proposal_id: str = ""
    ttl_seconds: int = Field(0, description="过期时间（秒），0=永不过期")


class DecideRequest(BaseModel):
    decided_by: str = "anonymous"
    note: str = ""


# ── 工具函数 ──

def _store():
    try:
        from kernel.approval import get_approval_store
        return get_approval_store()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"ApprovalStore 不可用: {e}")


# ═══════════════════════════════════════════
#  CRUD
# ═══════════════════════════════════════════

@router.get("")
async def list_approvals(
    status: str = Query("", description="pending/approved/rejected"),
    source: str = "",
    risk_level: str = "",
    limit: int = Query(100, ge=1, le=500),
):
    """列出审批请求。不带参数时返回所有 pending。"""
    s = _store()
    try:
        if status == "pending" or status == "":
            items = await asyncio.to_thread(
                s.list_pending, source=source, risk_level=risk_level, limit=limit
            )
        else:
            items = await asyncio.to_thread(
                s.list_all, status=status, source=source, limit=limit
            )
        return {"status": "ok", "total": len(items),
                "items": [a.to_dict() for a in items]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_approval(body: CreateApprovalRequest):
    """创建审批请求。"""
    s = _store()
    try:
        ap = await asyncio.to_thread(
            s.create_approval,
            source=body.source,
            title=body.title,
            description=body.description,
            risk_level=body.risk_level,
            payload=body.payload,
            workflow_id=body.workflow_id,
            run_id=body.run_id,
            proposal_id=body.proposal_id,
            ttl_seconds=body.ttl_seconds,
        )
        return {"status": "ok", "approval": ap.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def stats():
    """返回各状态计数。"""
    s = _store()
    return {"status": "ok", "stats": await asyncio.to_thread(s.stats)}


@router.get("/{approval_id}")
async def get_approval(approval_id: str):
    """获取审批详情。"""
    s = _store()
    ap = await asyncio.to_thread(s.get, approval_id)
    if ap is None:
        raise HTTPException(status_code=404, detail="审批不存在")
    return {"status": "ok", "approval": ap.to_dict()}


@router.post("/{approval_id}/approve")
async def approve(approval_id: str, body: DecideRequest):
    """批准审批。"""
    s = _store()
    result = await asyncio.to_thread(
        s.approve, approval_id, decided_by=body.decided_by, note=body.note
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "审批失败"))
    return {"status": "ok", "approval": result["approval"]}


@router.post("/{approval_id}/reject")
async def reject(approval_id: str, body: DecideRequest):
    """拒绝审批。"""
    s = _store()
    result = await asyncio.to_thread(
        s.reject, approval_id, decided_by=body.decided_by, note=body.note
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error", "拒绝失败"))
    return {"status": "ok", "approval": result["approval"]}


@router.delete("/{approval_id}")
async def delete_approval(approval_id: str):
    """删除审批（管理员）。"""
    s = _store()
    ok = await asyncio.to_thread(s.delete, approval_id)
    return {"status": "ok" if ok else "not_found", "id": approval_id}


# ═══════════════════════════════════════════
#  工作流恢复
# ═══════════════════════════════════════════

@router.post("/runs/{run_id}/resume")
async def resume_workflow(run_id: str, approval_id: str = ""):
    """恢复暂停的工作流运行。

    若关联的审批已通过，则从暂停处继续执行。
    """
    try:
        from kernel.studio.workflow_runner import get_workflow_runner
        runner = get_workflow_runner()
        run = await asyncio.to_thread(runner.resume, run_id, approval_id=approval_id)
        return {
            "status": "ok",
            "run_id": run.id,
            "run_status": run.status,
            "duration": run.duration,
            "steps_count": len(run.steps or []),
            "output": run.output,
            "error": run.error,
            "paused_at_step": run.paused_at_step,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  模块挂载
# ═══════════════════════════════════════════

def mount_approval_api(app) -> None:
    """把审批 API 挂载到 FastAPI app。"""
    app.include_router(router)
