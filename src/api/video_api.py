"""Remotion 视频渲染对外 API（video.remotion 能力）。

端点：
- GET  /api/video/remotion/health   探测 Remotion CLI 可用性
- POST /api/video/remotion/render   渲染一个 composition（project_dir + composition_id + props）

诚实降级（理念6）：Remotion 未安装时 health=False、render 返回 ok=False 并说明原因，
绝不谎报渲染成功。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/remotion", tags=["video-remotion"])


class RenderRequest(BaseModel):
    project_dir: str = Field(..., description="Remotion 项目根目录")
    composition_id: str = Field(..., description="要渲染的 composition 名称")
    props: Dict[str, Any] = Field(default_factory=dict, description="传给 composition 的 props")
    entry_point: Optional[str] = Field(None, description="entry 文件（默认 <project_dir>/src/index.tsx）")
    output: Optional[str] = Field(None, description="输出 mp4 路径（默认 data/workspaces/remotion/）")
    concurrency: int = Field(4, description="并发帧数")
    timeout: int = Field(600, description="渲染超时（秒）")


def _get_adapter():
    from core.fabric.adapters.remotion_adapter import RemotionAdapter
    return RemotionAdapter()


@router.get("/health")
async def health():
    try:
        return {"status": "ok", **_get_adapter().health_detail()}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}


@router.post("/render")
async def render(body: RenderRequest):
    try:
        from core.fabric.adapter import InvokeRequest, Capability
        adapter = _get_adapter()
        res = adapter.invoke(InvokeRequest(
            capability=Capability.MEDIA_VIDEO,
            payload=body.model_dump(),
        ))
        if not res.ok:
            raise HTTPException(status_code=422, detail=res.error)
        return {"status": "ok", **res.data}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


def mount_video_api(app) -> None:
    app.include_router(router)
