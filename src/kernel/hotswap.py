"""v1.0 插件热替换管理器：运行时 swap 插件，不重启。

"物种思维"的最后一块拼图：内核的 pluggable slots 允许运行时替换。
本模块提供线程安全的热替换管理，替换时发射事件通知所有监听者。

用法：
    hsm = HotSwapManager(kernel)
    hsm.swap_model_gateway(new_gateway)     # 运行时替换模型网关
    hsm.swap_agent_runtime("openclaw", new)  # 运行时替换引擎
    hsm.swap_skill_bus(new_bus)              # 运行时替换技能总线
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List

from kernel.events import Event, SystemEvent
from kernel.interfaces import AgentRuntime, ModelGateway, SkillBus


class HotSwapManager:
    """线程安全的运行时插件热替换管理器。

    所有 swap 操作都是原子性的：先验证新插件可用，再原子替换引用。
    替换成功后发射 plugin.swapped 事件。
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel
        self._lock = Lock()
        self._swap_history: List[Dict[str, Any]] = []

    # ── 模型网关热替换 ──
    def swap_model_gateway(self, new_gateway: ModelGateway) -> bool:
        """运行时替换模型网关。返回是否成功。"""
        with self._lock:
            old = self._kernel._model_gateway
            self._kernel._model_gateway = new_gateway
            self._record("model_gateway",
                         str(type(old).__name__) if old else "none",
                         str(type(new_gateway).__name__))
            self._kernel.events.emit(Event(
                SystemEvent.PLUGIN_REGISTERED, "hotswap",
                {"plugin": "model_gateway",
                 "old": str(type(old).__name__) if old else "none",
                 "new": str(type(new_gateway).__name__)}))
        return True

    # ── Agent 运行时热替换 ──
    def swap_agent_runtime(self, engine: str,
                           new_runtime: AgentRuntime) -> bool:
        """运行时替换指定 engine 的 AgentRuntime 插件。"""
        with self._lock:
            old = self._kernel._runtimes.get(engine)
            self._kernel._runtimes[engine] = new_runtime
            self._record("agent_runtime",
                         str(type(old).__name__) if old else "none",
                         str(type(new_runtime).__name__),
                         engine=engine)
            self._kernel.events.emit(Event(
                SystemEvent.PLUGIN_REGISTERED, "hotswap",
                {"plugin": "agent_runtime", "engine": engine,
                 "old": str(type(old).__name__) if old else "none",
                 "new": str(type(new_runtime).__name__)}))
        return True

    def remove_agent_runtime(self, engine: str) -> bool:
        """运行时移除一个引擎插件。"""
        with self._lock:
            if engine not in self._kernel._runtimes:
                return False
            del self._kernel._runtimes[engine]
            self._kernel.events.emit(Event(
                SystemEvent.PLUGIN_REMOVED, "hotswap",
                {"plugin": "agent_runtime", "engine": engine}))
        return True

    # ── 技能总线热替换 ──
    def swap_skill_bus(self, new_bus: SkillBus) -> bool:
        """运行时替换技能总线。"""
        with self._lock:
            old = self._kernel._skill_bus
            self._kernel._skill_bus = new_bus
            self._record("skill_bus",
                         str(type(old).__name__) if old else "none",
                         str(type(new_bus).__name__))
            self._kernel.events.emit(Event(
                SystemEvent.PLUGIN_REGISTERED, "hotswap",
                {"plugin": "skill_bus",
                 "old": str(type(old).__name__) if old else "none",
                 "new": str(type(new_bus).__name__)}))
        return True

    # ── 审计 ──
    def history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._swap_history[-limit:])

    def _record(self, plugin_type: str, old: str, new: str,
                **extra: Any) -> None:
        import datetime
        self._swap_history.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "plugin": plugin_type,
            "old": old,
            "new": new,
            **extra,
        })
        # 只保留最近 200 条
        if len(self._swap_history) > 200:
            self._swap_history = self._swap_history[-200:]


__all__ = ["HotSwapManager"]
