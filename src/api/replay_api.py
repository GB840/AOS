"""Replay & Debug API —— 失败回放与单步调试的 HTTP 接口（Task 5）。

提供：
- GET  /api/replay/traces              —— 列出最近 trace（跨工作流）
- GET  /api/replay/traces/{trace_id}   —— 取 trace 详情
- POST /api/replay/{trace_id}/from/{step_index}  —— 从某步重放（支持 what-if）
- POST /api/replay/{trace_id}/step/{step_index}  —— 单步调试（只跑该步）
- POST /api/replay/compare             —— 对比两条 trace

设计原则：
- 非侵入：replay/debug/compare 都不修改原 trace、不写 Pulse、不触发 Evolve
- 诚实：trace 不存在 / step_index 越界 / FabricHub 不可用都如实返回 error
- what-if：override_engine / override_payload 支持假设分析
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/replay", tags=["replay"])


# ── Pydantic 模型 ──

class ReplayFromRequest(BaseModel):
    """从某步重放——请求体。"""
    input_data: Dict[str, Any] = Field(
        default_factory=dict, description="覆盖初始输入（空则沿用原 trace 的 input）"
    )
    override_engine: str = Field("", description="what-if——对该步换成此引擎（如 ollama）")
    override_payload: Dict[str, Any] = Field(
        default_factory=dict, description="what-if——对该步注入额外 payload 字段"
    )


class DebugStepRequest(BaseModel):
    """单步调试——请求体。"""
    override_engine: str = Field("", description="换引擎跑该步")
    override_payload: Dict[str, Any] = Field(
        default_factory=dict, description="注入额外 payload 字段"
    )


class CompareRequest(BaseModel):
    """对比两条 trace——请求体。"""
    trace_id_a: str = Field(..., description="trace A 的 run_id")
    trace_id_b: str = Field(..., description="trace B 的 run_id")


# ── 工具函数 ──

def _get_runner():
    """懒加载 WorkflowRunner 单例（避免循环 import）。"""
    try:
        from kernel.studio.workflow_runner import WorkflowRunner
        from kernel.studio.workflow_store import get_workflow_store
        return WorkflowRunner(store=get_workflow_store())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"WorkflowRunner 不可用: {e}")


# ═══════════════════════════════════════════
#  Trace 列表 / 详情
# ═══════════════════════════════════════════

@router.get("/traces")
async def list_traces(
    wf_id: str = Query("", description="仅列出该工作流的 trace（空=全部）"),
    status: str = Query("", description="按状态过滤：success/failed/partial/running/awaiting_approval"),
    limit: int = Query(50, ge=1, le=500),
):
    """列出最近 trace（跨工作流）。

    返回摘要列表（不含 steps 详细内容），按 started_at 倒序。
    """
    runner = _get_runner()
    try:
        items = await asyncio.to_thread(runner.list_traces, wf_id=wf_id, limit=limit, status=status)
        return {"status": "ok", "total": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """取 trace 详情（含每步的完整输出）。"""
    runner = _get_runner()
    try:
        trace = await asyncio.to_thread(runner.get_trace, trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail=f"trace 不存在: {trace_id}")
        return {"status": "ok", "trace": trace}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  回放 / 单步调试
# ═══════════════════════════════════════════

@router.post("/{trace_id}/from/{step_index}")
async def replay_from_step(trace_id: str, step_index: int, body: Optional[ReplayFromRequest] = None):
    """从 step_index 重放该步及之后所有步（支持 what-if）。

    - 不修改原 trace
    - 不写 Pulse / 不触发 Evolve
    - override_engine / override_payload 仅对该步生效
    """
    runner = _get_runner()
    try:
        kwargs: Dict[str, Any] = {}
        if body is not None:
            if body.input_data:
                kwargs["input_data"] = body.input_data
            if body.override_engine:
                kwargs["override_engine"] = body.override_engine
            if body.override_payload:
                kwargs["override_payload"] = body.override_payload
        result = await asyncio.to_thread(
            lambda: runner.replay_from_step(trace_id, step_index, **kwargs)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "重放失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trace_id}/step/{step_index}")
async def debug_step(trace_id: str, step_index: int, body: Optional[DebugStepRequest] = None):
    """单步调试：只重放 step_index 这一步，不往后链式执行。

    适合快速验证「换引擎/换 payload 后这一步能否成功」。
    """
    runner = _get_runner()
    try:
        kwargs: Dict[str, Any] = {}
        if body is not None:
            if body.override_engine:
                kwargs["override_engine"] = body.override_engine
            if body.override_payload:
                kwargs["override_payload"] = body.override_payload
        result = await asyncio.to_thread(
            lambda: runner.debug_step(trace_id, step_index, **kwargs)
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "调试失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  Trace 对比
# ═══════════════════════════════════════════

@router.post("/compare")
async def compare_traces(body: CompareRequest):
    """对比两条 trace 的差异（静态对比，不重跑）。

    返回每步的 ok / engine / duration 差异。
    """
    runner = _get_runner()
    try:
        result = await asyncio.to_thread(
            runner.compare_traces, body.trace_id_a, body.trace_id_b
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "对比失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  挂载
# ═══════════════════════════════════════════

def mount_replay_api(app: FastAPI) -> None:
    """挂载 Replay & Debug API 到 FastAPI app。"""
    app.include_router(router)
    logger.info("Replay & Debug API 已挂载: /api/replay")
