"""Context Engineering API —— 运行时上下文管理的 HTTP 接口。

Task 2: Context Engineering
- 列出/获取/删除会话上下文
- 查看会话统计（token 占用、优先级分布、压缩条数）
- 触发手动压缩
- 获取当前上下文文本（可喂给 LLM）
- 跨会话持久化与加载（断点续跑）

数据落盘：data/workspaces/fabric/context/sessions/{session_id}.jsonl
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/context", tags=["context"])


# ── Pydantic 模型 ──

class CreateSessionRequest(BaseModel):
    session_id: str = Field("", description="会话 ID（空则服务端生成）")
    max_tokens: int = Field(8000, ge=500, le=200000, description="上下文 token 上限")
    preserve_recent: int = Field(3, ge=1, le=50, description="压缩时保留最近 N 步")


class AddMessageRequest(BaseModel):
    role: str = Field(..., description="消息角色（user/assistant/system）")
    content: str = Field(..., description="消息内容")
    priority: str = Field("normal", description="优先级: critical/high/normal/low")


class AddStepRequest(BaseModel):
    step_index: int = Field(0, ge=-1, le=10000)
    step_name: str = Field("")
    capability: str = Field("")
    ok: bool = Field(True)
    error: str = Field("")
    output: Dict[str, Any] = Field(default_factory=dict)


# ── 工具函数 ──

def _get_manager(session_id: str):
    """从全局会话注册表获取 ContextManager。不存在则 404。"""
    try:
        from kernel.context.context_manager import _sessions, _sessions_lock
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"ContextManager 模块不可用: {e}")
    with _sessions_lock:
        manager = _sessions.get(session_id)
    if manager is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return manager


# ═══════════════════════════════════════════
#  会话管理
# ═══════════════════════════════════════════

@router.get("/sessions")
async def list_sessions():
    """列出所有活跃会话（含统计信息）。"""
    try:
        from kernel.context.context_manager import list_sessions as _list
        return {"status": "ok", "sessions": _list()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions")
async def create_session(body: CreateSessionRequest):
    """显式创建一个新会话（或重置已有会话）。"""
    try:
        from kernel.context.context_manager import get_session
        # 不重置已有；用 get_session 复用或创建
        manager = get_session(body.session_id or "", max_tokens=body.max_tokens)
        manager.preserve_recent = body.preserve_recent
        return {
            "status": "ok",
            "session_id": manager.session_id,
            "max_tokens": manager.max_tokens,
            "preserve_recent": manager.preserve_recent,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定会话的统计信息。"""
    manager = _get_manager(session_id)
    return {"status": "ok", "stats": manager.stats()}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除一个会话（内存 + 磁盘持久化文件）。"""
    try:
        from kernel.context.context_manager import delete_session as _delete
        ok = _delete(session_id)
        return {"status": "ok" if ok else "not_found", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/persist")
async def persist_session(session_id: str):
    """把会话上下文持久化到 JSONL（断点续跑用）。"""
    manager = _get_manager(session_id)
    try:
        path = manager.persist()
        return {"status": "ok", "path": path, "entry_count": len(manager._entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/load")
async def load_session(session_id: str):
    """从磁盘 JSONL 加载会话上下文（断点续跑）。"""
    try:
        from kernel.context.context_manager import (
            ContextManager, _sessions, _sessions_lock,
        )
        loaded = ContextManager.load(session_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"磁盘上未找到会话: {session_id}")
        with _sessions_lock:
            _sessions[session_id] = loaded
        return {"status": "ok", "stats": loaded.stats()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  条目管理
# ═══════════════════════════════════════════

@router.get("/sessions/{session_id}/entries")
async def list_entries(
    session_id: str,
    priority: str = Query("", description="按优先级过滤: critical/high/normal/low"),
):
    """列出会话所有条目（可按优先级过滤）。"""
    manager = _get_manager(session_id)
    entries = manager.get_entries(priority=priority)
    return {"status": "ok", "entries": entries, "count": len(entries)}


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, body: AddMessageRequest):
    """添加一段对话消息到会话。"""
    manager = _get_manager(session_id)
    try:
        entry = manager.add_message(body.role, body.content, body.priority)
        return {"status": "ok", "entry_id": entry.id, "stats": manager.stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/steps")
async def add_step(session_id: str, body: AddStepRequest):
    """手动添加一个步骤结果到会话。"""
    manager = _get_manager(session_id)
    try:
        step_result = {
            "step_index": body.step_index,
            "step_name": body.step_name,
            "capability": body.capability,
            "ok": body.ok,
            "error": body.error,
            "output": body.output,
        }
        entry = manager.add_step(step_result)
        return {"status": "ok", "entry_id": entry.id, "stats": manager.stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/text")
async def get_context_text(
    session_id: str,
    max_entries: int = Query(0, ge=0, le=1000, description="最多返回多少条（0=全部）"),
):
    """获取当前上下文的文本表示（可直接喂给 LLM）。"""
    manager = _get_manager(session_id)
    try:
        text = manager.get_context_text(max_entries=max_entries)
        return {
            "status": "ok",
            "text": text,
            "length": len(text),
            "stats": manager.stats(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  压缩
# ═══════════════════════════════════════════

@router.post("/sessions/{session_id}/compact")
async def compact_session(session_id: str):
    """手动触发上下文压缩（即使未超阈值也强制压缩一次）。"""
    manager = _get_manager(session_id)
    try:
        # 临时把 max_tokens 设为 1 强制触发压缩
        original_max = manager.max_tokens
        manager.max_tokens = 1
        try:
            result = manager.compact_if_needed()
        finally:
            manager.max_tokens = original_max
        return {"status": "ok", "result": result, "stats": manager.stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """清空会话上下文（保留 session_id）。"""
    manager = _get_manager(session_id)
    try:
        manager.clear()
        return {"status": "ok", "stats": manager.stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  模块挂载
# ═══════════════════════════════════════════

def mount_context_api(app) -> None:
    """把 Context Engineering API 挂载到 FastAPI app。"""
    app.include_router(router)
