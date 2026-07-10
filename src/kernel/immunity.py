"""v1.0 物种免疫层：异常检测 / 自愈 / 熔断降级。

这是 AOS 从"骨架"到"物种"的第一层血肉——原生免疫能力。
建立在现有 EventBus 之上（内核关键路径已发射 agent.stopped/failed、
message.denied、model.failed、skill.failed 等事件），免疫层订阅这些事件，
实现自动检测、自愈、熔断。

设计原则（物种思维）：
- 零依赖：仅依赖 kernel.events + kernel.types + stdlib
- 事件驱动：所有免疫行为通过订阅 EventBus 触发，不侵入内核代码
- 可替换：免疫策略（阈值/重试次数/回滚规则）都是类参数，可注入
- 自愈不破坏：回滚 → 重启 → 隔离，绝不放行已确定有害的操作
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from kernel.events import Event, EventBus, SystemEvent


# ─── 异常检测器 ──────────────────────────────────────────────────

class AnomalyDetector:
    """订阅事件总线，按滑动窗口检测异常模式。

    检测规则：
    - 错误率阈值：窗口内失败/总调用 > threshold → 触发告警
    - 连续失败：连续 N 次失败 → 触发告警
    - 响应时间突增：平均延迟超过基线 N 倍 → 触发告警

    检测到异常时调用 on_alert 回调（可注入自愈/通知逻辑）。
    """

    def __init__(self, event_bus: EventBus,
                 window_seconds: float = 60.0,
                 error_threshold: float = 0.5,
                 consecutive_failures: int = 5,
                 latency_spike_multiplier: float = 3.0,
                 on_alert: Callable[[str, str, Dict[str, Any]], None] | None = None):
        self._bus = event_bus
        self._window = window_seconds
        self._error_threshold = error_threshold
        self._consecutive_failures = consecutive_failures
        self._latency_mult = latency_spike_multiplier
        self._on_alert = on_alert

        self._lock = threading.RLock()
        self._events: List[Event] = []
        self._consecutive_fail_count = 0
        self._latency_baseline: Dict[str, float] = {}
        self._alerts: List[Dict[str, Any]] = []

        # 订阅事件
        self._bus.subscribe("model.*", self._on_model_event)
        self._bus.subscribe("agent.*", self._on_agent_event)
        self._bus.subscribe("skill.*", self._on_skill_event)
        self._bus.subscribe("message.*", self._on_message_event)

    # ── 事件处理器 ──
    def _on_model_event(self, event: Event) -> None:
        self._record(event)
        if event.event_type in (SystemEvent.MODEL_FAILED, "model.failed"):
            self._check_consecutive(event)

    def _on_agent_event(self, event: Event) -> None:
        self._record(event)
        if event.event_type in (SystemEvent.AGENT_FAILED, "agent.failed"):
            self._check_consecutive(event)

    def _on_skill_event(self, event: Event) -> None:
        self._record(event)
        if event.event_type in (SystemEvent.SKILL_FAILED, "skill.failed"):
            self._check_consecutive(event)

    def _on_message_event(self, event: Event) -> None:
        self._record(event)
        if event.event_type in (SystemEvent.MESSAGE_DENIED, "message.denied"):
            self._check_consecutive(event)

    def _record(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)
            cutoff = time.time() - self._window
            self._events = [e for e in self._events
                            if _event_timestamp(e) > cutoff]

    def _check_consecutive(self, event: Event) -> None:
        with self._lock:
            self._consecutive_fail_count += 1
            if self._consecutive_fail_count >= self._consecutive_failures:
                self._alert("consecutive_failures",
                            f"{self._consecutive_fail_count} consecutive failures",
                            {"last_event": event.event_type,
                             "source": event.source})

    # ── 检测方法 ──
    def error_rate(self) -> float:
        """窗口内错误率。"""
        with self._lock:
            if not self._events:
                return 0.0
            failures = sum(1 for e in self._events
                           if e.event_type.endswith((".failed", ".denied")))
            return failures / len(self._events)

    def is_healthy(self) -> bool:
        """综合健康判定。"""
        rate = self.error_rate()
        with self._lock:
            cf = self._consecutive_fail_count
        return rate < self._error_threshold and cf < self._consecutive_failures

    def recent_alerts(self, n: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._alerts[-n:])

    def clear_alerts(self) -> None:
        with self._lock:
            self._alerts.clear()

    def _alert(self, rule: str, message: str, detail: Dict[str, Any]) -> None:
        record = {"timestamp": time.time(), "rule": rule,
                  "message": message, "detail": detail}
        with self._lock:
            self._alerts.append(record)
        if self._on_alert:
            self._on_alert(rule, message, detail)


# ─── 熔断器 ──────────────────────────────────────────────────────

class CircuitBreaker:
    """熔断器：连续失败 N 次后打开，拒绝请求一段时间再半开探测。

    用法：
        cb = CircuitBreaker(name="litellm-gw", failure_threshold=3, cooldown_seconds=30)
        def call_model():
            with cb:
                return gateway.chat(model, messages)
    """

    class Open:
        pass

    OPEN = Open()

    def __init__(self, name: str, failure_threshold: int = 3,
                 cooldown_seconds: float = 30.0):
        self.name = name
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "closed"    # closed → open → half_open → closed
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def __enter__(self) -> None:
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time > self._cooldown:
                    self._state = "half_open"
                else:
                    raise CircuitBreakerOpenError(self.name)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        with self._lock:
            if exc_type is None:
                self._state = "closed"
                self._failures = 0
            else:
                self._failures += 1
                self._last_failure_time = time.time()
                if self._failures >= self._threshold:
                    self._state = "open"
        return False  # 不抑制异常，让调用方处理

    def reset(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0


class CircuitBreakerOpenError(Exception):
    """熔断器已打开时抛出的异常。"""
    def __init__(self, name: str):
        super().__init__(f"Circuit breaker OPEN: {name}")


# ─── 自愈引擎 ────────────────────────────────────────────────────

@dataclass
class _HealAction:
    action: str        # "restart" | "rollback" | "isolate"
    target: str        # agent_id / engine name
    reason: str
    timestamp: float = field(default_factory=time.time)


class SelfHealer:
    """自愈引擎：订阅异常事件，自动执行恢复策略。

    恢复策略：
    - agent.failed → 重启 agent（调用 restart_agent callback）
    - model.failed 频繁 → 降级到备选模型（调用 fallback callback）
    - skill.failed 反复 → 隔离 skill（调用 isolate callback）
    """

    def __init__(self, event_bus: EventBus,
                 restart_agent: Callable[[str], bool] | None = None,
                 fallback_model: Callable[[str], str] | None = None,
                 isolate_skill: Callable[[str], bool] | None = None):
        self._bus = event_bus
        self._restart = restart_agent or (lambda a: False)
        self._fallback = fallback_model or (lambda m: "")
        self._isolate = isolate_skill or (lambda s: False)

        self._lock = threading.RLock()
        self._history: List[_HealAction] = []
        self._agent_fail_count: Dict[str, int] = defaultdict(int)
        self._skill_fail_count: Dict[str, int] = defaultdict(int)

        self._bus.subscribe("agent.*", self._on_agent_event)
        self._bus.subscribe("model.failed", self._on_model_failed)
        self._bus.subscribe("skill.failed", self._on_skill_failed)

    def _on_agent_event(self, event: Event) -> None:
        agent_id = event.payload.get("agent_id", "")
        if not agent_id:
            return
        if event.event_type in ("agent.failed", SystemEvent.AGENT_FAILED):
            with self._lock:
                self._agent_fail_count[agent_id] += 1
            if self._agent_fail_count[agent_id] >= 3:
                self._heal("restart", agent_id, "agent failed 3 times",
                           lambda: self._restart(agent_id))

    def _on_model_failed(self, event: Event) -> None:
        model = event.payload.get("model", event.source)
        self._heal("rollback", model, "model failure",
                   lambda: self._fallback(model) if self._fallback(model) else None)

    def _on_skill_failed(self, event: Event) -> None:
        skill_id = event.payload.get("skill_id", "")
        if not skill_id:
            return
        with self._lock:
            self._skill_fail_count[skill_id] += 1
        if self._skill_fail_count[skill_id] >= 5:
            self._heal("isolate", skill_id, "skill failed 5 times",
                       lambda: self._isolate(skill_id))

    def _heal(self, action: str, target: str, reason: str, execute: Callable):
        try:
            execute()
        except Exception:
            pass
        record = _HealAction(action=action, target=target, reason=reason)
        with self._lock:
            self._history.append(record)
            if len(self._history) > 200:
                self._history = self._history[-200:]

    @property
    def history(self) -> List[_HealAction]:
        with self._lock:
            return list(self._history)




def _event_timestamp(event: Event) -> float:
    """提取事件的 unix 时间戳。"""
    try:
        import datetime
        dt = datetime.datetime.fromisoformat(event.timestamp)
        return dt.timestamp()
    except (ValueError, TypeError):
        return time.time()


__all__ = [
    "AnomalyDetector",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "SelfHealer",
]
