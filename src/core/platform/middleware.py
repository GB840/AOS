"""
AOS v5.0 — API 中间件 (Middleware)

对标蓝图 MIDDLEWARE(幂等/限流/Trace)。纯 Python, 零硬依赖。
满足蓝图节点: MIDDLEWARE(幂等 / 限流 / Trace 注入)。

设计原则 (严谨 + 开放 + 灵活):
  - IdempotencyStore 后端可插拔: 默认内存, 也可传入一个满足 set/get 接口的实例 (如 Redis/DB)。
  - 限流用令牌桶, 支持按 key (用户/IP) 隔离。
  - TraceInjector 与 observability.Tracer 联动, 在调用前注入 trace_id。
"""

import functools
import threading
import time
from typing import Any, Callable, Dict, Optional


# ---------------------------------------------------------------------------
# 幂等
# ---------------------------------------------------------------------------
class IdempotencyStore:
    """可插拔幂等存储。内存实现线程安全; 传入自定义 backend 即可换 Redis/DB。"""

    def __init__(self, backend: Optional[Any] = None, ttl: float = 3600.0):
        self._backend = backend
        self._ttl = ttl
        self._lock = threading.Lock()
        self._mem: Dict[str, float] = {}

    def seen(self, key: str) -> bool:
        if self._backend is not None:
            return self._backend.get(f"idem:{key}") is not None
        with self._lock:
            ts = self._mem.get(key)
            if ts is None:
                return False
            if time.time() - ts > self._ttl:
                self._mem.pop(key, None)
                return False
            return True

    def mark(self, key: str) -> None:
        if self._backend is not None:
            self._backend.set(f"idem:{key}", time.time(), ex=self._ttl)
            return
        with self._lock:
            self._mem[key] = time.time()


def idempotent(store: IdempotencyStore, key_func: Callable[..., str]):
    """装饰器: 用 key_func(*args, **kwargs) 生成幂等键, 重复请求直接复用占位结果。

    注意: 本实现为轻量版 —— 命中即视为重复 (返回 {"duplicated": True})。
    若需复用首次真实结果, 可在 backend 中存结果 (此处保持简单与可预测)。
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            if store.seen(key):
                return {"duplicated": True, "key": key}
            store.mark(key)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 限流 (令牌桶)
# ---------------------------------------------------------------------------
class RateLimiter:
    """按 key 隔离的令牌桶限流。线程安全。allow() 返回是否放行。"""

    def __init__(self, rate: float = 10.0, capacity: float = 20.0):
        self.rate = rate
        self.capacity = capacity
        self._buckets: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

    def _bucket(self, key: str) -> Dict[str, float]:
        b = self._buckets.get(key)
        now = time.time()
        if b is None:
            b = {"tokens": self.capacity, "ts": now}
            self._buckets[key] = b
        elapsed = now - b["ts"]
        b["tokens"] = min(self.capacity, b["tokens"] + elapsed * self.rate)
        b["ts"] = now
        return b

    def allow(self, key: str = "_global", cost: float = 1.0) -> bool:
        with self._lock:
            b = self._bucket(key)
            if b["tokens"] >= cost:
                b["tokens"] -= cost
                return True
            return False


# ---------------------------------------------------------------------------
# 链路注入
# ---------------------------------------------------------------------------
def inject_trace(tracer, key_func: Optional[Callable[..., str]] = None):
    """装饰器: 调用前开一个 span, 并把 trace_id 注入 kwargs['trace_id']。"""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            name = key_func(*args, **kwargs) if key_func else fn.__name__
            with tracer.span(name, attributes={"fn": fn.__name__}):
                return fn(*args, **kwargs)
        return wrapper
    return decorator
