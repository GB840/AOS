"""Ollama 本地开源模型网关（Ollama 原生 REST，默认 :11434）。

单创OS 默认模型路径：开源本地优先，闭源（智谱/agnes）降级 opt-in。
- 零硬依赖：仅标准库 urllib 调 Ollama 原生 /api/chat、/api/tags。
- 开源可验证：Ollama 跑 Qwen/DeepSeek/Llama 等，数据不出本地、无 API 分成。
- 优雅降级：端点不可达时 list_models 返回 []、health 标 unhealthy，由 wiring 降级链跳过。

集成：kernel 包内继承 ModelGateway（相对导入）；独立/测试环境走 fallback
（本地兼容类），避免重型链依赖，保证任意环境可 import + 单测。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    from ..interfaces import ModelGateway
    from ..types import (ChatChunk, ChatResponse, GatewayHealth, Message,
                         ModelCapabilities, ModelInfo)
    _KERNEL_OK = True
except Exception:
    # 轻量 fallback：无 kernel 包上下文（importlib 加载/独立测试）
    ModelGateway = object  # type: ignore
    class ModelInfo:  # type: ignore
        def __init__(self, model_id, provider="ollama", display_name="", extra=None):
            self.model_id = model_id
            self.provider = provider
            self.display_name = display_name
            self.extra = extra or {}
    class GatewayHealth:  # type: ignore
        def __init__(self, healthy, provider="ollama", error="", latency_ms=0.0, model_count=0):
            self.healthy = healthy
            self.provider = provider
            self.error = error
            self.latency_ms = latency_ms
            self.model_count = model_count
    class ChatResponse:  # type: ignore
        def __init__(self, content="", model="", raw=None):
            self.content = content
            self.model = model
            self.raw = raw or {}
    class ChatChunk:  # type: ignore
        def __init__(self, delta="", finish_reason="stop"):
            self.delta = delta
            self.finish_reason = finish_reason
    class ModelCapabilities:  # type: ignore
        def __init__(self, context_window=32768, supports_tools=True,
                     supports_vision=False, supports_streaming=True, extra=None):
            self.context_window = context_window
            self.supports_tools = supports_tools
            self.supports_vision = supports_vision
            self.supports_streaming = supports_streaming
            self.extra = extra or {}
    class Message:  # type: ignore
        def __init__(self, sender="user", recipient="", payload=None):
            self.sender = sender
            self.recipient = recipient
            self.payload = payload or {}
    _KERNEL_OK = False


class OllamaModelGateway(ModelGateway):
    """把本地 Ollama 翻译为内核 ModelGateway 接口（开源默认入口）。"""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url
                         or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.enabled = os.environ.get("OLLAMA_ENABLED", "1") != "0"

    # ---- 内部 REST ----
    def _get(self, path: str, timeout: int = 3) -> Dict[str, Any]:
        req = urllib.request.Request(self.base_url + path,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    # ---- ModelGateway 接口 ----
    def health(self) -> "GatewayHealth":
        try:
            data = self._get("/api/tags")
            return GatewayHealth(healthy=True, provider="ollama",
                                 model_count=len(data.get("models", [])))
        except Exception as e:
            return GatewayHealth(healthy=False, provider="ollama", error=str(e))

    def list_models(self) -> List["ModelInfo"]:
        if not self.enabled:
            return []
        try:
            data = self._get("/api/tags")
            out: List["ModelInfo"] = []
            for m in data.get("models", []):
                name = m.get("name", "")
                out.append(ModelInfo(
                    model_id=f"ollama/{name}", provider="ollama",
                    display_name=name,
                    extra={"local": True, "opensource": True,
                           "size": m.get("size", 0)},
                ))
            return out
        except Exception:
            return []

    def chat(self, model_id: str, messages: List["Message"], **kwargs: Any) -> "ChatResponse":
        ollama_model = model_id.split("/", 1)[1] if "/" in model_id else model_id
        oai = _to_messages(messages, kwargs)
        try:
            resp = self._post("/api/chat", {
                "model": ollama_model,
                "messages": oai,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "num_predict": kwargs.get("max_tokens", 2048),
                },
            })
            content = (resp.get("message") or {}).get("content", "")
            return ChatResponse(content=content, model=model_id,
                                raw={"backend": "ollama", "model": ollama_model})
        except Exception as e:
            return ChatResponse(content="", model=model_id,
                                raw={"error": f"ollama call failed: {e}"})

    async def stream_chat(self, model_id: str, messages: List["Message"],
                          **kwargs: Any) -> AsyncIterator["ChatChunk"]:
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content,
                        finish_reason="stop" if resp.content else "error")

    def get_capabilities(self, model_id: str) -> "ModelCapabilities":
        name = model_id.split("/", 1)[1] if "/" in model_id else model_id
        vision = any(k in name.lower() for k in ("vl", "vision", "llava"))
        return ModelCapabilities(
            context_window=32768, supports_tools=True, supports_vision=vision,
            supports_streaming=True,
            extra={"backend": "ollama", "local": True, "opensource": True},
        )


def _to_messages(messages: List["Message"], kwargs: Dict[str, Any]) -> List[Dict[str, str]]:
    if messages:
        out: List[Dict[str, str]] = []
        for m in messages:
            role = getattr(m, "sender", None) or "user"
            if role not in ("system", "user", "assistant"):
                role = "user"
            out.append({"role": role, "content": _content(getattr(m, "payload", None))})
        return out
    return [{"role": "user", "content": kwargs.get("prompt", "")}]


def _content(payload: Any) -> str:
    if isinstance(payload, dict):
        return (payload.get("prompt") or payload.get("message")
                or payload.get("content") or str(payload))
    return str(payload)


__all__ = ["OllamaModelGateway"]
