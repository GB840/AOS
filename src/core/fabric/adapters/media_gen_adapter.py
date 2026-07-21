"""MediaGenAdapter —— AOS fabric 的 MEDIA_IMAGE / MEDIA_VIDEO 平面（国产智谱后端）。

用智谱开放平台（bigmodel.cn）的 CogView-4（文生图）+ CogVideoX（文生视频）实现，
纯 stdlib urllib 调用，零第三方依赖。替代 Scroll-World 绑定的国外模型
（GPT Image 2 + Seedance via Higgsfield 国外平台），落实「用国产的做」。

设计原则（对齐项目铁律 + 现有适配器范式）：
- **零依赖**：仅用 urllib/json/os，不依赖 zhipuai SDK（避 Python 3.14 装包坑）。
- **缺 key 优雅降级**：ZHIPU_API_KEY 未配置时 health()=False，路由层忽略，不谎报 live。
- **诚实可观测**：invoke 失败如实返回 error（含 HTTP 状态码/响应体），不编造 URL；
  engine_id 由路由层回填。
- **文生图同步**：POST images/generations → data[].url；**文生视频异步**：
  POST videos/generations 拿 id → 轮询 async-result/{id}（PROCESSING→SUCCESS/FAIL）。
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

_ZHIPU_BASE = "https://open.bigmodel.cn/api/paas/v4"
_DEFAULT_IMAGE_MODEL = "cogview-4-250304"
_DEFAULT_VIDEO_MODEL = "cogvideox-3"


def _get_key() -> str | None:
    """读取智谱 API Key（兼容 ZHIPU_API_KEY / ZHIPUAI_API_KEY 两种命名）。"""
    return os.environ.get("ZHIPU_API_KEY") or os.environ.get("ZHIPUAI_API_KEY")


def _http_json(method: str, url: str, api_key: str,
               body: dict | None = None, timeout: int = 60) -> tuple[dict, int]:
    """最小 HTTP JSON 客户端（stdlib），返回 (parsed_json, status_code)。

    status=-1 表示网络/超时层错误（非 HTTP 状态码）。
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return ({"error": {"message": raw}}, e.code)
    except Exception as e:  # 网络不可达 / 超时
        return ({"error": {"message": str(e)}}, -1)
    try:
        return (json.loads(raw), status)
    except json.JSONDecodeError:
        return ({"error": {"message": raw}}, status)


class MediaGenAdapter(BaseAgentAdapter):
    """国产文生图/文生视频平面：智谱 CogView-4 + CogVideoX。"""

    def __init__(self) -> None:
        self._api_key = _get_key()
        self._available = bool(self._api_key)
        if self._available:
            logger.info("MediaGenAdapter: ready (ZHIPU_API_KEY configured)")
        else:
            logger.info("MediaGenAdapter: ZHIPU_API_KEY 未配置，将优雅降级")

    @property
    def engine_id(self) -> str:
        return "media-gen"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.MEDIA_IMAGE, Capability.MEDIA_VIDEO]

    def health(self) -> bool:
        # 真实探测：引擎 live 的前提是配置了智谱 API Key（不硬编码 True）
        return self._available

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        mode = (payload.get("mode") or "image").lower()
        if mode == "image":
            return self._gen_image(payload)
        if mode == "video":
            return self._gen_video(payload)
        return InvokeResult(ok=False, error=f"未知 mode: {mode!r}（支持 image / video）")

    # ---- 文生图（同步） ----
    def _gen_image(self, payload: dict) -> InvokeResult:
        if not self._available:
            return InvokeResult(ok=False, error="未配置 ZHIPU_API_KEY")
        prompt = payload.get("prompt") or payload.get("text") or ""
        if not prompt:
            return InvokeResult(ok=False, error="未提供 prompt（文生图需要文本描述）")
        model = payload.get("model") or _DEFAULT_IMAGE_MODEL
        size = payload.get("size") or "1024x1024"
        body = {"model": model, "prompt": prompt, "size": size}
        parsed, status = _http_json(
            "POST", f"{_ZHIPU_BASE}/images/generations", self._api_key, body, timeout=60
        )
        if status != 200:
            msg = parsed.get("error", {}).get("message", parsed)
            return InvokeResult(ok=False, error=f"文生图 HTTP {status}: {msg}")
        data = parsed.get("data") or []
        if not data:
            return InvokeResult(ok=False, error="文生图返回空 data")
        url = data[0].get("url")
        if not url:
            return InvokeResult(ok=False, error="文生图未返回 url")
        return InvokeResult(ok=True, data={
            "url": url, "model": model, "prompt": prompt, "size": size,
        })

    # ---- 文生视频（异步轮询） ----
    def _gen_video(self, payload: dict) -> InvokeResult:
        if not self._available:
            return InvokeResult(ok=False, error="未配置 ZHIPU_API_KEY")
        prompt = payload.get("prompt") or payload.get("text") or ""
        if not prompt:
            return InvokeResult(ok=False, error="未提供 prompt（文生视频需要文本描述）")
        model = payload.get("model") or _DEFAULT_VIDEO_MODEL
        size = payload.get("size") or "1280x720"
        quality = payload.get("quality") or "speed"
        duration = int(payload.get("duration") or 5)
        fps = int(payload.get("fps") or 30)
        with_audio = bool(payload.get("with_audio", False))
        body = {
            "model": model, "prompt": prompt, "quality": quality,
            "with_audio": with_audio, "size": size, "fps": fps, "duration": duration,
        }
        parsed, status = _http_json(
            "POST", f"{_ZHIPU_BASE}/videos/generations", self._api_key, body, timeout=60
        )
        if status != 200:
            msg = parsed.get("error", {}).get("message", parsed)
            return InvokeResult(ok=False, error=f"文生视频 HTTP {status}: {msg}")
        task_id = parsed.get("id")
        if not task_id:
            return InvokeResult(ok=False, error="文生视频未返回任务 id")

        timeout_s = int(payload.get("poll_timeout") or 180)
        interval = 5
        deadline = time.time() + timeout_s
        last = parsed
        while time.time() < deadline:
            time.sleep(interval)
            last, _ = _http_json(
                "GET", f"{_ZHIPU_BASE}/async-result/{task_id}", self._api_key, timeout=30
            )
            status_val = last.get("task_status")
            if status_val == "SUCCESS":
                results = last.get("video_result") or []
                if not results:
                    return InvokeResult(ok=False, error="视频生成成功但未返回 video_result")
                item = results[0]
                return InvokeResult(ok=True, data={
                    "url": item.get("url"),
                    "cover_image_url": item.get("cover_image_url"),
                    "model": model, "prompt": prompt, "size": size, "duration": duration,
                })
            if status_val == "FAIL":
                msg = last.get("error", {}).get("message", last)
                return InvokeResult(ok=False, error=f"视频生成失败: {msg}")
            # PROCESSING：继续轮询
        return InvokeResult(
            ok=False,
            error=f"视频生成轮询超时（{timeout_s}s 内未 SUCCESS），最后状态: {last.get('task_status')}",
        )
