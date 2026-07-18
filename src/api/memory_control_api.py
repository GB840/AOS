"""可干预记忆控制面 API（任务②）。

暴露 MemoryControlStore 的 list/get/add/update/delete/rollback，让蒸馏后的记忆
从「只可观」变为「可干预」（补全理念8「白盒才可进化」的最后一公里）。

端点（前缀 /api/memory/control）：
- GET    /            list（scope / project_id 过滤）
- GET    /{id}        get 单条
- POST   /            add
- PATCH  /{id}        update（旧值进 edit_history）
- DELETE /{id}        delete（软删）
- POST   /{id}/rollback  rollback 到某版本

诚实：记忆不存在/已删/无该版本快照，如实返回 404，不编造。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from kernel.memory_control import MemoryControlStore

logger = logging.getLogger(__name__)

_store: Optional[MemoryControlStore] = None


def _get_store() -> MemoryControlStore:
    global _store
    if _store is None:
        _store = MemoryControlStore()
    return _store


class MemoryAddRequest(BaseModel):
    text: str
    category: str = "user_note"
    source: str = "manual"
    confidence: float = 0.5
    scope: str = "global"            # global | user | project
    project_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryUpdateRequest(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None
    project_id: Optional[str] = None


class MemoryRollbackRequest(BaseModel):
    version: int


def mount_memory_control_api(app: FastAPI) -> None:
    @app.get("/api/memory/control")
    async def list_memories(scope: str = "", project_id: str = ""):
        items = _get_store().list(
            scope=scope or None, project_id=project_id or None
        )
        return {"status": "ok", "total": len(items), "items": items}

    @app.get("/api/memory/control/{memory_id}")
    async def get_memory(memory_id: str):
        rec = _get_store().get(memory_id)
        if rec is None or rec.get("deleted"):
            raise HTTPException(status_code=404, detail=f"记忆不存在或已删除: {memory_id}")
        return {"status": "ok", "memory": rec}

    @app.post("/api/memory/control")
    async def add_memory(body: MemoryAddRequest):
        rec = _get_store().add(
            text=body.text, category=body.category, source=body.source,
            confidence=body.confidence, scope=body.scope,
            project_id=body.project_id, metadata=body.metadata,
        )
        return {"status": "ok", "memory": rec}

    @app.patch("/api/memory/control/{memory_id}")
    async def update_memory(memory_id: str, body: MemoryUpdateRequest):
        rec = _get_store().update(
            memory_id, text=body.text, category=body.category,
            confidence=body.confidence, metadata=body.metadata,
            scope=body.scope, project_id=body.project_id,
        )
        if rec is None:
            raise HTTPException(status_code=404, detail=f"记忆不存在或已删除: {memory_id}")
        return {"status": "ok", "memory": rec}

    @app.delete("/api/memory/control/{memory_id}")
    async def delete_memory(memory_id: str):
        ok = _get_store().delete(memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"记忆不存在或已删除: {memory_id}")
        return {"status": "ok", "deleted": True, "memory_id": memory_id}

    @app.post("/api/memory/control/{memory_id}/rollback")
    async def rollback_memory(memory_id: str, body: MemoryRollbackRequest):
        rec = _get_store().rollback(memory_id, body.version)
        if rec is None:
            raise HTTPException(
                status_code=404,
                detail=f"记忆不存在/已删除/无该版本快照: {memory_id}",
            )
        return {"status": "ok", "memory": rec}

    @app.get("/api/memory/lifecycle")
    async def lifecycle_report():
        """概念2 农耕层循环记忆量化报告（各 tier 计数/归档数）。"""
        from kernel.memory_distiller import get_distiller
        d = get_distiller()
        rep = d.lifecycle_report()
        if rep is None:
            return {"status": "disabled", "reason": "lifecycle 未启用（无 lifecycle_path）"}
        return {"status": "ok", "report": rep}

    @app.post("/api/memory/lifecycle/prune")
    async def lifecycle_prune():
        """概念2 触发一次周期 prune（TTL 过期 + 分层降级 + 归档软删）。"""
        from kernel.memory_distiller import get_distiller
        d = get_distiller()
        rep = d.lifecycle_prune()
        if rep is None:
            return {"status": "disabled", "reason": "lifecycle 未启用（无 lifecycle_path）"}
        return {"status": "ok", "prune": rep}
