"""L4F 共识自演化通道 —— 完全自研核心（生命体OS 白皮书 L4F / L5B）。

系统的规则不该永远由最初的作者写死，但也不能谁都能改。
本模块给「规则怎么合法地变」一条**可审计的通道**：

    提案(propose) → 辩论期(debate) → 加权投票(vote) → 生效/否决 → 存档

四条硬约束：
1. **宪法条款需超级多数**（≥2/3 且投票率 ≥60%），普通条款过半即可。
2. **红线条款永不可改**：宪法里标 immutable 的（不伤害人类等）连提案都拒收。
3. **权重投票**：不同角色话语权不同（守卫 > 工人 > 传感器），但**单方不得过半**——
   防止一个角色独裁（这是「大同」的制度保证）。
4. **全程留痕**：谁提的、谁投的、什么时候生效，都写进档案，可事后复核。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 提案类型
ORDINARY, CONSTITUTIONAL = "ordinary", "constitutional"

# 不可变更的红线条款 id（连提案都不受理）
IMMUTABLE_CLAUSES = frozenset({
    "no_harm_to_humans", "no_deception", "no_irreversible_without_approval",
})

# 角色投票权重（单一角色总权重不得 ≥ 50%，由 ConsensusChannel 校验）
DEFAULT_ROLE_WEIGHTS: Dict[str, float] = {
    "guardian": 3.0, "worker": 2.0, "archivist": 1.5, "sensor": 1.0, "human": 5.0,
}

PENDING, DEBATING, PASSED, REJECTED, WITHDRAWN = (
    "pending", "debating", "passed", "rejected", "withdrawn")


class ImmutableClause(PermissionError):
    """试图修改红线条款。"""


@dataclass
class Vote:
    voter: str
    role: str
    approve: bool
    weight: float = 1.0
    rationale: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"voter": self.voter, "role": self.role, "approve": self.approve,
                "weight": self.weight, "rationale": self.rationale[:200], "ts": self.ts}


@dataclass
class Proposal:
    pid: str
    title: str
    clause: str
    kind: str = ORDINARY
    proposer: str = "unknown"
    body: str = ""
    status: str = PENDING
    votes: List[Vote] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    debate_until: float = 0.0
    decided_at: Optional[float] = None
    outcome_reason: str = ""

    def tally(self, weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """统计票权。

        weights 为 None 时用投票当时记录的名义权重（存档口径）；
        传入「角色→有效权重」时按折算后的有效权重统计（结算口径，见
        ConsensusChannel.effective_role_weights）。
        """
        def w_of(v: "Vote") -> float:
            return v.weight if weights is None else weights.get(v.role, v.weight)
        yes = sum(w_of(v) for v in self.votes if v.approve)
        no = sum(w_of(v) for v in self.votes if not v.approve)
        return {"yes": round(yes, 4), "no": round(no, 4),
                "total": round(yes + no, 4), "count": len(self.votes)}

    def to_dict(self) -> dict:
        return {"pid": self.pid, "title": self.title, "clause": self.clause,
                "kind": self.kind, "proposer": self.proposer, "status": self.status,
                "tally": self.tally(), "reason": self.outcome_reason,
                "votes": [v.to_dict() for v in self.votes]}


class ConsensusChannel:
    """共识自演化通道。"""

    ORDINARY_PASS = 0.5          # 普通条款：>50% 赞成权重
    CONSTITUTIONAL_PASS = 2 / 3  # 宪法条款：≥2/3
    MIN_TURNOUT = 0.6            # 宪法条款最低投票率（按合格选民权重）
    MAX_SINGLE_ROLE_SHARE = 0.5  # 单一角色权重占比上限

    def __init__(self, role_weights: Optional[Dict[str, float]] = None,
                 debate_seconds: float = 0.0, strict_electorate: bool = False):
        self.role_weights = dict(role_weights or DEFAULT_ROLE_WEIGHTS)
        self.debate_seconds = debate_seconds
        # strict=True：注册当场就拒绝失衡名册（适合固定名册一次性装配的场景）；
        # 默认 False：允许逐个注册（中间态必然失衡），失衡在结算时以权重折算兜底。
        self.strict_electorate = strict_electorate
        self._proposals: Dict[str, Proposal] = {}
        self._electorate: Dict[str, str] = {}      # voter -> role
        self.archive: List[dict] = []
        self._seq = 0

    # ---------------------------------------------------------------- 选民
    def register_voter(self, voter: str, role: str) -> None:
        if role not in self.role_weights:
            raise ValueError(f"未知角色 {role}，合法={sorted(self.role_weights)}")
        self._electorate[voter] = role
        if self.strict_electorate:
            self.assert_electorate_balanced()

    def role_totals(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for role in self._electorate.values():
            totals[role] = totals.get(role, 0.0) + self.role_weights[role]
        return totals

    def validate_electorate(self) -> dict:
        """体检名册：返回各角色名义占比与是否违反「单方不得过半」。不抛错。"""
        totals = self.role_totals()
        grand = sum(totals.values())
        shares = {r: (w / grand if grand > 0 else 0.0) for r, w in totals.items()}
        offenders = [r for r, s in shares.items()
                     if s >= self.MAX_SINGLE_ROLE_SHARE and len(totals) > 1]
        return {"balanced": not offenders, "offenders": offenders,
                "shares": {r: round(s, 4) for r, s in shares.items()},
                "grand": round(grand, 4)}

    def assert_electorate_balanced(self) -> None:
        rep = self.validate_electorate()
        if not rep["balanced"]:
            r = rep["offenders"][0]
            raise PermissionError(
                f"角色 {r} 权重占比 {rep['shares'][r]:.0%} ≥ "
                f"{self.MAX_SINGLE_ROLE_SHARE:.0%}，"
                f"违反「单方不得过半」，请调整选民构成或权重")

    def effective_role_weights(self) -> Dict[str, float]:
        """有效权重 = 名义权重按「单方不得过半」折算后的每票权重。

        某角色总权重占比 ≥ 上限时，把该角色整体压到恰好等于上限：
        设其他角色合计 O、上限 c，则该角色允许的总权重 = c*O/(1-c)，
        再按比例摊回到该角色每一票上。这样「独裁」在**制度上不可能**，
        而不是靠注册时报错去人工规避。
        """
        totals = self.role_totals()
        grand = sum(totals.values())
        eff = dict(self.role_weights)
        if grand <= 0 or len(totals) <= 1:
            return eff
        c = self.MAX_SINGLE_ROLE_SHARE
        for role, w in totals.items():
            if w / grand >= c and w > 0:
                others = grand - w
                allowed = c * others / (1 - c) if c < 1 else others
                if allowed < w:
                    eff[role] = self.role_weights[role] * (allowed / w)
        return eff

    def electorate_weight(self) -> float:
        """合格选民的**有效**总权重（结算投票率的分母）。"""
        eff = self.effective_role_weights()
        return round(sum(eff[r] for r in self._electorate.values()), 4)

    # ---------------------------------------------------------------- 提案
    def propose(self, title: str, clause: str, *, kind: str = ORDINARY,
                proposer: str = "unknown", body: str = "",
                now: Optional[float] = None) -> Proposal:
        if clause in IMMUTABLE_CLAUSES:
            raise ImmutableClause(
                f"条款 {clause} 属永恒红线，不受理任何修改提案")
        if kind not in (ORDINARY, CONSTITUTIONAL):
            raise ValueError(f"未知提案类型 {kind}")
        self._seq += 1
        now = (time.time() if now is None else now)
        p = Proposal(pid=f"P{self._seq:04d}", title=title, clause=clause, kind=kind,
                     proposer=proposer, body=body, created_at=now,
                     status=DEBATING if self.debate_seconds > 0 else PENDING,
                     debate_until=now + self.debate_seconds)
        self._proposals[p.pid] = p
        return p

    def withdraw(self, pid: str, who: str) -> Proposal:
        p = self._require(pid)
        if p.proposer != who:
            raise PermissionError(f"{who} 非提案人，不能撤回 {pid}")
        p.status = WITHDRAWN
        return p

    # ---------------------------------------------------------------- 投票
    def vote(self, pid: str, voter: str, approve: bool,
             rationale: str = "", now: Optional[float] = None) -> Vote:
        p = self._require(pid)
        if p.status in (PASSED, REJECTED, WITHDRAWN):
            raise PermissionError(f"提案 {pid} 已 {p.status}，不可再投票")
        role = self._electorate.get(voter)
        if role is None:
            raise PermissionError(f"{voter} 不在选民名册中")
        if any(v.voter == voter for v in p.votes):
            raise PermissionError(f"{voter} 已对 {pid} 投过票，不得重复投票")
        now = (time.time() if now is None else now)
        if p.status == DEBATING and now < p.debate_until:
            raise PermissionError(
                f"提案 {pid} 尚在辩论期（还剩 {p.debate_until - now:.1f}s），不得提前投票")
        p.status = PENDING
        # 存档留痕记名义权重（谁在什么身份下投的），结算时再按有效权重折算，
        # 两个口径都可查，避免「悄悄改票权」。
        v = Vote(voter=voter, role=role, approve=approve,
                 weight=self.role_weights[role], rationale=rationale, ts=now)
        p.votes.append(v)
        return v

    # ---------------------------------------------------------------- 结算
    def close(self, pid: str, now: Optional[float] = None) -> Proposal:
        p = self._require(pid)
        if p.status in (PASSED, REJECTED, WITHDRAWN):
            return p
        eff = self.effective_role_weights()
        t = p.tally(eff)                      # 结算口径：按折算后的有效权重
        grand = self.electorate_weight()
        turnout = (t["total"] / grand) if grand > 0 else 0.0
        ratio = (t["yes"] / t["total"]) if t["total"] > 0 else 0.0
        rep = self.validate_electorate()
        capped = "" if rep["balanced"] else \
            f"（名册失衡，已对 {'/'.join(rep['offenders'])} 折算至 " \
            f"{self.MAX_SINGLE_ROLE_SHARE:.0%} 上限）"

        if p.kind == CONSTITUTIONAL:
            if turnout < self.MIN_TURNOUT:
                p.status, p.outcome_reason = REJECTED, \
                    f"宪法提案投票率 {turnout:.0%} < 下限 {self.MIN_TURNOUT:.0%}"
            elif ratio >= self.CONSTITUTIONAL_PASS:
                p.status, p.outcome_reason = PASSED, \
                    f"宪法提案通过（赞成 {ratio:.0%} ≥ 2/3，投票率 {turnout:.0%}）"
            else:
                p.status, p.outcome_reason = REJECTED, \
                    f"宪法提案赞成 {ratio:.0%} < 2/3"
        else:
            if ratio > self.ORDINARY_PASS:
                p.status, p.outcome_reason = PASSED, f"普通提案通过（赞成 {ratio:.0%}）"
            else:
                p.status, p.outcome_reason = REJECTED, f"普通提案赞成 {ratio:.0%} 未过半"

        p.outcome_reason += capped
        p.decided_at = (time.time() if now is None else now)
        self.archive.append(p.to_dict())
        return p

    # ---------------------------------------------------------------- 查询
    def get(self, pid: str) -> Optional[Proposal]:
        return self._proposals.get(pid)

    def open_proposals(self) -> List[Proposal]:
        return [p for p in self._proposals.values()
                if p.status in (PENDING, DEBATING)]

    def pass_rate(self) -> float:
        done = [a for a in self.archive if a["status"] in (PASSED, REJECTED)]
        if not done:
            return 0.0
        return round(sum(1 for a in done if a["status"] == PASSED) / len(done), 4)

    def _require(self, pid: str) -> Proposal:
        p = self._proposals.get(pid)
        if p is None:
            raise KeyError(f"提案 {pid} 不存在")
        return p


__all__ = ["ConsensusChannel", "Proposal", "Vote", "ImmutableClause",
           "ORDINARY", "CONSTITUTIONAL", "IMMUTABLE_CLAUSES", "DEFAULT_ROLE_WEIGHTS",
           "PENDING", "DEBATING", "PASSED", "REJECTED", "WITHDRAWN"]
