"""v1.0 模型降级链：多模型 fallback + 自动故障转移。

这是 v1.0 物种思维"模型网关层（可换模型）"的品质增强项。
在 ModelGatewayLayer 之上增加自动降级能力：主模型不可用（无 key / 超时 /
返回空）时，自动切换到备选模型，保证系统韧性。

"依赖倒置"：本模块只依赖 ModelGateway ABC + stdlib，不绑定任何具体引擎。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..interfaces import ModelGateway
from ..types import ChatResponse, Message


@dataclass
class FallbackResult:
    """降级链的返回：包含最终结果 + 实际使用的模型 + 尝试历史。"""
    response: ChatResponse
    model_used: str
    attempts: List[str] = field(default_factory=list)  # 尝试过的模型列表
    errors: List[str] = field(default_factory=list)     # 每次失败的简要原因


class FallbackChain:
    """多模型自动降级链。

    用法：
        chain = FallbackChain(gateway, ["openai/gpt-4o", "zhipu/glm-4-flash", "ollama/llama3"])
        result = chain.chat_with_fallback(prompt="你好")
        # 如果 gpt-4o 失败（无 key / 超时），自动切 glm-4-flash，再失败切 llama3

    每个模型尝试时：
    - 异常 → 记录并跳过，切下一个
    - 返回 content 为空 → 标记不健康（可通过 health_check 判定），切下一个
    - 成功 → 立即返回，不再尝试候补
    """

    def __init__(self, gateway: ModelGateway,
                 models: List[str],
                 health_check: Callable[[str], bool] | None = None,
                 on_fallback: Callable[[str, str, str], None] | None = None) -> None:
        """
        gateway:      ModelGateway 插件实例
        models:       降级链模型列表（优先级从高到低）
        health_check: 可选模型健康检查函数(model_id)→bool
        on_fallback:  可选降级回调(from_model, to_model, reason)
        """
        self._gateway = gateway
        self._models = list(models)
        self._health_check = health_check
        self._on_fallback = on_fallback
        self._lock = threading.RLock()

    @property
    def models(self) -> List[str]:
        with self._lock:
            return list(self._models)

    def add_model(self, model_id: str, position: int | None = None) -> None:
        """追加或插入模型到降级链。"""
        with self._lock:
            if position is None:
                self._models.append(model_id)
            else:
                self._models.insert(position, model_id)

    def remove_model(self, model_id: str) -> bool:
        with self._lock:
            if model_id in self._models:
                self._models.remove(model_id)
                return True
            return False

    def reorder(self, models: List[str]) -> None:
        """重排降级链顺序（覆盖）。"""
        with self._lock:
            assert all(m in self._models for m in models), "models 必须是现有子集"
            remaining = [m for m in self._models if m not in models]
            self._models = models + remaining

    def chat_with_fallback(
        self, prompt: str, system: str = "", **kwargs: Any
    ) -> FallbackResult:
        """经降级链调用模型。

        prompt: 用户输入
        system: 系统提示
        kwargs: 传给 ModelGateway.chat 的额外参数
        """
        with self._lock:
            models = list(self._models)

        attempts: List[str] = []
        errors: List[str] = []
        last_resp: Optional[ChatResponse] = None

        for idx, model_id in enumerate(models):
            # 健康检查（可选）
            if self._health_check is not None and not self._health_check(model_id):
                msg = f"{model_id}: unhealthy (skipped)"
                attempts.append(model_id)
                errors.append(msg)
                continue

            attempts.append(model_id)

            try:
                msgs: List[Message] = []
                if system:
                    msgs.append(Message(sender="system", recipient="user",
                                        payload={"content": system}))
                msgs.append(Message(sender="user", recipient="assistant",
                                    payload={"prompt": prompt}))
                resp = self._gateway.chat(model_id, msgs, **kwargs)
                last_resp = resp

                if resp.content:
                    # 成功！
                    return FallbackResult(response=resp, model_used=model_id,
                                          attempts=attempts, errors=errors)
                else:
                    msg = f"{model_id}: empty response"
                    errors.append(msg)
            except Exception as exc:
                msg = f"{model_id}: {exc}"
                errors.append(msg)
                if self._on_fallback:
                    next_model = models[idx + 1] if idx + 1 < len(models) else None
                    self._on_fallback(model_id, next_model or "(end)", str(exc))
                continue

            # 空响应触发的 fallback
            if self._on_fallback:
                next_model = models[idx + 1] if idx + 1 < len(models) else None
                if next_model:
                    self._on_fallback(model_id, next_model, "empty response")

        # 所有模型都失败
        return FallbackResult(
            response=last_resp or ChatResponse(content="", model="(none)"),
            model_used="(none)",
            attempts=attempts,
            errors=errors,
        )

    def _next_after(self, model_id: str) -> Optional[str]:
        with self._lock:
            try:
                idx = self._models.index(model_id)
                return self._models[idx + 1] if idx + 1 < len(self._models) else None
            except ValueError:
                return None

    async def chat_with_fallback_async(
        self, prompt: str, system: str = "", **kwargs: Any
    ) -> FallbackResult:
        """降级链的异步版本（asyncio.to_thread 包装同步调用）。"""
        import asyncio
        return await asyncio.to_thread(self.chat_with_fallback, prompt, system, **kwargs)

    def health_status(self) -> Dict[str, bool]:
        """快速检查降级链各模型的健康状态。"""
        with self._lock:
            models = list(self._models)
        if self._health_check is None:
            return {m: True for m in models}
        return {m: self._health_check(m) for m in models}
