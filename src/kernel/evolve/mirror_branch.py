"""L5 演进层 · 镜像分支试错（Mirror Branch Trial）—— 完全自研核心（生命体OS 白皮书 L5）。

**问题**：自进化最大的风险不是「改不动」，而是「改坏了还上线了」。
`evolution_distiller` 能蒸馏出候选改法，但缺一道**上线前的对照闸门**——
改动必须先在镜像分支跑影子流量，与基线做统计对照，达标才 promote，不达标自动 rollback。

**设计（四条纪律）**：

1. **影子不出门（side-effect free）**：候选臂的产出**不投放真实世界**。
   `record()` 强制校验 `emitted=False`，候选臂一旦被标记已投放即抛 `ShadowLeak`。
   ——对应宪法 reversibility：试错阶段必须可逆。
2. **不够样本不下结论**：`MIN_SAMPLES` 之前一律 `hold`，绝不"跑两次就上线"（理念6 量化置信）。
   显著性用**双比例 z 检验**自研实现（无 scipy 依赖），单边检验候选是否真的更好。
3. **宪法红线不可跨**：候选臂只要出现 **1 次伤害事件**（`harm=True`）即永久 `BLOCKED`，
   不设"可容忍伤害率"（与 `spirit/datong.py` 的 no_harm=1.0 一致）。
4. **不可逆改动必须人审**：`irreversible=True` 的分支，即使数据达标也只给 `needs_approval`，
   必须显式传 `approver`（可再叠加 L4 共识提案 `consensus_ok`）才能 promote。

**与既有模块的关系（选型铁律：现有够好就复用，不重复造）**：
- 统计对照本模块自带（causal.py 是"观测相关"事后归因，这里是"事前 A/B 闸门"，职责不同）；
- 共识审批复用 `kernel.spirit.consensus.ConsensusChannel`，本模块只留 `consensus_ok` 钩子；
- 回滚快照只存"引用 + 元数据"，不复制代码，真正的代码版本管理交给 `versioning.py` / git。

诚实度：② 单元验证（tests/test_mirror_branch.py）。真实流量灰度为 ③ 待验。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

BASELINE = "baseline"
CANDIDATE = "candidate"
ARMS = (BASELINE, CANDIDATE)

# 分支状态
TRIAL = "trial"            # 试错中
PROMOTED = "promoted"      # 已晋升（候选取代基线）
ROLLED_BACK = "rolled_back"  # 已回滚
BLOCKED = "blocked"        # 宪法红线否决，永久拉黑

# 闸门判决
HOLD = "hold"
PROMOTE = "promote"
ROLLBACK = "rollback"
NEEDS_APPROVAL = "needs_approval"
CONSTITUTION_BLOCK = "constitution_block"


class ShadowLeak(RuntimeError):
    """候选臂的产出被投放到真实世界——影子流量纪律被破坏。"""


class BranchClosed(RuntimeError):
    """分支已终局（promoted/rolled_back/blocked），不接受新样本。"""


def _phi(x: float) -> float:
    """标准正态 CDF（用 erf 实现，避免引 scipy）。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_proportion_z(succ_a: int, n_a: int, succ_b: int, n_b: int) -> Dict[str, float]:
    """双比例 z 检验：检验 A（候选）成功率是否**显著高于** B（基线）。

    返回 z 值与**单边** p 值。样本为 0 时返回 z=0/p=1（即"没证据"），不抛错。
    """
    if n_a <= 0 or n_b <= 0:
        return {"z": 0.0, "p_value": 1.0}
    p_a = succ_a / n_a
    p_b = succ_b / n_b
    pooled = (succ_a + succ_b) / (n_a + n_b)
    denom = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b))
    if denom <= 0:
        return {"z": 0.0, "p_value": 1.0}
    z = (p_a - p_b) / denom
    return {"z": z, "p_value": 1.0 - _phi(z)}


@dataclass
class TrialSample:
    """一次影子对照的单臂样本。"""
    task_id: str
    arm: str
    success: bool
    cost: float = 0.0
    latency: float = 0.0
    harm: bool = False          # 是否造成真实伤害（宪法红线）
    emitted: bool = False       # 产出是否已投放真实世界
    ts: float = 0.0
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "arm": self.arm, "success": self.success,
            "cost": round(self.cost, 6), "latency": round(self.latency, 4),
            "harm": self.harm, "emitted": self.emitted, "ts": self.ts,
        }


@dataclass
class GateDecision:
    """闸门判决（带可复核理由，不给黑箱结论）。"""
    verdict: str
    reason: str
    lift: float = 0.0
    p_value: float = 1.0
    samples: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict, "reason": self.reason,
            "lift": round(self.lift, 4), "p_value": round(self.p_value, 4),
            "samples": dict(self.samples),
        }


class MirrorBranch:
    """镜像分支：基线 vs 候选的影子对照 + 晋升闸门 + 回滚留痕。"""

    MIN_SAMPLES = 20          # 每臂最少样本，不够不下结论
    MIN_LIFT = 0.05           # 最小提升幅度（5 个百分点）
    ALPHA = 0.05              # 显著性水平（单边）
    MAX_COST_RATIO = 1.5      # 候选成本不得超过基线 1.5 倍（贵太多不划算）
    ROLLBACK_LIFT = -0.10     # 明显更差即建议回滚

    def __init__(self, name: str, baseline_ref: str, candidate_ref: str, *,
                 irreversible: bool = False,
                 min_samples: Optional[int] = None,
                 min_lift: Optional[float] = None,
                 alpha: Optional[float] = None) -> None:
        self.name = name
        self.baseline_ref = baseline_ref
        self.candidate_ref = candidate_ref
        self.irreversible = irreversible
        self.min_samples = self.MIN_SAMPLES if min_samples is None else min_samples
        self.min_lift = self.MIN_LIFT if min_lift is None else min_lift
        self.alpha = self.ALPHA if alpha is None else alpha
        self.state = TRIAL
        self.samples: List[TrialSample] = []
        self.audit: List[Dict[str, Any]] = []
        self._snapshot = {"ref": baseline_ref, "taken_at": None}

    # ---------------- 采样 ----------------

    def record(self, task_id: str, arm: str, success: bool, *,
               cost: float = 0.0, latency: float = 0.0,
               harm: bool = False, emitted: bool = False,
               now: Optional[float] = None,
               detail: Optional[Dict[str, Any]] = None) -> TrialSample:
        """记一条样本。候选臂 `emitted=True` 直接抛 ShadowLeak（影子不出门）。"""
        if self.state != TRIAL:
            raise BranchClosed(f"分支 {self.name} 已 {self.state}，不再接受样本")
        if arm not in ARMS:
            raise ValueError(f"未知臂：{arm}（只允许 {ARMS}）")
        if arm == CANDIDATE and emitted:
            raise ShadowLeak(
                f"分支 {self.name}：候选臂产出被投放真实世界（task={task_id}），"
                f"违反影子流量纪律（宪法 reversibility）"
            )
        s = TrialSample(
            task_id=task_id, arm=arm, success=success, cost=cost, latency=latency,
            harm=harm, emitted=emitted,
            ts=time.time() if now is None else now,
            detail=dict(detail or {}),
        )
        self.samples.append(s)
        if arm == CANDIDATE and harm:
            self._block(f"候选臂出现伤害事件（task={task_id}），宪法 no_harm=1.0 不设容忍率", now=now)
        return s

    def shadow_run(self, task_id: str,
                   baseline_runner: Callable[[str], Dict[str, Any]],
                   candidate_runner: Callable[[str], Dict[str, Any]],
                   *, now: Optional[float] = None) -> Dict[str, TrialSample]:
        """同一任务两臂各跑一次。runner 返回 dict，至少含 `success`。

        runner 抛异常不吞——记为失败样本后**继续**（失败即训练数据，理念2），
        但异常信息完整留在 detail 里（理念6 诚实）。
        """
        out: Dict[str, TrialSample] = {}
        for arm, runner in ((BASELINE, baseline_runner), (CANDIDATE, candidate_runner)):
            t0 = time.time()
            try:
                r = runner(task_id) or {}
                out[arm] = self.record(
                    task_id, arm, bool(r.get("success")),
                    cost=float(r.get("cost", 0.0)),
                    latency=float(r.get("latency", time.time() - t0)),
                    harm=bool(r.get("harm", False)),
                    emitted=bool(r.get("emitted", False)) if arm == BASELINE else False,
                    now=now, detail={"raw": r},
                )
            except ShadowLeak:
                raise
            except Exception as exc:  # noqa: BLE001 —— 真实错误要留证据
                out[arm] = self.record(
                    task_id, arm, False,
                    latency=time.time() - t0, now=now,
                    detail={"error": f"{type(exc).__name__}: {exc}"},
                )
        return out

    # ---------------- 度量 ----------------

    def arm_metrics(self, arm: str) -> Dict[str, Any]:
        rows = [s for s in self.samples if s.arm == arm]
        n = len(rows)
        succ = sum(1 for s in rows if s.success)
        cost = sum(s.cost for s in rows)
        lat = sum(s.latency for s in rows)
        return {
            "arm": arm, "samples": n, "success": succ,
            "success_rate": (succ / n) if n else None,
            "avg_cost": (cost / n) if n else None,
            "avg_latency": (lat / n) if n else None,
            "harm_events": sum(1 for s in rows if s.harm),
        }

    def metrics(self) -> Dict[str, Any]:
        b = self.arm_metrics(BASELINE)
        c = self.arm_metrics(CANDIDATE)
        lift = None
        if b["success_rate"] is not None and c["success_rate"] is not None:
            lift = c["success_rate"] - b["success_rate"]
        return {"name": self.name, "state": self.state,
                BASELINE: b, CANDIDATE: c,
                "lift": lift, "irreversible": self.irreversible}

    # ---------------- 闸门 ----------------

    def gate(self) -> GateDecision:
        """给出晋升判决。不产生副作用，可反复调用（白盒可复核）。"""
        b = self.arm_metrics(BASELINE)
        c = self.arm_metrics(CANDIDATE)
        n = {BASELINE: b["samples"], CANDIDATE: c["samples"]}

        if self.state == BLOCKED:
            return GateDecision(CONSTITUTION_BLOCK, "分支已被宪法红线拉黑，不可晋升", samples=n)
        if c["harm_events"] > 0:
            return GateDecision(CONSTITUTION_BLOCK,
                                f"候选臂伤害事件 {c['harm_events']} 次 > 0，宪法 no_harm 红线",
                                samples=n)
        if n[BASELINE] < self.min_samples or n[CANDIDATE] < self.min_samples:
            return GateDecision(HOLD,
                                f"样本不足（基线 {n[BASELINE]}/{self.min_samples}，"
                                f"候选 {n[CANDIDATE]}/{self.min_samples}），不瞎下结论",
                                samples=n)

        lift = c["success_rate"] - b["success_rate"]
        stat = two_proportion_z(c["success"], n[CANDIDATE], b["success"], n[BASELINE])
        p = stat["p_value"]

        if lift <= self.ROLLBACK_LIFT:
            return GateDecision(ROLLBACK,
                                f"候选显著更差（lift={lift:+.1%}），建议回滚",
                                lift=lift, p_value=p, samples=n)
        if lift < self.min_lift:
            return GateDecision(HOLD,
                                f"提升不足（lift={lift:+.1%} < 阈值 {self.min_lift:+.1%}）",
                                lift=lift, p_value=p, samples=n)
        if p > self.alpha:
            return GateDecision(HOLD,
                                f"提升未达统计显著（p={p:.3f} > α={self.alpha}），可能是噪声",
                                lift=lift, p_value=p, samples=n)
        if (b["avg_cost"] or 0) > 0 and (c["avg_cost"] or 0) > (b["avg_cost"] * self.MAX_COST_RATIO):
            return GateDecision(HOLD,
                                f"候选成本过高（{c['avg_cost']:.4f} > 基线 {b['avg_cost']:.4f} "
                                f"× {self.MAX_COST_RATIO}），性价比不划算",
                                lift=lift, p_value=p, samples=n)
        if self.irreversible:
            return GateDecision(NEEDS_APPROVAL,
                                f"数据达标（lift={lift:+.1%}, p={p:.3f}）但改动不可逆，需人工审批",
                                lift=lift, p_value=p, samples=n)
        return GateDecision(PROMOTE,
                            f"候选胜出（lift={lift:+.1%}, p={p:.3f}），可晋升",
                            lift=lift, p_value=p, samples=n)

    # ---------------- 终局动作 ----------------

    def promote(self, *, approver: Optional[str] = None,
                consensus_ok: bool = False,
                now: Optional[float] = None) -> Dict[str, Any]:
        """晋升候选为新基线。宪法拉黑不可晋升；不可逆改动必须 approver。"""
        d = self.gate()
        if d.verdict == CONSTITUTION_BLOCK:
            raise PermissionError(f"晋升被宪法红线拒绝：{d.reason}")
        if d.verdict in (HOLD, ROLLBACK):
            raise PermissionError(f"晋升条件不满足：{d.reason}")
        if d.verdict == NEEDS_APPROVAL and not (approver or consensus_ok):
            raise PermissionError(f"不可逆改动需人工审批或 L4 共识通过：{d.reason}")

        self._snapshot = {"ref": self.baseline_ref, "taken_at": time.time() if now is None else now}
        old = self.baseline_ref
        self.baseline_ref = self.candidate_ref
        self.state = PROMOTED
        rec = {"event": "promote", "from": old, "to": self.candidate_ref,
               "approver": approver, "consensus_ok": consensus_ok,
               "decision": d.to_dict(),
               "ts": time.time() if now is None else now}
        self.audit.append(rec)
        return rec

    def rollback(self, reason: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """回滚到快照基线。晋升后仍可回滚（快照留着就是为了这个）。"""
        restored = self._snapshot.get("ref") or self.baseline_ref
        self.baseline_ref = restored
        self.state = ROLLED_BACK
        rec = {"event": "rollback", "restored": restored, "reason": reason,
               "ts": time.time() if now is None else now}
        self.audit.append(rec)
        return rec

    def _block(self, reason: str, *, now: Optional[float] = None) -> None:
        self.state = BLOCKED
        self.audit.append({"event": "constitution_block", "reason": reason,
                           "ts": time.time() if now is None else now})

    def to_dict(self) -> dict:
        return {"metrics": self.metrics(), "gate": self.gate().to_dict(),
                "audit": list(self.audit),
                "baseline_ref": self.baseline_ref, "candidate_ref": self.candidate_ref}


class MirrorLab:
    """镜像实验室：管多条分支，给出全局"可晋升清单"。

    并发上限 `MAX_CONCURRENT` 防"同时改十处"——多处同改会互相污染归因（理念8 白盒可解释）。
    """

    MAX_CONCURRENT = 3

    def __init__(self, max_concurrent: Optional[int] = None) -> None:
        self.max_concurrent = self.MAX_CONCURRENT if max_concurrent is None else max_concurrent
        self.branches: Dict[str, MirrorBranch] = {}

    def open(self, name: str, baseline_ref: str, candidate_ref: str, **kw) -> MirrorBranch:
        if name in self.branches and self.branches[name].state == TRIAL:
            raise ValueError(f"分支 {name} 已在试错中")
        active = sum(1 for b in self.branches.values() if b.state == TRIAL)
        if active >= self.max_concurrent:
            raise PermissionError(
                f"并发试错分支已达上限 {self.max_concurrent}，多处同改会污染归因，先收敛再开新分支"
            )
        br = MirrorBranch(name, baseline_ref, candidate_ref, **kw)
        self.branches[name] = br
        return br

    def promotable(self) -> List[str]:
        return [n for n, b in self.branches.items() if b.gate().verdict == PROMOTE]

    def blocked(self) -> List[str]:
        return [n for n, b in self.branches.items() if b.state == BLOCKED]

    def report(self) -> Dict[str, Any]:
        return {
            "active": sum(1 for b in self.branches.values() if b.state == TRIAL),
            "promotable": self.promotable(),
            "blocked": self.blocked(),
            "branches": {n: b.metrics() for n, b in self.branches.items()},
        }
