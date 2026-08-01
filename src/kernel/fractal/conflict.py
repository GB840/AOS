"""L2G 粒子冲突协调协议 —— 完全自研核心（生命体OS 白皮书 L2G）。

分形粒子（L7 FractalSpawner 派生的子体）会并发争抢同一资源：
同一个文件、同一个端口、同一笔预算、同一个外部账号。
本协议保证：**要么有序，要么明确失败，绝不静默互踩**。

三段式协议（刻意简单、可单测、无外部依赖）：
1. **租约（Lease）**：资源以租约独占，带 TTL，过期自动回收（防死锁）。
2. **优先级仲裁**：同代按 priority，跨代**父代永远优先于子代**（避免子体饿死父体）。
3. **冲突升级**：连续抢占失败 N 次 → 上报 GrowthGuard/人工，而不是无限重试。

与 L7 GrowthGuard 的分工：GrowthGuard 管「能不能派生/能不能做危险动作」，
本模块管「已经存在的粒子之间怎么不打架」。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DEFAULT_TTL = 30.0            # 秒；租约默认存活时间
MAX_PREEMPT_FAILS = 3         # 连续抢占失败上限 → 升级上报


class ConflictEscalation(RuntimeError):
    """冲突反复无法自动化解，需上报（GrowthGuard / 人工）。"""


@dataclass
class Lease:
    resource: str
    holder: str                 # 粒子 id
    generation: int             # 粒子代数（0=父体）
    priority: int               # 越大越优先
    expires_at: float
    acquired_at: float = field(default_factory=time.time)

    def expired(self, now: Optional[float] = None) -> bool:
        return ((time.time() if now is None else now)) >= self.expires_at

    def to_dict(self) -> dict:
        return {"resource": self.resource, "holder": self.holder,
                "generation": self.generation, "priority": self.priority,
                "expires_at": self.expires_at, "acquired_at": self.acquired_at}


@dataclass
class ArbitrationResult:
    granted: bool
    resource: str
    holder: str
    reason: str
    preempted: Optional[str] = None    # 被抢占者 id

    def to_dict(self) -> dict:
        return {"granted": self.granted, "resource": self.resource,
                "holder": self.holder, "reason": self.reason,
                "preempted": self.preempted}


class ConflictCoordinator:
    """粒子冲突协调器。"""

    def __init__(self, default_ttl: float = DEFAULT_TTL,
                 max_preempt_fails: int = MAX_PREEMPT_FAILS):
        self.default_ttl = default_ttl
        self.max_preempt_fails = max_preempt_fails
        self._leases: Dict[str, Lease] = {}
        self._fails: Dict[Tuple[str, str], int] = {}     # (holder, resource) -> 连续失败
        self.log: List[dict] = []

    # ---------------------------------------------------------------- 内部
    def _reap(self, now: Optional[float] = None) -> List[str]:
        """回收过期租约（防死锁：持有者崩溃也不会永久占住）。"""
        now = (time.time() if now is None else now)
        dead = [r for r, l in self._leases.items() if l.expired(now)]
        for r in dead:
            self._leases.pop(r, None)
        return dead

    def _wins(self, challenger_gen: int, challenger_pri: int, incumbent: Lease) -> bool:
        """仲裁规则：父代（代数小）优先；同代比 priority；再平局则在位者胜（稳定性）。"""
        if challenger_gen != incumbent.generation:
            return challenger_gen < incumbent.generation
        return challenger_pri > incumbent.priority

    # ---------------------------------------------------------------- 申请
    def acquire(self, resource: str, holder: str, *, generation: int = 0,
                priority: int = 0, ttl: Optional[float] = None,
                now: Optional[float] = None) -> ArbitrationResult:
        now = (time.time() if now is None else now)
        self._reap(now)
        ttl = self.default_ttl if ttl is None else ttl
        cur = self._leases.get(resource)

        if cur is None:
            self._leases[resource] = Lease(resource, holder, generation, priority, now + ttl, now)
            self._fails.pop((holder, resource), None)
            return self._done(ArbitrationResult(True, resource, holder, "资源空闲，直接授予"))

        if cur.holder == holder:           # 续租
            cur.expires_at = now + ttl
            return self._done(ArbitrationResult(True, resource, holder, "续租成功"))

        if self._wins(generation, priority, cur):
            self._leases[resource] = Lease(resource, holder, generation, priority, now + ttl, now)
            self._fails.pop((holder, resource), None)
            return self._done(ArbitrationResult(
                True, resource, holder,
                f"抢占成功（gen {generation}<{cur.generation} 或 pri {priority}>{cur.priority}）",
                preempted=cur.holder))

        key = (holder, resource)
        self._fails[key] = self._fails.get(key, 0) + 1
        if self._fails[key] >= self.max_preempt_fails:
            self._done(ArbitrationResult(False, resource, holder,
                                         f"连续 {self._fails[key]} 次抢占失败，升级上报"))
            raise ConflictEscalation(
                f"粒子 {holder} 对资源 {resource} 连续 {self._fails[key]} 次争用失败；"
                f"当前持有者 {cur.holder}(gen={cur.generation},pri={cur.priority})，需人工/守卫介入"
            )
        return self._done(ArbitrationResult(
            False, resource, holder,
            f"让位于 {cur.holder}（gen={cur.generation},pri={cur.priority}）"))

    def release(self, resource: str, holder: str) -> bool:
        cur = self._leases.get(resource)
        if cur and cur.holder == holder:
            self._leases.pop(resource, None)
            return True
        return False

    def release_all(self, holder: str) -> int:
        targets = [r for r, l in self._leases.items() if l.holder == holder]
        for r in targets:
            self._leases.pop(r, None)
        return len(targets)

    # ---------------------------------------------------------------- 查询
    def holder_of(self, resource: str, now: Optional[float] = None) -> Optional[str]:
        self._reap(now)
        l = self._leases.get(resource)
        return l.holder if l else None

    def snapshot(self) -> List[dict]:
        return [l.to_dict() for l in self._leases.values()]

    def _done(self, r: ArbitrationResult) -> ArbitrationResult:
        self.log.append({"ts": time.time(), **r.to_dict()})
        return r


__all__ = ["ConflictCoordinator", "Lease", "ArbitrationResult",
           "ConflictEscalation", "DEFAULT_TTL", "MAX_PREEMPT_FAILS"]
