"""多模态（视觉理解）API —— 暴露 VLMAdapter 端点（/api/multimodal/*）。

诚实优先：无后端（未配 VLM_API_KEY 且 ollama 未起）时 health 返回 ready=False，
analyze 返回 ok=False + 真实错误，绝不伪造视觉结果。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI


def mount_vlm_api(app: FastAPI) -> None:
    router = APIRouter(tags=["multimodal"])

    @router.get("/api/multimodal/health")
    def health() -> Any:
        """VLM 后端健康度（含档位解析与可用后端列表）。"""
        from core.fabric.adapters.vlm_adapter import VLMAdapter
        return VLMAdapter().health_detail()

    @router.post("/api/multimodal/analyze")
    def analyze(payload: dict) -> Any:
        """图像理解：payload 含 image_path 或 image_base64 + prompt。

        成功返回 {ok:True, text, engine, tier, prompt}；
        无后端/读取失败返回 {ok:False, error}（诚实，不伪造）。
        """
        from core.fabric.adapter import InvokeRequest
        from core.fabric.adapters.vlm_adapter import VLMAdapter
        from core.fabric.capability import Capability
        res = VLMAdapter().invoke(
            InvokeRequest(capability=Capability.VISION_UNDERSTAND, payload=payload or {})
        )
        if not res.ok:
            return {"ok": False, "error": res.error}
        return {"ok": True, **(res.data or {})}

    app.include_router(router)
