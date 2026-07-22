"""v1.0 模型网关层：统一调用 / 智能路由 / 成本控制。

这是 v1.0 物种思维中"模型网关层（可换模型）"的默认实现。
层级的抽象接口是 ModelGateway(ABC)（定义在 ../interfaces.py）。
本层在其上叠加三个子组件：统一调用、智能路由、成本控制。

依赖倒置：本层只依赖 ModelGateway ABC + stdlib，不 import 任何具体模型引擎。
换引擎只需换传入的 gateway 实例，本层逻辑不变。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import threading

from ..interfaces import ModelGateway
from ..types import ChatResponse, Message, ModelInfo


# ─── 智能路由策略 ────────────────────────────────────────────────

class RouteStrategy:
    """路由策略命名空间。"""
    CAPABILITY = "capability"   # 按能力匹配：需要 tool → 选 supports_tools 的
    COST = "cost"               # 按成本最低（需价格表）
    BALANCED = "balanced"       # 能力匹配优先，平级选成本低的


# 默认价格表（可替换 / 可扩展）。价格单位：token 美元单价。
# 实际使用时替换为真实定价数据（litellm cost_map / 云厂商定价 API）。
_DEFAULT_PRICE_REGISTRY: Dict[str, float] = {
    # 开源本地模型：本地推理零边际成本，登记为 0（成本路由会优先选）
    "ollama/qwen3:8b": 0.0,
    "ollama/qwen2.5:7b": 0.0,
    "ollama/deepseek-r1:8b": 0.0,
    "ollama/llama3.1:8b": 0.0,
    # 闭源兜底（opt-in）：保留价格用于成本追踪
    "zhipu/glm-4-flash": 0.0001,
    "openai/gpt-4o": 0.0025,
    "openai/gpt-4o-mini": 0.00015,
    "anthropic/claude-sonnet-4": 0.001,
}


# ─── 成本追踪器 ──────────────────────────────────────────────────

@dataclass
class _CostEntry:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_count: int = 0


class CostTracker:
    """线程安全的模型成本 / token 追踪器。

    用法：
        tracker = CostTracker()
        tracker.record("zhipu/glm-4-flash", prompt_tokens=500, completion_tokens=200)
        print(tracker.usage("zhipu/glm-4-flash"))
        if tracker.check_budget("zhipu/glm-4-flash", limit_usd=1.0):
            pass  # 额度内
    """

    def __init__(self, price_registry: Dict[str, float] | None = None) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[str, _CostEntry] = {}
        self._price = price_registry or _DEFAULT_PRICE_REGISTRY.copy()

    @property
    def price_registry(self) -> Dict[str, float]:
        return dict(self._price)

    def set_price(self, model_id: str, usd_per_token: float) -> None:
        """动态更新模型价格（插拔式价格表）。"""
        self._price[model_id] = usd_per_token

    def record(self, model_id: str, prompt_tokens: int = 0,
               completion_tokens: int = 0) -> None:
        with self._lock:
            entry = self._entries.setdefault(model_id, _CostEntry())
            entry.prompt_tokens += prompt_tokens
            entry.completion_tokens += completion_tokens
            entry.request_count += 1

    def usage(self, model_id: str) -> Dict[str, Any]:
        with self._lock:
            entry = self._entries.get(model_id)
            if entry is None:
                return {"model": model_id, "total_tokens": 0, "estimated_usd": 0.0,
                        "requests": 0}
            tokens = entry.prompt_tokens + entry.completion_tokens
            price = self._price.get(model_id, 0)
            return {
                "model": model_id,
                "prompt_tokens": entry.prompt_tokens,
                "completion_tokens": entry.completion_tokens,
                "total_tokens": tokens,
                "estimated_usd": round(tokens * price, 8),
                "requests": entry.request_count,
            }

    def total_usage(self) -> Dict[str, Any]:
        """所有模型的汇总用量与估算成本。"""
        with self._lock:
            total_tokens = 0
            total_usd = 0.0
            total_requests = 0
            per_model: Dict[str, Any] = {}
            for mid, entry in self._entries.items():
                t = entry.prompt_tokens + entry.completion_tokens
                usd = round(t * self._price.get(mid, 0), 8)
                total_tokens += t
                total_usd += usd
                total_requests += entry.request_count
                per_model[mid] = {"tokens": t, "estimated_usd": usd,
                                  "requests": entry.request_count}
            return {
                "total_tokens": total_tokens,
                "estimated_usd": round(total_usd, 8),
                "total_requests": total_requests,
                "per_model": per_model,
            }

    def check_budget(self, model_id: str, limit_usd: float) -> bool:
        """检查模型是否超过预算。"""
        return self.usage(model_id)["estimated_usd"] < limit_usd

    def reset(self, model_id: str | None = None) -> None:
        with self._lock:
            if model_id is None:
                self._entries.clear()
            else:
                self._entries.pop(model_id, None)


# ─── 模型网关层 ──────────────────────────────────────────────────

class ModelGatewayLayer:
    """v1.0 模型网关层（可换模型）。

    三个子组件：
    1. 统一调用 → chat_unified(prompt, model, ...)
    2. 智能路由 → route(prompt, strategy) → model_id
    3. 成本控制 → cost_tracker: CostTracker
    """

    def __init__(
        self,
        gateway: ModelGateway,
        models: List[str] | None = None,
        price_registry: Dict[str, float] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._gateway = gateway
        self._models = models or [m.model_id for m in gateway.list_models()]
        self.cost_tracker = CostTracker(price_registry=price_registry)

    # ── 统一调用 ──
    def chat_unified(self, prompt: str, model: str | None = None,
                     system: str = "", **kwargs: Any) -> ChatResponse:
        """统一入口：任意 prompt → 任意模型 → ChatResponse。"""
        model_id = model or self._default_model()
        msgs: List[Message] = []
        if system:
            msgs.append(Message(sender="system", recipient="user", payload={"content": system}))
        msgs.append(Message(sender="user", recipient="assistant", payload={"prompt": prompt}))
        resp = self._gateway.chat(model_id, msgs, **kwargs)
        self.cost_tracker.record(model_id)
        return resp

    # ── 智能路由 ──
    def route(self, prompt: str, strategy: str = RouteStrategy.BALANCED,
              required_capabilities: Dict[str, bool] | None = None) -> str:
        """根据策略从注册模型中选出最合适的 model_id。

        strategy:
          "capability" — 只按能力匹配（筛选 supports_tools / supports_vision）
          "cost"       — 只按价格排序（最低价优先）
          "balanced"   — 先能力筛，平级选成本低（默认）
        """
        return self._route_model(strategy, required_capabilities or {})

    def _default_model(self) -> str:
        with self._lock:
            if self._models:
                # 开源本地模型优先（ollama/ 开头），兑现「开源默认」
                for m in self._models:
                    if m.startswith("ollama/"):
                        return m
                return self._models[0]
            # 无任何网关时：env 覆盖 > 历史默认（仍建议配置开源本地模型）
            return os.environ.get("AOS_DEFAULT_MODEL", "zhipu/glm-4-flash")

    def _route_model(self, strategy: str, caps: Dict[str, bool]) -> str:
        if strategy == RouteStrategy.COST:
            return self._lowest_cost_model()
        if strategy == RouteStrategy.CAPABILITY:
            return self._best_capability_model(caps) or self._default_model()
        # balanced: capability first, cost as tiebreaker
        best = self._best_capability_model(caps)
        if best is not None:
            return best
        return self._lowest_cost_model()

    def _best_capability_model(self, caps: Dict[str, bool]) -> Optional[str]:
        if not caps:
            return None
        with self._lock:
            scored: List[tuple[int, float, str]] = []
            for mid in self._models:
                mc = self._gateway.get_capabilities(mid)
                score = 0
                if caps.get("tools") and mc.supports_tools:
                    score += 2
                if caps.get("vision") and mc.supports_vision:
                    score += 2
                if caps.get("streaming") and mc.supports_streaming:
                    score += 1
                if score > 0:
                    price = self.cost_tracker.price_registry.get(mid, 0.01)
                    scored.append((-score, price, mid))
            scored.sort()
            return scored[0][2] if scored else None

    def _lowest_cost_model(self) -> str:
        with self._lock:
            best = self._default_model()
            best_price = float("inf")
            for mid in self._models:
                p = self.cost_tracker.price_registry.get(mid)
                if p is not None and p < best_price:
                    best_price = p
                    best = mid
            return best

    def list_models(self) -> List[ModelInfo]:
        return self._gateway.list_models()

    def add_model(self, model_id: str) -> None:
        with self._lock:
            if model_id not in self._models:
                self._models.append(model_id)

    def set_price(self, model_id: str, usd_per_token: float) -> None:
        with self._lock:
            self.cost_tracker.set_price(model_id, usd_per_token)
