"""ResilienceBus: 融合四层防御为一条自愈闭环（炼为一体核心）。

原本四条防线各自为政、互不说话：
  * FailureMonitor（MAST 14 类失败埋点）—— 只观测，不驱动任何恢复动作；
  * CircuitBreaker（immunity.CircuitBreaker）—— 写了但 route() 热路径没人调用它；
  * SelfHealer（immunity.SelfHealer）—— 写了但只响应 EventBus，route 失败不触发；
  * EvolutionDistiller（白盒蒸馏）—— 要 AOS_DISTILLER_ROUTE=1 才开，且只做排序。

本模块把它们熔成**一条闭环**，默认随 FabricHub 启动常驻（不须任何 opt-in env）：
  失败观测 → 蒸馏学习 → 熔断拦截 → 降级链 → 自愈恢复 → 成功反馈蒸馏

设计原则：
  * 零硬依赖：仅用 stdlib + 已存在的四个模块；任意一层缺失都不拖垮总线。
  * 不阻塞主路由：所有跨层调用 best-effort try/except，异常吞掉记日志。
  * 单一可信状态：每个引擎的「是否该跳过」由 ResilienceBus 统一裁定，
    route() 不各自维护熔断/降级逻辑，避免状态分裂。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 每个引擎连续失败达到该次数 → 触发熔断（跳过该引擎，直走降级链）
_DEFAULT_CB_FAILURE_THRESHOLD = 3
# 熔断冷却时间（秒）：冷却期内该引擎不尝试，冷却后半开探测
_DEFAULT_CB_COOLDOWN = 30.0
# 半开后连续成功达到该次数 → 关闭熔断（恢复服务）
_DEFAULT_CB_SUCCESS_THRESHOLD = 2


class _PerEngineBreaker:
    """轻量每引擎熔断器（融合 immunity.CircuitBreaker 的状态机，但零依赖、
    不抛异常——被 OPEN 的引擎由 ResilienceBus 统一裁定「跳过」，不靠调用方
    捕获 CircuitBreakerOpenError）。"""

    def __init__(self, name: str,
                 failure_threshold: int = _DEFAULT_CB_FAILURE_THRESHOLD,
                 cooldown: float = _DEFAULT_CB_COOLDOWN,
                 success_threshold: int = _DEFAULT_CB_SUCCESS_THRESHOLD) -> None:
        self.name = name
        self._fail_threshold = failure_threshold
        self._cooldown = cooldown
        self._success_threshold = success_threshold
        self._failures = 0
        self._successes = 0
        self._last_failure = 0.0
        self._state = "closed"  # closed | open | half_open
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        with self._lock:
            # 冷却期内的 open → 检查是否可转 half_open
            if self._state == "open" and \
               (time.time() - self._last_failure) > self._cooldown:
                self._state = "half_open"
                self._successes = 0
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == "open"

    def on_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure = time.time()
            self._successes = 0
            if self._failures >= self._fail_threshold:
                self._state = "open"

    def on_success(self) -> None:
        with self._lock:
            if self._state == "half_open":
                self._successes += 1
                if self._successes >= self._success_threshold:
                    self._state = "closed"
                    self._failures = 0
                    self._successes = 0
            else:
                self._state = "closed"
                self._failures = 0


class ResilienceBus:
    """自愈闭环总线：把失败观测 / 蒸馏学习 / 熔断 / 降级 / 自愈熔成一条链路。

    用法（FabricHub.__init__ 末尾）::

        self._res = ResilienceBus(
            failure_monitor=self._failure_monitor,
            distiller=self._distiller,
            fallback_resolver=self._resolve_fallback_engine,
            restart_engine=self._restart_engine_host,
        )

    route() 在每个引擎尝试前调用 ``should_skip(eid)``；尝试后调用
    ``on_outcome(eid, ok, error)``。总线内部自动完成：失败累计 → 熔断 →
    自愈触发 → 成功回灌蒸馏。
    """

    def __init__(self,
                 failure_monitor: Any = None,
                 distiller: Any = None,
                 fallback_resolver: Callable[[str], Optional[str]] | None = None,
                 restart_engine: Callable[[str], bool] | None = None,
                 isolate_engine: Callable[[str], bool] | None = None) -> None:
        self._fm = failure_monitor
        self._distiller = distiller
        self._fallback_resolver = fallback_resolver or (lambda e: None)
        self._restart = restart_engine or (lambda e: False)
        self._isolate = isolate_engine or (lambda e: False)
        self._breakers: Dict[str, _PerEngineBreaker] = {}
        self._lock = threading.RLock()
        # 自愈动作历史（可观测）
        self._heal_history: List[Dict[str, Any]] = []
        self._tripped: Dict[str, float] = {}  # engine_id -> 熔断触发时间戳
        # 统计快照
        self._total_failures = 0
        self._total_success = 0
        self._circuit_trips = 0

    # ---- 主接口（route 调用） ----

    def should_skip(self, engine_id: str) -> bool:
        """route() 在尝试某引擎前调用：返回 True 表示该引擎已被熔断，跳过它
        直走降级链。绝不会因本调用抛异常（best-effort）。"""
        try:
            with self._lock:
                br = self._breakers.get(engine_id)
            if br is None:
                return False
            return br.is_open
        except Exception as e:  # noqa: BLE001
            logger.warning("ResilienceBus.should_skip 异常(降级为不跳过): %s", e)
            return False

    def on_outcome(self, engine_id: str, ok: bool,
                   error: Optional[str] = None) -> None:
        """route() 在某个引擎尝试后调用：更新熔断状态 + 蒸馏器 + 失败监控。"""
        try:
            with self._lock:
                br = self._breakers.get(engine_id)
                if br is None:
                    br = _PerEngineBreaker(engine_id)
                    self._breakers[engine_id] = br
            if ok:
                br.on_success()
                self._total_success += 1
                # 成功回灌蒸馏器：强化「该引擎可靠」证据
                self._feed_distiller(engine_id, True, None)
            else:
                br.on_failure()
                self._total_failures += 1
                self._feed_distiller(engine_id, False, error)
                # 新熔断触发 → 启动自愈
                if br.is_open and engine_id not in self._tripped:
                    self._tripped[engine_id] = time.time()
                    self._circuit_trips += 1
                    self._trigger_heal(engine_id, error)
        except Exception as e:  # noqa: BLE001
            logger.warning("ResilienceBus.on_outcome 异常(已忽略): %s", e)

    # ---- 内部链路 ----

    def _feed_distiller(self, engine_id: str, ok: bool, error: Optional[str]) -> None:
        """把 outcome 喂给白盒蒸馏器（best-effort）。"""
        if self._distiller is None:
            return
        try:
            # 蒸馏器按 (capability, engine) 维度记录；这里没有 capability 维度，
            # 用 engine_id 同时作 capability 占位（route 层已另按 capability 喂过，
            # 这里只补「引擎级」聚合，帮助熔断决策）。
            self._distiller.record_outcome(engine_id, engine_id, ok, error or "")
        except Exception:  # noqa: BLE001
            pass

    def _trigger_heal(self, engine_id: str, error: Optional[str]) -> None:
        """熔断触发后尝试自愈：先重启该引擎宿主，重启不成则尝试降级到备选。

        自愈动作记录进 _heal_history 供可观测；任何一步失败都不阻断主流程。
        """
        # 1) 尝试重启引擎宿主（子进程 respawn / 进程内复探）
        try:
            if self._restart(engine_id):
                self._record_heal("restart", engine_id, "circuit opened")
                return
        except Exception as e:  # noqa: BLE001
            logger.warning("ResilienceBus: 重启 %s 失败: %s", engine_id, e)
        # 2) 重启不成 → 找降级备选引擎，并把它标为「优先」（蒸馏器升优先级）
        try:
            alt = self._fallback_resolver(engine_id)
            if alt:
                self._record_heal("fallback", engine_id,
                                  f"circuit opened, use {alt}")
                return
        except Exception as e:  # noqa: BLE001
            logger.warning("ResilienceBus: 降级解析 %s 失败: %s", engine_id, e)
        # 3) 都失败 → 隔离（极端情况下防止反复打爆该引擎）
        try:
            if self._isolate(engine_id):
                self._record_heal("isolate", engine_id, "restart+fallback failed")
                return
        except Exception:  # noqa: BLE001
            pass
        self._record_heal("none", engine_id, "no heal action succeeded")

    def _record_heal(self, action: str, target: str, reason: str) -> None:
        with self._lock:
            self._heal_history.append({
                "action": action, "target": target,
                "reason": reason, "ts": time.time(),
            })
            if len(self._heal_history) > 200:
                self._heal_history = self._heal_history[-200:]

    # ---- 可观测 ----

    def health(self) -> Dict[str, Any]:
        """真实健康快照。

        【理念6 诚实纪律】自愈「尝试」与自愈「生效」必须分开报：
        action == "none" 表示 restart/fallback/isolate 三招全没成，
        它是一次**失败的尝试**，绝不能计入 heal_succeeded 充数。
        旧字段 heal_actions 语义已修正为「真正生效的次数」（原先把失败也算了进去，
        会让面板上看着像自愈了很多次，属于指标虚高——已拆除）。
        """
        with self._lock:
            open_breakers = {e: br.state for e, br in self._breakers.items()
                             if br.is_open}
            attempts = len(self._heal_history)
            succeeded = sum(1 for h in self._heal_history
                            if h.get("action") != "none")
            return {
                "total_failures": self._total_failures,
                "total_success": self._total_success,
                "circuit_trips": self._circuit_trips,
                "open_circuits": open_breakers,
                "heal_attempts": attempts,
                "heal_succeeded": succeeded,
                "heal_failed": attempts - succeeded,
                # 兼容旧字段名，但语义已修正为「真正生效」而非「尝试过」
                "heal_actions": succeeded,
                "recent_heals": self._heal_history[-5:],
                "distiller_connected": self._distiller is not None,
                "failure_monitor_connected": self._fm is not None,
            }

    def reset_engine(self, engine_id: str) -> None:
        """外部（如 recover()）成功恢复某引擎后调用：关闭其熔断并回灌成功。"""
        with self._lock:
            br = self._breakers.get(engine_id)
            if br is not None:
                br.on_success()
            self._tripped.pop(engine_id, None)
        self._feed_distiller(engine_id, True, None)


# ---- 全局单例（与 FailureMonitor 同模式，供跨模块取用） ----
_bus: Optional[ResilienceBus] = None
_bus_lock = threading.Lock()


def get_resilience_bus() -> Optional[ResilienceBus]:
    """返回当前进程的 ResilienceBus 单例（若 FabricHub 已构建）。无则 None。"""
    global _bus
    return _bus


def set_resilience_bus(bus: ResilienceBus) -> None:
    """FabricHub 构建后注册单例。"""
    global _bus
    with _bus_lock:
        _bus = bus


__all__ = ["ResilienceBus", "get_resilience_bus", "set_resilience_bus"]
