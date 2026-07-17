"""视频生成适配器 —— AOS fabric 的 MEDIA_VIDEO 平面（本地零成本视频生成）。

基于 kernel.video_maker 封装：脚本分镜 → edge-tts 配音（逐词字幕）→ 
PIL 文字幻灯片/用户图片 → ffmpeg 烧字幕 + 拼接 → 输出 mp4。

设计原则（对齐 AOS 核心理念）：
- 本地优先：ffmpeg + edge-tts + Pillow，零付费 API
- 诚实：生成后用 ffprobe 校验是合法 mp4，失败如实报错
- 优雅降级：缺任一依赖则 health() 返回 False，不谎报 live
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)

_VIDEO_DIR = os.environ.get(
    "AOS_VIDEO_OUTPUT_DIR",
    os.path.join("data", "workspaces", "fabric", "videos"),
)


def _video_dir() -> str:
    os.makedirs(_VIDEO_DIR, exist_ok=True)
    return _VIDEO_DIR


def _check_deps() -> Dict[str, bool]:
    from kernel.video_maker import check_deps
    return check_deps()


class VideoMakerAdapter(BaseAgentAdapter):
    """本地视频生成适配器（MEDIA_VIDEO）。

    支持两种输入：
    1. script: 分镜列表 [{"text": "...", "image": "可选图片路径"}]
    2. text: 纯文本，自动按段落拆成单分镜
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        deps = _check_deps()
        self._ready = all(deps.values())
        logger.info("VideoMakerAdapter: ready=%s deps=%s", self._ready, deps)

    @property
    def engine_id(self) -> str:
        return "video-maker"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.MEDIA_VIDEO]

    def health(self) -> bool:
        return self._ready

    def tier(self) -> str:
        return TIER_HIGH

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not self._ready:
            missing = [k for k, v in _check_deps().items() if not v]
            return InvokeResult(
                ok=False,
                error=f"视频生成依赖未就绪: {', '.join(missing)}",
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        script_raw = payload.get("script") or payload.get("scenes") or payload.get("shots")
        text = payload.get("text") or payload.get("content") or payload.get("prompt") or ""
        voice = payload.get("voice") or "zh-CN-XiaoxiaoNeural"
        size_str = payload.get("size") or "1280x720"
        output_name = payload.get("output_name") or ""

        try:
            w, h = (int(x) for x in size_str.lower().split("x"))
            size = (w, h)
        except Exception:
            size = (1280, 720)

        if script_raw and isinstance(script_raw, list):
            script = []
            for item in script_raw:
                if isinstance(item, str):
                    script.append({"text": item})
                elif isinstance(item, dict):
                    script.append({
                        "text": item.get("text", ""),
                        "image": item.get("image", ""),
                    })
        elif text:
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            if not paragraphs:
                paragraphs = [text]
            script = [{"text": p} for p in paragraphs]
        else:
            return InvokeResult(
                ok=False,
                error="缺少输入：需提供 script（分镜列表）或 text（纯文本）",
                engine_id=self.engine_id,
            )

        import uuid
        from kernel.video_maker import generate_video

        task_id = uuid.uuid4().hex[:8]
        if output_name:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in output_name)
            output_path = os.path.join(_video_dir(), f"{safe_name}_{task_id}.mp4")
        else:
            output_path = os.path.join(_video_dir(), f"video_{task_id}.mp4")

        with self._lock:
            result = generate_video(
                script,
                output_path,
                voice=voice,
                size=size,
            )

        if result.get("ok"):
            return InvokeResult(
                ok=True,
                data={
                    "output": result.get("output", ""),
                    "duration": result.get("duration", 0),
                    "segments": result.get("segments", 0),
                    "meta": result.get("meta", []),
                    "engine": self.engine_id,
                },
                engine_id=self.engine_id,
            )
        else:
            return InvokeResult(
                ok=False,
                error=result.get("error", "生成失败"),
                engine_id=self.engine_id,
            )
