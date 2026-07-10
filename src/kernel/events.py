"""v1.0 系统事件总线：发布/订阅 + 内置事件类型。

这是 v1.0 物种思维的品质增强项。内核在关键路径发射事件，外部
（日志/监控/审计/通知插件）可订阅这些事件，实现可观测性与解耦扩展。

"依赖倒置"：本模块零依赖（仅 stdlib），内核和层都可 import。
事件订阅者可以是任何 callable，不绑定具体框架。

内置事件类型覆盖内核三职责 + 四层关键操作。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Dict, List, Optional


# ─── 事件命名空间 ─────────────────────────────────────────────────

class SystemEvent:
    """系统事件类型命名空间。"""
    # 内核生命周期
    AGENT_REGISTERED = "agent.registered"
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_FAILED = "agent.failed"

    # 消息路由
    MESSAGE_ROUTED = "message.routed"
    MESSAGE_DENIED = "message.denied"

    # 权限
    PERMISSION_CHECKED = "permission.checked"
    PERMISSION_DENIED = "permission.denied"

    # 模型网关
    MODEL_INVOKED = "model.invoked"
    MODEL_FAILED = "model.failed"
    MODEL_FALLBACK = "model.fallback"

    # 技能总线
    SKILL_DISCOVERED = "skill.discovered"
    SKILL_CALLED = "skill.called"
    SKILL_FAILED = "skill.failed"

    # Agent 运行时
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    MEMORY_SET = "memory.set"
    MEMORY_CLEARED = "memory.cleared"

    # 插件
    PLUGIN_REGISTERED = "plugin.registered"
    PLUGIN_REMOVED = "plugin.removed"

    # 系统
    SYSTEM_STARTED = "system.started"

    # 成本
    COST_RECORDED = "cost.recorded"


# ─── 事件数据 ─────────────────────────────────────────────────────

@dataclass
class Event:
    """一条系统事件。

    event_type:  事件类型（见 SystemEvent 常量）
    source:      事件来源标识（kernel / model_gateway / mcp_bus / ...）
    payload:     事件数据
    timestamp:   事件发生时间（ISO 8601）
    trace_id:    可选追踪 ID（串联多次事件）
    """
    event_type: str
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            import datetime
            self.timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()


# 事件处理器类型：callable(Event) → 无返回值
EventHandler = Callable[[Event], None]


# ─── 事件总线 ─────────────────────────────────────────────────────

class EventBus:
    """线程安全的事件总线。

    支持按事件类型订阅、通配符匹配、同步/异步发射。

    用法：
        bus = EventBus()

        # 订阅
        bus.subscribe(SystemEvent.AGENT_STARTED, lambda e: print(f"started: {e.payload}"))
        bus.subscribe("agent.*", lambda e: print(f"agent event: {e.event_type}"))

        # 发射
        bus.emit(Event(SystemEvent.AGENT_STARTED, "kernel", payload={"agent_id": "a1"}))

        # 历史
        for e in bus.recent(n=20):
            print(e.event_type, e.timestamp)
    """

    def __init__(self, max_history: int = 500) -> None:
        self._lock = Lock()
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._history: List[Event] = []
        self._max_history = max_history

    # ── 订阅 ──
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅一个事件类型。支持 'agent.*' 通配符。"""
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """取消订阅。返回是否找到并移除。"""
        with self._lock:
            entries = self._subscribers.get(event_type, [])
            if handler in entries:
                entries.remove(handler)
                if not entries:
                    del self._subscribers[event_type]
                return True
            return False

    def subscriber_count(self, event_type: str) -> int:
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    # ── 发射 ──
    def emit(self, event: Event) -> None:
        """同步发射事件到所有匹配的订阅者。"""
        handlers = self._get_matching_handlers(event.event_type)
        for h in handlers:
            try:
                h(event)
            except Exception:
                # 一个订阅者崩溃不影响其他订阅者
                pass
        self._record(event)

    def emit_async(self, event: Event) -> None:
        """异步发射（通过 threading.Thread 非阻塞）。

        注：真正的 async/await 版本可在未来扩展；当前提供
        threading 实现以保证与现有同步代码兼容。
        """
        import threading
        t = threading.Thread(target=self.emit, args=(event,), daemon=True)
        t.start()

    # ── 历史 ──
    def recent(self, n: int = 20, event_type: str | None = None) -> List[Event]:
        """获取最近 N 条历史事件，可过滤类型。"""
        with self._lock:
            if event_type is None:
                return list(self._history[-n:])
            return [e for e in self._history
                    if _event_matches(e.event_type, event_type)][-n:]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # ── 内部 ──
    def _get_matching_handlers(self, event_type: str) -> List[EventHandler]:
        with self._lock:
            result: List[EventHandler] = []
            for pattern, handlers in self._subscribers.items():
                if _event_matches(event_type, pattern):
                    result.extend(handlers)
            return result

    def _record(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]


# ─── 通配符匹配 ───────────────────────────────────────────────────

def _event_matches(event_type: str, pattern: str) -> bool:
    """通配符匹配：'agent.registered' 匹配 'agent.*' 和 '*'。"""
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        return event_type.startswith(pattern[:-1])
    return event_type == pattern


# ─── 内核事件发射工具 ─────────────────────────────────────────────

class EventEmitter:
    """混入工具：给内核或层类增加事件发射能力。

    用法：
        class MyService(EventEmitter):
            def __init__(self):
                super().__init__()  # self.events = EventBus()

            def do_something(self):
                self.emit(SystemEvent.AGENT_STARTED, source="my_service",
                           payload={"agent_id": "a1"})
    """

    def __init__(self, event_bus: EventBus | None = None):
        self.events = event_bus or EventBus()

    def emit(self, event_type: str, source: str = "system",
             payload: Optional[Dict[str, Any]] = None,
             trace_id: str = "", sync: bool = True) -> None:
        ev = Event(event_type=event_type, source=source,
                   payload=payload or {}, trace_id=trace_id)
        if sync:
            self.events.emit(ev)
        else:
            self.events.emit_async(ev)


__all__ = [
    "Event",
    "EventBus",
    "EventEmitter",
    "EventHandler",
    "SystemEvent",
]
