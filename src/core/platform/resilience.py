"""
AOS v5.0 — 统一弹性框架 (Resilience)

对标蓝图 RESILIENCE(重试/熔断/降级)。纯 Python, 零硬依赖, 线程安全。
满足蓝图节点: RESILIENCE(弹性服务: 重试/熔断/降级) + 作为 FABRIC 的执行保护。

设计原则 (严谨 + 开放 + 灵活):
  - 所有装饰器都保留原函数签名与返回值语义; 失败时按策略处理, 不吞异常以外的其他副作用。
  - CircuitBreaker 状态机: closed -> open(失败超阈值) -> half-open(冷却后放行试探) -> closed/open。
  - 可注入: 任意 callable 可作为 fallback, 便于测试与替换。
"""

import functools
import logging
import threading
import time
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """熔断器开启时抛出, 表明快速失败 (不访问下游)。"""


class CircuitBreaker:
    """简单但正确的熔断状态机。线程安全。"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0,
                 expected_exceptions: Tuple[Type[BaseException], ...] = (Exception,)):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if time.time() - self._opened_at >= self.recovery_timeout:
                return "half-open"
            return "open"

    def allow(self) -> bool:
        """是否放行本次调用。half-open 试探也返回 True (试探成功后关闭)。"""
        with self._lock:
            if self._opened_at is None:
                return True
            if time.time() - self._opened_at >= self.recovery_timeout:
                return True
            return False

    def on_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def on_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.time()

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        if not self.allow():
            raise CircuitBreakerOpen(f"circuit open (failures>={self.failure_threshold})")
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except self.expected_exceptions:
            self.on_failure()
            # half-open 试探失败 -> 继续保持 open
            if self.state == "half-open":
                with self._lock:
                    self._opened_at = time.time()
            raise


def retry(times: int = 3, backoff: float = 0.0,
          exceptions: Tuple[Type[BaseException], ...] = (Exception,)):
    """重试装饰器。最后一次仍失败则原样抛出。"""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last: Optional[BaseException] = None
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:  # type: ignore[misc]
                    last = e
                    if attempt < times - 1 and backoff:
                        time.sleep(backoff)
            assert last is not None
            raise last
        return wrapper
    return decorator


def fallback(default: Any = None, handler: Optional[Callable[[Exception, Tuple, dict], Any]] = None,
             exceptions: Tuple[Type[BaseException], ...] = (Exception,)):
    """失败时返回 default, 或调用 handler(exc, args, kwargs) 计算回退值。"""
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except exceptions as e:  # type: ignore[misc]
                if handler is not None:
                    return handler(e, args, kwargs)
                return default
        return wrapper
    return decorator


def degrade(fn: Callable[..., Any]) -> Callable[..., Any]:
    """软降级: 异常时返回 None (而非抛出), 用于非关键路径。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - 软降级语义
            logger.warning("degrade: %s raised, returning None: %s", fn.__name__, e)
            return None
    return wrapper
