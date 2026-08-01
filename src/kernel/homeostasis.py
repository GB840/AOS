"""L2E 体感稳态系统 —— 完全自研核心（生命体OS 白皮书 L2E）。

生命体六判据之「有稳态」的工程实现：负反馈控制器。
它盯住若干**体征（vital）**，一旦偏离设定点（setpoint）超出死区，
就产出**纠偏动作**并逐步加大力度，直到回到区间；持续失稳则升级为告警/休眠。

与 L0 life_state 的分工：
- life_state 是「我现在什么状态」（状态量）；
- homeostasis 是「状态偏了怎么自动拉回来」（控制律）。

刻意不引入 PID 全套（避免过度设计）：用**带死区的比例控制 + 失稳计数**，
简单、可解释、可单测——符合宪法「白盒才可进化」。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Vital:
    """一个受控体征。"""

    name: str
    setpoint: float                  # 目标值
    deadband: float = 0.05           # 死区：偏差在此内不动作（防抖）
    low: float = 0.0                 # 物理下界
    high: float = 1.0                # 物理上界
    gain: float = 1.0                # 比例增益
    higher_is_better: bool = True    # True: 低于设定点才算「坏」（如 energy）
    #                                  False: 高于设定点才算「坏」（如 debt/温度）

    def deviation(self, value: float) -> float:
        """返回「坏的方向」上的偏差，正数=偏坏，负数/0=没问题。"""
        d = (self.setpoint - value) if self.higher_is_better else (value - self.setpoint)
        return d if d > self.deadband else 0.0


@dataclass
class Correction:
    vital: str
    deviation: float
    effort: float                    # 0..1 纠偏力度
    action: str
    severity: str                    # ok / mild / severe / critical

    def to_dict(self) -> dict:
        return {"vital": self.vital, "deviation": round(self.deviation, 4),
                "effort": round(self.effort, 4), "action": self.action,
                "severity": self.severity}


# 体征 → 纠偏动作映射（可扩展，但默认给出可直接执行的动作串）
DEFAULT_ACTIONS: Dict[str, str] = {
    "energy": "rest_cycle",           # 进入 rest（交给 rhythm.RhythmScheduler）
    "focus": "reset_focus",           # 重置专注（清上下文碎片）
    "mood": "seek_easy_win",          # 先做一件容易成的事，重建正反馈
    "debt": "pay_debt_first",         # 优先清偿失败任务
    "error_rate": "reduce_concurrency",
    "latency_ms": "switch_engine_tier:light",
    "temperature": "throttle_compute",
}


class Homeostasis:
    """稳态控制器：注册体征 → 每 tick 评估 → 输出纠偏动作。"""

    SEVERITY_STEPS = ((0.5, "critical"), (0.25, "severe"), (0.0, "mild"))

    def __init__(self, instability_threshold: int = 3):
        self._vitals: Dict[str, Vital] = {}
        self._streak: Dict[str, int] = {}       # 连续失稳次数
        self.instability_threshold = instability_threshold
        self.history: List[dict] = []

    # ---------------------------------------------------------------- 注册
    def register(self, vital: Vital) -> None:
        self._vitals[vital.name] = vital
        self._streak.setdefault(vital.name, 0)

    @classmethod
    def with_defaults(cls) -> "Homeostasis":
        """AOS 默认体征组：直接对齐 L0 life_state 四维 + 两个运行时指标。"""
        h = cls()
        h.register(Vital("energy", setpoint=0.5, deadband=0.05, higher_is_better=True))
        h.register(Vital("focus", setpoint=0.5, deadband=0.05, higher_is_better=True))
        h.register(Vital("mood", setpoint=0.35, deadband=0.05, higher_is_better=True))
        h.register(Vital("debt", setpoint=1.0, deadband=0.2, high=5.0,
                         higher_is_better=False, gain=0.4))
        h.register(Vital("error_rate", setpoint=0.2, deadband=0.05,
                         higher_is_better=False))
        return h

    # ---------------------------------------------------------------- 评估
    def tick(self, readings: Dict[str, float]) -> List[Correction]:
        """输入一组体征读数，输出需要执行的纠偏动作（按力度降序）。"""
        out: List[Correction] = []
        for name, v in self._vitals.items():
            if name not in readings:
                continue
            dev = v.deviation(float(readings[name]))
            if dev <= 0:
                self._streak[name] = 0
                continue
            self._streak[name] += 1
            span = max(1e-6, (v.high - v.low))
            effort = min(1.0, (dev / span) * v.gain)
            sev = self._severity(dev / span)
            if self._streak[name] >= self.instability_threshold:
                sev = "critical"          # 反复失稳直接升级
                effort = min(1.0, effort + 0.3)
            out.append(Correction(name, dev, effort,
                                  DEFAULT_ACTIONS.get(name, "investigate"), sev))
        out.sort(key=lambda c: c.effort, reverse=True)
        self.history.append({"ts": time.time(),
                             "corrections": [c.to_dict() for c in out]})
        return out

    def _severity(self, ratio: float) -> str:
        for thr, label in self.SEVERITY_STEPS:
            if ratio >= thr:
                return label
        return "ok"

    # ---------------------------------------------------------------- 状态
    def is_stable(self) -> bool:
        return all(s == 0 for s in self._streak.values())

    def unstable_vitals(self) -> List[str]:
        return [k for k, v in self._streak.items() if v > 0]

    def should_hibernate(self) -> bool:
        """任一体征连续失稳超过阈值 2 倍 → 建议深度休眠（交给 rhythm）。"""
        return any(v >= self.instability_threshold * 2 for v in self._streak.values())


__all__ = ["Homeostasis", "Vital", "Correction", "DEFAULT_ACTIONS"]
