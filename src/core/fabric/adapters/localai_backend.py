"""LocalAI 接入 —— 真接开源（Apache-2.0），非自研等价。

项目：mudler/LocalAI（GitHub，Apache-2.0，可商用）
定位：自托管、OpenAI 兼容的本地推理 API（LLM / 嵌入 / 图像 / 音频），
消费级硬件可跑，无需 GPU。AOS 的 L1A 节点原本标「自研等价」，
现真接为 opt-in 模型后端客户端。

接入方式（对齐 AOS 第一性「本地优先 / 不绑死 / 诚实降级」）：
- LocalAI 是 Go 服务端，AOS 这边是**轻量 HTTP 客户端**（OpenAI 兼容协议）。
- 服务端需独立运行（docker 或二进制）；本客户端只负责调用，不内嵌服务进程。
- 重依赖（requests）惰性导入；服务端不可达时 available()=False，绝不谎报 live。
- 与 AOS 现有 model_gateway 三级路由互补：LocalAI 作为「本地/私有化」一档。
"""
from __future__ import annotations

import os
from typing import List, Optional

try:
    import requests

    REQUESTS_AVAILABLE = True
except Exception:  # pragma: no cover
    requests = None
    REQUESTS_AVAILABLE = False


class LocalAIBackend:
    """LocalAI OpenAI 兼容客户端（opt-in，需运行中的 LocalAI 服务端）。"""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (
            base_url
            or os.environ.get("AOS_LOCALAI_URL")
            or "http://localhost:8080"
        ).rstrip("/")

    # ---- 可用性（如实，探活服务端）----
    def is_available(self) -> bool:
        if not REQUESTS_AVAILABLE:
            return False
        try:
            r = requests.get(f"{self.base_url}/healthz", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def health_detail(self) -> dict:
        return {
            "engine": "localai",
            "license": "Apache-2.0",
            "base_url": self.base_url,
            "client_ready": REQUESTS_AVAILABLE,
            "server_reachable": self.is_available(),
            "ready": REQUESTS_AVAILABLE and self.is_available(),
            "note": "需独立运行 LocalAI 服务端（docker run -p 8080:8080 localai/localai）；本客户端仅调用其 OpenAI 兼容 API",
        }

    # ---- 调用（OpenAI 兼容）----
    def chat(self, messages: List[dict], model: str = "gpt-3.5-turbo", **kwargs) -> dict:
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests 未安装：pip install requests")
        if not self.is_available():
            raise RuntimeError(f"LocalAI 服务端不可达：{self.base_url}（请先启动 LocalAI）")
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={"model": model, "messages": messages, **kwargs},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def list_models(self) -> list:
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests 未安装：pip install requests")
        if not self.is_available():
            raise RuntimeError(f"LocalAI 服务端不可达：{self.base_url}")
        resp = requests.get(f"{self.base_url}/v1/models", timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
