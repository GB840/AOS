"""步骤级审核控制面 API（三省六部制式「封驳」闭环）。

- GET  /api/review/pending         列出 orchestrator 来源的 pending 审批（按 run 分组）
- POST /api/review/resume/{run_id} 用持久化 spec 重新拉起流水线（准后继续执行）

准/驳本身走既有 /api/approvals（approval_api 已挂载）。resume 通过 FabricHub
单例重新路由 system.workflow，复用同一 route_fn，因此「准后执行」与首次运行
走完全相同的执行路径（理念5 能力即路由、权限即边界）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/pending")
async def pending_reviews():
    """列出 orchestrator 来源的待审核步骤，按 run 分组（供「审核」tab 渲染）。"""
    try:
        from kernel.approval.approval_store import get_approval_store
        store = get_approval_store()
        items = await asyncio.to_thread(store.list_pending, source="orchestrator")
        by_run: Dict[str, list] = {}
        for a in items:
            by_run.setdefault(a.run_id or "unknown", []).append(a.to_dict())
        return {"status": "ok", "total": len(items), "by_run": by_run}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/{run_id}")
async def resume_run(run_id: str):
    """用持久化 spec 重新拉起流水线（准后继续执行被封驳闸门挡住的后续步骤）。

    经 FabricHub 单例重新路由 system.workflow，复用与首次运行完全相同的
    执行路径；已批准的步骤放行执行、已驳回的封驳跳过、仍 pending 的继续等待。
    """
    try:
        from kernel.approval.review_gate import get_review_gate
        from mcp.protocol import _get_hub
        from core.fabric.capability import Capability

        gate = get_review_gate()
        spec = gate.get_spec(run_id)
        if not spec:
            raise HTTPException(
                status_code=404,
                detail=f"未找到 run_id={run_id} 的持久化规格（可能未开启审核模式或已清理）",
            )
        hub = _get_hub()
        res = await asyncio.to_thread(hub.route, Capability.WORKFLOW_EXECUTE.value, spec)
        return {
            "status": "ok",
            "success": getattr(res, "ok", False),
            "data": getattr(res, "data", None),
            "error": getattr(res, "error", None),
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


def mount_review_api(app) -> None:
    """把审核控制面 API 挂载到 FastAPI app。"""
    app.include_router(router)
