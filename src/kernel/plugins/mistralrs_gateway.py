"""插件：把本地 mistralrs 三端点登记为内核 ModelGateway（v1.0 模型网关层）。

补齐对账表缺口 G3：内核原 LiteLLMModelGateway 只认 zhipu/glm-4-flash，
完全不知道 mistralrs 的存在。本插件让内核直接调到用户主用的本地推理运行时。

真相源与运行链路对齐（不重造）：
- 端口/模型 id 全部读 `utils.config.config`（与 src/router/llm_router.py 同源）。
- mistralrs `serve` 暴露 OpenAI 兼容 API：base_url = f"{HOST}:{port}/v1"，
  api_key 任意（"mistralrs"），model 字段必须是其 /v1/models 实际报告的目录路径 id。
- 三端点：GENERAL(1234) / CODING(1235) / REASONING(1236)。

内核核心零依赖；本文件位于 plugins/，允许 import 具体实现（openai / config）。
缺 openai 库或端点不可达时优雅降级（返回 ok=False 的空响应），内核不崩。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from ..interfaces import ModelGateway
from ..types import (
    ChatChunk,
    ChatResponse,
    GatewayHealth,
    Message,
    ModelCapabilities,
    ModelInfo,
)

try:
    from openai import OpenAI
    _OPENAI_OK = True
except Exception:  # openai 未安装
    OpenAI = None  # type: ignore
    _OPENAI_OK = False


# 内核层稳定模型 id  →  (config 端口属性, config 模型属性)
# 这三个 id 与 src/router/llm_router.py 的 ModelProvider 值一致，便于双轨对齐。
_ROUTES = {
    "mistralrs_general":   ("MISTRALRS_PORT_GENERAL",   "MISTRALRS_MODEL_GENERAL"),
    "mistralrs_coding":    ("MISTRALRS_PORT_CODING",    "MISTRALRS_MODEL_CODING"),
    "mistralrs_reasoning": ("MISTRALRS_PORT_REASONING", "MISTRALRS_MODEL_REASONING"),
}


class MistralRSModelGateway(ModelGateway):
    """把本地 mistralrs 三端点翻译为内核 ModelGateway 接口。"""

    def __init__(self, config: Any = None) -> None:
        if config is None:
            from utils.config import config as _cfg
            config = _cfg
        self._cfg = config
        self._host = getattr(config, "MISTRALRS_HOST", "http://localhost")
        self._clients: Dict[str, Any] = {}  # model_id -> OpenAI client（惰性建）

    # ---- 内部：解析路由 ----
    def _resolve(self, model_id: str):
        """model_id → (port, mistralrs_model_path)。未知 id 回退 general。"""
        port_attr, model_attr = _ROUTES.get(model_id, _ROUTES["mistralrs_general"])
        port = getattr(self._cfg, port_attr)
        model_path = getattr(self._cfg, model_attr)
        return port, model_path

    def _client(self, model_id: str):
        if not _OPENAI_OK:
            return None
        if model_id not in self._clients:
            port, _ = self._resolve(model_id)
            self._clients[model_id] = OpenAI(
                base_url=f"{self._host}:{port}/v1",
                api_key="mistralrs",
            )
        return self._clients[model_id]

    # ---- ModelGateway 接口 ----
    def health(self) -> GatewayHealth:
        import time
        if not getattr(self._cfg, "MISTRALRS_ENABLED", False):
            return GatewayHealth(healthy=False, provider="mistralrs",
                                error="MISTRALRS_ENABLED=False")
        t0 = time.time()
        try:
            client = self._client("mistralrs_general")
            if client is None:
                return GatewayHealth(healthy=False, provider="mistralrs",
                                    error="openai lib unavailable")
            models = client.models.list()
            latency = (time.time() - t0) * 1000
            return GatewayHealth(
                healthy=True, provider="mistralrs",
                latency_ms=round(latency, 1),
                model_count=len(models.data) if models else 0,
            )
        except Exception as e:
            return GatewayHealth(healthy=False, provider="mistralrs",
                                error=str(e), latency_ms=(time.time() - t0) * 1000)

    def list_models(self) -> List[ModelInfo]:
        if not getattr(self._cfg, "MISTRALRS_ENABLED", False):
            return []
        display = {
            "mistralrs_general": "MistralRS · 通用 (1234)",
            "mistralrs_coding": "MistralRS · 代码 (1235)",
            "mistralrs_reasoning": "MistralRS · 推理/长文 (1236)",
        }
        return [
            ModelInfo(model_id=mid, provider="mistralrs", display_name=display[mid])
            for mid in _ROUTES
        ]

    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        client = self._client(model_id)
        if client is None:
            return ChatResponse(content="", model=model_id,
                                raw={"error": "openai lib unavailable"})
        _, model_path = self._resolve(model_id)
        oai_messages = _to_openai_messages(messages, kwargs)
        try:
            resp = client.chat.completions.create(
                model=model_path,
                messages=oai_messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            content = resp.choices[0].message.content or ""
            return ChatResponse(content=content, model=model_id,
                                raw={"backend": "mistralrs", "model_path": model_path})
        except Exception as e:  # 端点未起 / 网络错误 —— 内核不崩，交由降级链处理
            return ChatResponse(content="", model=model_id,
                                raw={"error": f"mistralrs call failed: {e}"})

    async def stream_chat(self, model_id: str, messages: List[Message],
                          **kwargs: Any) -> AsyncIterator[ChatChunk]:
        # mistralrs 支持原生流，但为与现有薄缝一致，先退化为单次完整结果一个分片。
        resp = self.chat(model_id, messages, **kwargs)
        yield ChatChunk(delta=resp.content,
                        finish_reason="stop" if resp.content else "error")

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        # 本地量化小模型：上下文以保守值给出；工具/视觉按模型能力保守声明。
        ctx = 32768 if model_id == "mistralrs_reasoning" else 8192
        return ModelCapabilities(
            context_window=ctx,
            supports_tools=False,
            supports_vision=False,
            supports_streaming=True,
            extra={"backend": "mistralrs", "local": True},
        )


def _to_openai_messages(messages: List[Message], kwargs: Dict[str, Any]) -> List[Dict[str, str]]:
    """内核 Message 列表 → OpenAI chat messages。空列表时用 kwargs['prompt']。"""
    if messages:
        out: List[Dict[str, str]] = []
        for m in messages:
            role = m.sender or "user"
            if role not in ("system", "user", "assistant"):
                role = "user"
            out.append({"role": role, "content": _content(m.payload)})
        return out
    prompt = kwargs.get("prompt", "")
    return [{"role": "user", "content": prompt}]


def _content(payload: Any) -> str:
    if isinstance(payload, dict):
        return (payload.get("prompt") or payload.get("message")
                or payload.get("content") or str(payload))
    return str(payload)


__all__ = ["MistralRSModelGateway"]
