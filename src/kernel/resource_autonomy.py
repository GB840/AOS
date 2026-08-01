"""L2D 资源自治调度 —— 完全自研核心（生命体OS 白皮书 L2D）。

生命体判据之「有代谢」：系统必须自己管住自己的资源摄入与消耗，
而不是靠外部人盯着限流。本模块把 L0 生命状态（energy/debt）翻译成
**可执行的资源配额**，并在超支时自主降级而非崩溃。

三条自治规则（硬编码，不可配成「无上限」）：
1. 能量决定总预算：budget = base * energy_factor（energy 越低，总盘子越小）。
2. 债务收紧配额：debt 每 +1，可分配比例 ×0.85（逼系统先还债再扩张）。
3. 超支自动降级：超出配额不是报错，而是返回 degraded 建议（换轻模型/减并发/缩范围）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 资源种类
R_TOKEN, R_CPU_S, R_MEM_MB, R_NET_CALL, R_MONEY = (
    "token", "cpu_s", "mem_mb", "net_call", "money_cny")

DEFAULT_BASE: Dict[str, float] = {
    R_TOKEN: 200_000.0,
    R_CPU_S: 600.0,
    R_MEM_MB: 4096.0,
    R_NET_CALL: 300.0,
    R_MONEY: 5.0,
}


@dataclass
class Allocation:
    resource: str
    granted: float
    requested: float
    degraded: bool
    reason: str

    @property
    def ok(self) -> bool:
        return self.granted > 0

    def to_dict(self) -> dict:
        return {"resource": self.resource, "granted": round(self.granted, 4),
                "requested": round(self.requested, 4),
                "degraded": self.degraded, "reason": self.reason}


@dataclass
class ResourceAutonomy:
    """资源自治调度器：按生命状态自主定预算、自主降级。"""

    base: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BASE))
    used: Dict[str, float] = field(default_factory=dict)
    debt_penalty: float = 0.85       # 每点债务的收紧系数
    min_energy_factor: float = 0.15  # 能量再低也留 15% 保命预算

    # ------------------------------------------------------------- 预算
    def budget(self, resource: str, energy: float, debt: float = 0.0) -> float:
        base = self.base.get(resource, 0.0)
        ef = max(self.min_energy_factor, min(1.0, energy))
        dp = self.debt_penalty ** max(0.0, debt)
        return base * ef * dp

    def remaining(self, resource: str, energy: float, debt: float = 0.0) -> float:
        return max(0.0, self.budget(resource, energy, debt) - self.used.get(resource, 0.0))

    # ------------------------------------------------------------- 申请
    def request(self, resource: str, amount: float,
                energy: float, debt: float = 0.0) -> Allocation:
        """申请资源。够 → 全给；不够 → 给剩余额度并标 degraded（不抛错、不静默超支）。"""
        if resource not in self.base:
            return Allocation(resource, 0.0, amount, True, f"未知资源类型 {resource}")
        left = self.remaining(resource, energy, debt)
        if amount <= left:
            self.used[resource] = self.used.get(resource, 0.0) + amount
            return Allocation(resource, amount, amount, False, "配额充足")
        granted = left
        self.used[resource] = self.used.get(resource, 0.0) + granted
        return Allocation(
            resource, granted, amount, True,
            f"配额不足（剩 {left:.2f} < 申请 {amount:.2f}），自主降级",
        )

    def release(self, resource: str, amount: float) -> None:
        self.used[resource] = max(0.0, self.used.get(resource, 0.0) - amount)

    def reset(self) -> None:
        self.used.clear()

    # ------------------------------------------------------------- 降级建议
    def degrade_plan(self, energy: float, debt: float = 0.0) -> List[str]:
        """资源紧张时给出**具体**降级动作，供 autopilot / opc 直接消费。"""
        plan: List[str] = []
        tok_left_ratio = self._left_ratio(R_TOKEN, energy, debt)
        if energy < 0.3 or tok_left_ratio < 0.2:
            plan.append("switch_engine_tier:light")     # 换轻模型
        if tok_left_ratio < 0.1:
            plan.append("shrink_context:0.5")           # 上下文减半
        if self._left_ratio(R_NET_CALL, energy, debt) < 0.2:
            plan.append("cache_first:true")             # 优先命中缓存
        if debt >= 2.0:
            plan.append("no_new_goals:true")            # 先还债，不开新目标
        if self._left_ratio(R_MONEY, energy, debt) <= 0.0:
            plan.append("hard_stop:money_exhausted")    # 成本硬停
        return plan

    def _left_ratio(self, resource: str, energy: float, debt: float) -> float:
        b = self.budget(resource, energy, debt)
        return 1.0 if b <= 0 else max(0.0, self.remaining(resource, energy, debt) / b)

    def snapshot(self, energy: float, debt: float = 0.0) -> dict:
        return {
            r: {"budget": round(self.budget(r, energy, debt), 3),
                "used": round(self.used.get(r, 0.0), 3),
                "left": round(self.remaining(r, energy, debt), 3)}
            for r in self.base
        }


__all__ = ["ResourceAutonomy", "Allocation", "DEFAULT_BASE",
           "R_TOKEN", "R_CPU_S", "R_MEM_MB", "R_NET_CALL", "R_MONEY"]
