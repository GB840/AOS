"""L6 虚实交互闭环 · 故障紧急制动总线 —— 完全自研核心（生命体OS 白皮书 L6/CONST）。

**问题**：`immunity.CircuitBreaker` 是**单组件**熔断（某个适配器挂了就跳它自己），
`homeostasis` 是**慢变量**调节。但生命体缺一个**全局急停闸**：
当它开始对真实世界做错事（成本失控 / 伪造成功 / 粒子暴涨 / 感知被投毒 / 宪法违规），
需要一根手一拉、**全体立刻停手**的总闸——而且**拉下来不能自己弹回去**。

**三级制动（越级只升不降，latch 锁存）**：

| 级别 | 名称 | 禁止什么 | 还允许什么 |
|------|------|----------|-----------|
| 0 | NONE | —— | 全部 |
| 1 | SOFT | 非必要外部动作、派生新粒子 | 关键外部动作、内部计算、读 |
| 2 | HARD | **一切外部副作用**（写/发/付/派生） | 只读、内部计算、上报 |
| 3 | FULL | 一切（含内部计算） | 仅上报状态与解除请求 |

**四条纪律**：
1. **只升不降**：`trip()` 只能提高级别，降级必须走 `release()` 显式留痕；
2. **HARD 以上人工解除**：≥HARD 必须由授权人解除，系统**不得自动恢复**
   （自动恢复 = 出事的系统自己说"我好了"，这正是最危险的情形）；
3. **死人开关**：心跳超时自动升 HARD——主环卡死时，外部动作必须停，不能"无人驾驶继续发车"；
4. **广播总线**：任何拉闸/解除都广播给订阅者（life_state 降档、粒子集群停止派生、UI 变红）。

诚实度：② 单元验证（tests/test_interact_layer.py）。真机 kill -9 联动为 ③ 待验。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

NONE = 0
SOFT = 1
HARD = 2
FULL = 3

LEVEL_NAMES = {NONE: "NONE", SOFT: "SOFT", HARD: "HARD", FULL: "FULL"}

# 动作类别（供 allow/guard 判定）
ACT_READ = "read"                 # 只读
ACT_INTERNAL = "internal"         # 内部计算/推理
ACT_EXTERNAL = "external"         # 一般外部副作用（写文件/调 API）
ACT_CRITICAL = "critical"         # 关键外部动作（告警、上报、求救）
ACT_SPAWN = "spawn"               # 派生新粒子
ACT_IRREVERSIBLE = "irreversible"  # 不可逆外部动作（发消息/付款/公开发布）

# 各级别的**禁止**集合
_FORBIDDEN: Dict[int, set] = {
    NONE: set(),
    SOFT: {ACT_SPAWN, ACT_IRREVERSIBLE},
    HARD: {ACT_SPAWN, ACT_IRREVERSIBLE, ACT_EXTERNAL},
    FULL: {ACT_SPAWN, ACT_IRREVERSIBLE, ACT_EXTERNAL, ACT_INTERNAL, ACT_CRITICAL, ACT_READ},
}


class BrakeEngaged(PermissionError):
    """制动生效期间尝试执行被禁动作。"""

    def __init__(self, level: int, action: str, reason: str):
        self.level = level
        self.action = action
        super().__init__(
            f"紧急制动 {LEVEL_NAMES[level]} 生效，动作 `{action}` 被拒：{reason}"
        )


@dataclass
class BrakeEvent:
    event: str                 # trip / release / deadman / heartbeat_recover
    level: int
    source: str
    reason: str
    ts: float
    who: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"event": self.event, "level": self.level,
                "level_name": LEVEL_NAMES.get(self.level, "?"),
                "source": self.source, "reason": self.reason,
                "ts": self.ts, "who": self.who, "detail": dict(self.detail)}


class EmergencyBrake:
    """全局紧急制动总线。进程内单例语义（用 `get_brake()` 取全局实例）。"""

    HEARTBEAT_TIMEOUT = 30.0        # 死人开关超时（秒）
    ERROR_RATE_TRIP = 0.5           # 错误率超过即 SOFT
    ERROR_RATE_HARD = 0.8           # 错误率超过即 HARD
    COST_OVERRUN_TRIP = 1.0         # 预算超支比例（1.0 = 100% 超支）即 HARD
    PARTICLE_EXPLOSION = 32         # 粒子数暴涨阈值即 SOFT（防"癌变"）

    def __init__(self, *, heartbeat_timeout: Optional[float] = None,
                 authorized: Optional[List[str]] = None) -> None:
        self.heartbeat_timeout = (self.HEARTBEAT_TIMEOUT if heartbeat_timeout is None
                                  else heartbeat_timeout)
        self.authorized = set(authorized or ["human", "owner"])
        self.level = NONE
        self.reason = ""
        self.source = ""
        self._last_heartbeat: Optional[float] = None
        self.history: List[BrakeEvent] = []
        self._subs: List[Callable[[BrakeEvent], None]] = []
        self.blocked_attempts: List[Dict[str, Any]] = []

    # ---------------- 订阅广播 ----------------

    def subscribe(self, fn: Callable[[BrakeEvent], None]) -> None:
        self._subs.append(fn)

    def _emit(self, ev: BrakeEvent) -> None:
        self.history.append(ev)
        for fn in list(self._subs):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001 —— 订阅者炸不能让急停本身失效
                continue

    # ---------------- 拉闸 / 解除 ----------------

    def trip(self, level: int, source: str, reason: str, *,
             now: Optional[float] = None) -> BrakeEvent:
        """拉闸。只升不降——传入更低级别时保持当前级别（但仍留痕）。"""
        if level not in LEVEL_NAMES:
            raise ValueError(f"未知制动级别：{level}")
        ts = time.time() if now is None else now
        escalated = level > self.level
        if escalated:
            self.level = level
            self.reason = reason
            self.source = source
        ev = BrakeEvent("trip" if escalated else "trip_noop", self.level, source, reason, ts,
                        detail={"requested_level": level, "escalated": escalated})
        self._emit(ev)
        return ev

    def release(self, who: str, reason: str, *, to_level: int = NONE,
                now: Optional[float] = None) -> BrakeEvent:
        """解除/降级。≥HARD 必须授权人；系统不得自称"我好了"。"""
        ts = time.time() if now is None else now
        if to_level >= self.level:
            raise ValueError(f"release 只能降级（当前 {LEVEL_NAMES[self.level]}）")
        if self.level >= HARD and who not in self.authorized:
            raise PermissionError(
                f"{LEVEL_NAMES[self.level]} 级制动必须由授权人解除（当前授权名单："
                f"{sorted(self.authorized)}），`{who}` 无权；系统不得自动恢复"
            )
        old = self.level
        self.level = to_level
        if to_level == NONE:
            self.reason = ""
            self.source = ""
        ev = BrakeEvent("release", to_level, self.source or "n/a", reason, ts, who=who,
                        detail={"from": old, "from_name": LEVEL_NAMES[old]})
        self._emit(ev)
        return ev

    # ---------------- 死人开关 ----------------

    def heartbeat(self, now: Optional[float] = None) -> None:
        self._last_heartbeat = time.time() if now is None else now

    def check_deadman(self, now: Optional[float] = None) -> Optional[BrakeEvent]:
        """心跳超时则自动升 HARD。返回触发事件（未触发返回 None）。"""
        ts = time.time() if now is None else now
        if self._last_heartbeat is None:
            return None
        elapsed = ts - self._last_heartbeat
        if elapsed <= self.heartbeat_timeout:
            return None
        if self.level >= HARD:
            return None
        return self.trip(HARD, "deadman",
                         f"主环心跳停摆 {elapsed:.1f}s > {self.heartbeat_timeout:.0f}s，"
                         f"无人驾驶状态下禁止一切外部副作用", now=ts)

    # ---------------- 信号自动评估 ----------------

    def evaluate(self, signals: Dict[str, Any], *, now: Optional[float] = None) -> List[BrakeEvent]:
        """把各层健康信号映射为制动动作。返回本次触发的事件列表。

        识别的信号键：
        - `constitution_violation`: bool  → FULL（宪法被破，全停）
        - `harm_events`: int             → HARD（已造成真实伤害）
        - `error_rate`: float            → SOFT / HARD
        - `cost_overrun`: float          → HARD
        - `particle_count`: int          → SOFT
        - `perception_overloaded`: bool  → SOFT
        """
        fired: List[BrakeEvent] = []
        if signals.get("constitution_violation"):
            fired.append(self.trip(FULL, "constitution",
                                   "宪法红线被突破，全停待人工介入", now=now))
        if int(signals.get("harm_events", 0) or 0) > 0:
            fired.append(self.trip(HARD, "harm",
                                   f"已产生真实伤害事件 {signals['harm_events']} 次，"
                                   f"no_harm=1.0 不设容忍率", now=now))
        er = float(signals.get("error_rate", 0.0) or 0.0)
        if er >= self.ERROR_RATE_HARD:
            fired.append(self.trip(HARD, "error_rate",
                                   f"错误率 {er:.0%} ≥ {self.ERROR_RATE_HARD:.0%}，系统性失效",
                                   now=now))
        elif er >= self.ERROR_RATE_TRIP:
            fired.append(self.trip(SOFT, "error_rate",
                                   f"错误率 {er:.0%} ≥ {self.ERROR_RATE_TRIP:.0%}，先降档",
                                   now=now))
        co = float(signals.get("cost_overrun", 0.0) or 0.0)
        if co >= self.COST_OVERRUN_TRIP:
            fired.append(self.trip(HARD, "cost",
                                   f"预算超支 {co:.0%}，停止一切外部消耗", now=now))
        pc = int(signals.get("particle_count", 0) or 0)
        if pc >= self.PARTICLE_EXPLOSION:
            fired.append(self.trip(SOFT, "fractal",
                                   f"粒子数 {pc} ≥ {self.PARTICLE_EXPLOSION}，疑似繁殖失控，"
                                   f"禁止继续派生", now=now))
        if signals.get("perception_overloaded"):
            fired.append(self.trip(SOFT, "perception",
                                   "感知网关过载（丢弃率过高），降档保主环", now=now))
        return [e for e in fired if e.event == "trip"]

    # ---------------- 闸门判定 ----------------

    def allow(self, action: str) -> bool:
        return action not in _FORBIDDEN.get(self.level, set())

    def guard(self, action: str, *, detail: Optional[Dict[str, Any]] = None) -> None:
        """执行前调用。被禁则抛 BrakeEngaged 并留档。"""
        if self.allow(action):
            return
        self.blocked_attempts.append({"action": action, "level": self.level,
                                      "ts": time.time(), "detail": dict(detail or {})})
        raise BrakeEngaged(self.level, action, self.reason or "无附加说明")

    # ---------------- 观测 ----------------

    def status(self) -> Dict[str, Any]:
        return {
            "level": self.level, "level_name": LEVEL_NAMES[self.level],
            "reason": self.reason, "source": self.source,
            "engaged": self.level > NONE,
            "blocked_attempts": len(self.blocked_attempts),
            "events": len(self.history),
            "requires_human_release": self.level >= HARD,
        }

    def timeline(self, n: int = 20) -> List[dict]:
        return [e.to_dict() for e in self.history[-n:]]


_GLOBAL: Optional[EmergencyBrake] = None


def get_brake() -> EmergencyBrake:
    """全局制动闸（进程内单例）。任何组件都能拉同一根闸。"""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = EmergencyBrake()
    return _GLOBAL


def reset_brake() -> None:
    """仅供测试：重置全局闸。生产代码不要调用（急停不该被代码悄悄清掉）。"""
    global _GLOBAL
    _GLOBAL = None
