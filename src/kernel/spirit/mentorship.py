"""L4C 师徒协议 —— 完全自研核心（生命体OS 白皮书 L4C）。

新实例/新粒子不该一出生就拿满权限，也不该永远当学徒。
师徒协议给出一条**可考核的放权曲线**：

    观察(observe) → 陪跑(shadow) → 受限自主(limited) → 完全自主(autonomous)

晋级不是靠时间熬，是靠**真实通过的考核（Trial）**：
每级有明确的通过条件（成功率、零重大失误、师傅签字），
达不到就留级；出重大失误直接降级（不是罚站，是防止把权限交给还不会的手）。

这与 L7 GrowthGuard 的分工：GrowthGuard 管「这一次动作要不要审批」，
师徒协议管「这个个体整体上该有多大权限」。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

OBSERVE, SHADOW, LIMITED, AUTONOMOUS = "observe", "shadow", "limited", "autonomous"
STAGES = (OBSERVE, SHADOW, LIMITED, AUTONOMOUS)

# 各阶段权限白名单（与 fractal.particles 的能力原子对齐）
STAGE_CAPS: Dict[str, frozenset] = {
    OBSERVE: frozenset({"read"}),
    SHADOW: frozenset({"read", "net_readonly"}),
    LIMITED: frozenset({"read", "write", "net_readonly"}),
    AUTONOMOUS: frozenset({"read", "write", "net", "spend", "spawn"}),
}

# 晋级门槛：(最少考核次数, 最低成功率, 是否需师傅签字)
PROMOTION_RULES: Dict[str, tuple] = {
    OBSERVE: (3, 0.6, False),
    SHADOW: (5, 0.7, True),
    LIMITED: (8, 0.85, True),
}


@dataclass
class Trial:
    """一次考核记录（必须来自真实任务，不接受自评）。"""

    task: str
    passed: bool
    severe_fault: bool = False        # 重大失误：越权/破坏/谎报
    evidence: str = ""                # 真实证据（stdout/文件路径/退出码）
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"task": self.task, "passed": self.passed,
                "severe_fault": self.severe_fault,
                "evidence": self.evidence[:200], "ts": self.ts}


@dataclass
class Apprentice:
    aid: str
    mentor: Optional[str] = None
    stage: str = OBSERVE
    trials: List[Trial] = field(default_factory=list)
    mentor_signoff: bool = False
    demotions: int = 0

    # ---------------------------------------------------------------- 统计
    def stage_trials(self) -> List[Trial]:
        """只统计当前阶段（晋级/降级后清零重来）的考核。"""
        return self.trials

    def success_rate(self) -> float:
        t = self.stage_trials()
        return 0.0 if not t else round(sum(1 for x in t if x.passed) / len(t), 4)

    def caps(self) -> frozenset:
        return STAGE_CAPS[self.stage]

    def can(self, cap: str) -> bool:
        return cap in self.caps()

    def to_dict(self) -> dict:
        return {"aid": self.aid, "mentor": self.mentor, "stage": self.stage,
                "trials": len(self.trials), "success_rate": self.success_rate(),
                "mentor_signoff": self.mentor_signoff, "demotions": self.demotions,
                "caps": sorted(self.caps())}


class Mentorship:
    """师徒关系管理：收徒、记录考核、晋级/降级、权限查询。"""

    def __init__(self) -> None:
        self._apprentices: Dict[str, Apprentice] = {}

    # ---------------------------------------------------------------- 收徒
    def enroll(self, aid: str, mentor: Optional[str] = None) -> Apprentice:
        if aid in self._apprentices:
            raise ValueError(f"{aid} 已在师徒体系中")
        a = Apprentice(aid=aid, mentor=mentor)
        self._apprentices[aid] = a
        return a

    def get(self, aid: str) -> Apprentice:
        a = self._apprentices.get(aid)
        if a is None:
            raise KeyError(f"{aid} 不在师徒体系中")
        return a

    # ---------------------------------------------------------------- 考核
    def record(self, aid: str, task: str, passed: bool, *,
               severe_fault: bool = False, evidence: str = "") -> Trial:
        a = self.get(aid)
        t = Trial(task=task, passed=passed, severe_fault=severe_fault, evidence=evidence)
        a.trials.append(t)
        if severe_fault:
            self.demote(aid, reason="重大失误")
        return t

    def signoff(self, aid: str, mentor: str) -> None:
        """师傅签字。必须是登记在册的师傅本人，不接受自己给自己签。"""
        a = self.get(aid)
        if a.mentor is None:
            raise PermissionError(f"{aid} 无师傅，无法签字")
        if mentor != a.mentor:
            raise PermissionError(f"{mentor} 不是 {aid} 的师傅（应为 {a.mentor}）")
        if mentor == aid:
            raise PermissionError("不得自己给自己签字")
        a.mentor_signoff = True

    # ---------------------------------------------------------------- 升降
    def can_promote(self, aid: str) -> tuple[bool, str]:
        a = self.get(aid)
        if a.stage == AUTONOMOUS:
            return False, "已是完全自主，无可晋级"
        need_n, need_rate, need_sign = PROMOTION_RULES[a.stage]
        n = len(a.stage_trials())
        if n < need_n:
            return False, f"考核次数 {n} < {need_n}"
        rate = a.success_rate()
        if rate < need_rate:
            return False, f"成功率 {rate:.2f} < {need_rate}"
        if need_sign and not a.mentor_signoff:
            return False, "缺师傅签字"
        return True, "达标"

    def promote(self, aid: str) -> str:
        ok, why = self.can_promote(aid)
        if not ok:
            raise PermissionError(f"{aid} 不满足晋级条件：{why}")
        a = self.get(aid)
        a.stage = STAGES[STAGES.index(a.stage) + 1]
        a.trials.clear()             # 新阶段重新考核
        a.mentor_signoff = False
        return a.stage

    def demote(self, aid: str, reason: str = "") -> str:
        a = self.get(aid)
        i = STAGES.index(a.stage)
        if i > 0:
            a.stage = STAGES[i - 1]
        a.trials.clear()
        a.mentor_signoff = False
        a.demotions += 1
        return a.stage

    # ---------------------------------------------------------------- 查询
    def require(self, aid: str, cap: str) -> None:
        a = self.get(aid)
        if not a.can(cap):
            raise PermissionError(
                f"{aid} 处于 {a.stage} 阶段，无 {cap} 权限（持有={sorted(a.caps())}）")

    def roster(self) -> List[dict]:
        return [a.to_dict() for a in self._apprentices.values()]


__all__ = ["Mentorship", "Apprentice", "Trial", "STAGES", "STAGE_CAPS",
           "PROMOTION_RULES", "OBSERVE", "SHADOW", "LIMITED", "AUTONOMOUS"]
