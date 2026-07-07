"""
AOS v5.0 — 平台外壳层 (Platform Shell)

对标 AgentOS 蓝图里缺失的"平台工程外壳": 可观测 / 弹性 / 中间件 / 通知 / 事件溯源。
所有模块零硬依赖、依赖可探测、失败优雅降级 (严谨 + 开放 + 灵活)。

使用:
    from core.platform import Metrics, Tracer, CircuitBreaker, NotificationService, EventStore
"""

from core.platform.observability import (
    Metrics,
    Tracer,
    HealthAggregator,
    prometheus_exposition,
    default_metrics,
    default_tracer,
    default_health,
)
from core.platform.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    retry,
    fallback,
    degrade,
)
from core.platform.middleware import (
    IdempotencyStore,
    idempotent,
    RateLimiter,
    inject_trace,
)
from core.platform.notify import NotificationService
from core.platform.eventstore import EventStore
from core.platform.fileproc import extract_text
from core.platform.sandbox import Sandbox, PythonSandbox, WasmSandbox
from core.platform.cold import ColdStore
from core.platform.devops import Pipeline
from core.platform.compat import CompatMatrix

__all__ = [
    "Metrics", "Tracer", "HealthAggregator", "prometheus_exposition",
    "default_metrics", "default_tracer", "default_health",
    "CircuitBreaker", "CircuitBreakerOpen", "retry", "fallback", "degrade",
    "IdempotencyStore", "idempotent", "RateLimiter", "inject_trace",
    "NotificationService", "EventStore",
    "extract_text", "Sandbox", "PythonSandbox", "WasmSandbox",
    "ColdStore", "Pipeline", "CompatMatrix",
]
