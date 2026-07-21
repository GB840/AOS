"""Real Agnes AI adapter for the AOS open fabric - the LLM GATEWAY plane.

Agnes AI (apihub.agnes-ai.com) 仅暴露 OpenAI 兼容的 chat/completions 文本端点，
AOS 把它作为 LLM Gateway 使用。图/视频能力（images/generations、videos）在
收圆后已退出 Agnes 的路由供给，改由 media-gen（国产智谱）/ comfyui 服务——
对应「agnes 回归纯 LLM Gateway」的决策。

因此本适配器只 advertise LLM_GATEWAY；invoke 遇 media 能力会**诚实拒绝**
（而非连不可达的 agnes 云端拿 503 误判假活），generate_image / generate_video
便捷方法同样诚实拒绝，供显式调用时拿到清晰错误而非静默失败。
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
}


def _requests():
    """延迟导入，保证适配器在缺依赖时仍是合法代码。"""
    import requests  # type: ignore
    return requests


class AgnesAdapter(BaseAgentAdapter):
    """OpenAI-compatible LLM 适配器：仅文本（图/视频已退出 Agnes 路由供给，改由 media-gen/comfyui 服务）。"""

    # 隔离进子进程时，必须显式回灌的密钥类环境变量（subprocess_iso 默认全剥离）。
    # 单一事实源：和 __init__ 里的 os.environ.get 读取保持一致，新增 key 改这一处。
    REQUIRED_ENV: tuple[str, ...] = (
        "AGNES_API_KEY",
        "AGNES_BASE_URL",
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("AGNES_API_KEY", "")
        self._base = (base_url or os.environ.get("AGNES_BASE_URL", AGNES_DEFAULTS["base_url"])).rstrip("/")
        self._health_cache: Optional[tuple[bool, float]] = None

    # ---- 接口实现 ----
    @property
    def engine_id(self) -> str:
        return "agnes"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.LLM_GATEWAY]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        cap = req.capability.value if hasattr(req.capability, "value") else str(req.capability)
        if cap == Capability.LLM_GATEWAY.value:
            return self._chat(req)
        # 收圆：agnes 已退出 media 供给（图/视频改由 media-gen / comfyui 服务）。
        # invoke 遇 media 能力诚实拒绝，而非连不可达的 agnes 云端（503 误判假活）。
        if cap in (Capability.MEDIA_IMAGE.value, Capability.MEDIA_VIDEO.value):
            return InvokeResult(
                ok=False,
                error="agnes 已退出 media 供给：图/视频请改用 media-gen / comfyui 适配器",
            )
        return InvokeResult(ok=False, error=f"agnes: unsupported capability {cap}")

    def health(self) -> bool:
        """诚实判活：必须配置有效 key，且真实存活端点 /models 返回 2xx 才算 live。

        历史坑：曾直接探 Base URL(/v1)，Agnes 对 GET /v1 返回 404 Invalid URL，
        而原代码 `status_code < 500` 把 404 也判成"活着"——典型的假活。
        改为探 OpenAI 兼容标准存活端点 /models（带 Bearer key），并严格要求 2xx：
          - 2xx (200) -> 服务真 live 且 key 有效   => True
          - 401       -> key 无效，适配器无法服务  => False（诚实：不能服务即不健康）
          - 404       -> URL/服务不对              => False
          - 5xx       -> 服务端故障                => False
          - 连接/超时/DNS 异常                     => False
        结果缓存 30s，避免每次构造枢纽都打网络（现有测试套件会多次建枢纽）。
        """
        if not self._api_key:
            return False
        now = time.time()
        if self._health_cache is not None and (now - self._health_cache[1]) < 30:
            return self._health_cache[0]
        ok = False
        try:
            # 探真实存活端点 /models（而非 /v1，后者 Agnes 返回 404 假活）
            r = _requests().get(f"{self._base}/models", timeout=6, headers=self._headers())
            ok = 200 <= r.status_code < 300  # 严格 2xx：404/401/5xx 一律判 dead
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
        # 收圆：agnes 已退出 media 供给，图改由 media-gen / comfyui 服务。
        return InvokeResult(
            ok=False,
            error="agnes 已退出 media 供给：图请改用 media-gen / comfyui 适配器",
        )

    def generate_video(self, prompt: str, *, model: Optional[str] = None,
                       poll_timeout: float = 180.0, **opts: Any) -> InvokeResult:
        return InvokeResult(
            ok=False,
            error="agnes 已退出 media 供给：视频请改用 media-gen / comfyui 适配器",
        )

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
