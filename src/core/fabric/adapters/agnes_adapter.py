"""Real Agnes AI adapter for the AOS open fabric - the MULTIMODAL plane.

Agnes AI (apihub.agnes-ai.com) exposes an OpenAI-compatible surface:
  * POST {base}/chat/completions    -> agnes-2.0-flash       (text, 512K ctx)
  * POST {base}/images/generations  -> agnes-image-2.1-flash  (image, 文生图/图生图)
  * POST {base}/videos              -> agnes-video-v2.0       (video, 异步)
  * GET  {result_url}?video_id=...  -> 轮询视频结果

This adapter is THIN: it translates AOS capability calls into Agnes HTTP
calls. AOS never re-implements a model brain - it delegates to the real
provider, honouring the user's hard rule: real OSS / real APIs + AOS on top.

Config (from .env, injected by start_all.sh / fabric_scorecard.py):
  AGNES_API_KEY      (required)
  AGNES_BASE_URL     default https://apihub.agnes-ai.com/v1
  AGNES_VIDEO_RESULT_URL  default {host}/agnesapi  (root-relative per Agnes docs)
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability


AGNES_DEFAULTS: dict[str, str] = {
    "base_url": "https://apihub.agnes-ai.com/v1",
    "text_model": "agnes-2.0-flash",
    "image_model": "agnes-image-2.1-flash",
    "video_model": "agnes-video-v2.0",
}

# 视频轮询参数
_VIDEO_POLL_INTERVAL = 5.0      # 秒
_VIDEO_DEFAULT_TIMEOUT = 180.0  # 秒（生成时长当前 $0/秒，留足余量）


def _requests():
    """延迟导入，保证适配器在缺依赖时仍是合法代码。"""
    import requests  # type: ignore
    return requests


def _derive_result_url(base: str, explicit: Optional[str]) -> str:
    """视频结果端点：显式配置优先；否则由 Base URL 推导 host 根路径 + /agnesapi。"""
    if explicit:
        return explicit
    host = base.rstrip("/")
    if host.endswith("/v1"):
        host = host[: -len("/v1")]
    return host + "/agnesapi"


class AgnesAdapter(BaseAgentAdapter):
    """OpenAI-compatible 多模态适配器：文本 / 图像 / 视频。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        video_result_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("AGNES_API_KEY", "")
        self._base = (base_url or os.environ.get("AGNES_BASE_URL", AGNES_DEFAULTS["base_url"])).rstrip("/")
        self._result_url = _derive_result_url(self._base, video_result_url or os.environ.get("AGNES_VIDEO_RESULT_URL"))
        self._health_cache: Optional[tuple[bool, float]] = None

    # ---- 接口实现 ----
    @property
    def engine_id(self) -> str:
        return "agnes"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.LLM_GATEWAY, Capability.MEDIA_IMAGE, Capability.MEDIA_VIDEO]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        cap = req.capability.value if hasattr(req.capability, "value") else str(req.capability)
        if cap == Capability.LLM_GATEWAY.value:
            return self._chat(req)
        if cap == Capability.MEDIA_IMAGE.value:
            return self._image(req)
        if cap == Capability.MEDIA_VIDEO.value:
            return self._video(req)
        return InvokeResult(ok=False, error=f"agnes: unsupported capability {cap}")

    def health(self) -> bool:
        """诚实判活：必须配置 key，且 Base URL 可达（连接/超时失败才判 dead）。

        结果缓存 30s，避免每次构造枢纽都打网络（现有测试套件会多次建枢纽）。
        """
        if not self._api_key:
            return False
        now = time.time()
        if self._health_cache is not None and (now - self._health_cache[1]) < 30:
            return self._health_cache[0]
        ok = False
        try:
            r = _requests().get(self._base, timeout=4, headers=self._headers())
            ok = r.status_code < 500  # 2xx/3xx/4xx 都算"可达"
        except Exception as e:  # 连接失败 / 超时 / DNS
            logger.debug("agnes health probe failed: %s", e)
            ok = False
        self._health_cache = (ok, now)
        return ok

    def supported_protocols(self) -> list[str]:
        return ["OpenAI"]  # Agnes 是 OpenAI 兼容端点

    # ---- 便捷封装（直接调用也行） ----
    def chat(self, prompt: str, *, model: Optional[str] = None, **opts: Any) -> InvokeResult:
        return self._chat(InvokeRequest(
            capability=Capability.LLM_GATEWAY,
            payload={"prompt": prompt, "model": model or AGNES_DEFAULTS["text_model"], "opts": opts},
        ))

    def generate_image(self, prompt: str, *, model: Optional[str] = None, **opts: Any) -> InvokeResult:
        payload: dict[str, Any] = {"prompt": prompt, "model": model or AGNES_DEFAULTS["image_model"]}
        payload.update(opts)
        return self._image(InvokeRequest(capability=Capability.MEDIA_IMAGE, payload=payload))

    def generate_video(self, prompt: str, *, model: Optional[str] = None,
                       poll_timeout: float = _VIDEO_DEFAULT_TIMEOUT, **opts: Any) -> InvokeResult:
        payload: dict[str, Any] = {
            "prompt": prompt, "model": model or AGNES_DEFAULTS["video_model"],
            "poll_timeout": poll_timeout,
        }
        payload.update(opts)
        return self._video(InvokeRequest(capability=Capability.MEDIA_VIDEO, payload=payload))

    # ---- 内部：HTTP 封装 ----
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _chat(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        model = payload.get("model", AGNES_DEFAULTS["text_model"])
        if payload.get("messages"):
            messages = payload["messages"]
        else:
            prompt = payload.get("prompt") or payload.get("content") or payload.get("task") or ""
            messages = [{"role": "user", "content": prompt}]
        body: dict[str, Any] = {"model": model, "messages": messages}
        if payload.get("opts"):
            body.update(payload["opts"])
        try:
            r = _requests().post(
                f"{self._base}/chat/completions", headers=self._headers(), json=body, timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return InvokeResult(ok=True, data={"content": content, "model": model, "raw": data})
        except Exception as e:  # 缺 key / 网络 / 上游错误
            logger.warning("agnes chat failed: %s", e)
            return InvokeResult(ok=False, error=f"agnes chat failed: {e!r}")

    def _image(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        model = payload.get("model", AGNES_DEFAULTS["image_model"])
        prompt = payload.get("prompt") or payload.get("content") or ""
        body: dict[str, Any] = {"model": model, "prompt": prompt}
        for k in ("n", "size", "quality", "image", "images", "response_format"):
            if k in payload:
                body[k] = payload[k]
        try:
            r = _requests().post(
                f"{self._base}/images/generations", headers=self._headers(), json=body, timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("data", [])
            return InvokeResult(ok=True, data={"images": items, "model": model, "raw": data})
        except Exception as e:
            logger.warning("agnes image failed: %s", e)
            return InvokeResult(ok=False, error=f"agnes image failed: {e!r}")

    def _video(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        model = payload.get("model", AGNES_DEFAULTS["video_model"])
        prompt = payload.get("prompt") or payload.get("content") or ""
        body: dict[str, Any] = {"model": model, "prompt": prompt}
        for k in ("image", "images", "duration", "aspect_ratio", "resolution"):
            if k in payload:
                body[k] = payload[k]
        try:
            r = _requests().post(
                f"{self._base}/videos", headers=self._headers(), json=body, timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            video_id = self._extract_video_id(data)
            if not video_id:
                return InvokeResult(ok=False, error=f"agnes video: no video_id in response: {data!r}")
            url = self._poll_video(video_id, float(payload.get("poll_timeout", _VIDEO_DEFAULT_TIMEOUT)))
            if url is None:
                return InvokeResult(ok=False, error=f"agnes video: poll timeout for {video_id}")
            return InvokeResult(ok=True, data={"video_id": video_id, "url": url, "model": model})
        except Exception as e:
            logger.warning("agnes video failed: %s", e)
            return InvokeResult(ok=False, error=f"agnes video failed: {e!r}")

    @staticmethod
    def _extract_video_id(data: dict[str, Any]) -> str:
        """从创建任务响应里尽力抽取 video_id（Agnes 字段名未完全公开，做防御性解析）。"""
        for key in ("video_id", "id", "task_id"):
            v = data.get(key)
            if v:
                return str(v).strip()
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ("video_id", "id", "task_id"):
                v = nested.get(key)
                if v:
                    return str(v).strip()
        return ""

    def _poll_video(self, video_id: str, timeout: float) -> Optional[str]:
        """轮询视频结果端点，直到拿到 url 或超时 / 失败。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = _requests().get(
                    self._result_url, params={"video_id": video_id},
                    headers=self._headers(), timeout=30,
                )
                if r.status_code == 200:
                    data = r.json()
                    url = self._extract_video_url(data)
                    if url:
                        return url
                    status = self._extract_status(data)
                    if status in ("failed", "error", "expired"):
                        logger.warning("agnes video %s terminal status=%s", video_id, status)
                        return None
            except Exception as e:
                logger.debug("agnes video poll %s error: %s", video_id, e)
            time.sleep(_VIDEO_POLL_INTERVAL)
        return None

    @staticmethod
    def _extract_video_url(data: dict[str, Any]) -> Optional[str]:
        url = data.get("url") or data.get("video_url")
        if url:
            return str(url)
        nested = data.get("data")
        if isinstance(nested, dict):
            url = nested.get("url") or nested.get("video_url")
            if url:
                return str(url)
        return None

    @staticmethod
    def _extract_status(data: dict[str, Any]) -> Optional[str]:
        status = data.get("status")
        if status:
            return str(status).lower()
        nested = data.get("data")
        if isinstance(nested, dict) and nested.get("status"):
            return str(nested["status"]).lower()
        return None
