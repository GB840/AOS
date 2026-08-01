"""L4D 大同指数 + L4E 文明试错镜像 —— 完全自研核心（生命体OS 白皮书 L4D/L4E）。

**大同指数（Datong Index）**：给「多个个体/租户/文明共处得好不好」一个**可计算的分**，
免得「和谐共处」永远停留在口号。四个可测子项，各占 25%：

    diversity   多样性：价值观分布是否被单一插件垄断（用归一化熵）
    fairness    公平性：资源分配是否过度倾斜（用 1 - 基尼系数）
    consensus   共识度：近期提案的通过一致性
    harm_free   无害性：无害事件占比（有伤害记录直接拉低）

分数低不是罚分，是**告警**：低于阈值触发调节（调配额/开辩论/收权限）。

**文明试错镜像（Civilization Mirror）**：任何会影响全体的变更，
先在**镜像沙盘**里对副本跑一遍，看大同指数与关键指标怎么变，
再决定要不要上真身——「试错在镜像里，代价不落到真人身上」。
"""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

DEFAULT_ALERT = 0.55        # 大同指数低于此值触发调节


def _entropy_norm(values: Sequence[float]) -> float:
    """归一化香农熵 0..1：1=完全均衡，0=完全垄断。"""
    vals = [v for v in values if v > 0]
    if len(vals) <= 1:
        return 0.0
    total = sum(vals)
    ps = [v / total for v in vals]
    h = -sum(p * math.log(p) for p in ps)
    return round(h / math.log(len(vals)), 4)


def _gini(values: Sequence[float]) -> float:
    """基尼系数 0..1：0=绝对平均，1=绝对不均。"""
    xs = sorted(float(v) for v in values if v >= 0)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return round((2 * cum) / (n * sum(xs)) - (n + 1) / n, 4)


@dataclass
class DatongIndex:
    """大同指数计算器。所有输入都必须是**真实观测**，不接受主观打分。"""

    alert_threshold: float = DEFAULT_ALERT
    history: List[dict] = field(default_factory=list)

    def compute(self, *, value_shares: Sequence[float],
                resource_shares: Sequence[float],
                votes_passed: int = 0, votes_total: int = 0,
                harm_events: int = 0, total_events: int = 0) -> dict:
        diversity = _entropy_norm(value_shares)
        fairness = round(1.0 - _gini(resource_shares), 4)
        consensus = round(votes_passed / votes_total, 4) if votes_total > 0 else 0.5
        if total_events > 0:
            harm_free = round(1.0 - harm_events / total_events, 4)
        else:
            harm_free = 1.0 if harm_events == 0 else 0.0
        score = round((diversity + fairness + consensus + harm_free) / 4, 4)
        out = {"score": score, "diversity": diversity, "fairness": fairness,
               "consensus": consensus, "harm_free": harm_free,
               "alert": score < self.alert_threshold, "ts": time.time()}
        out["actions"] = self.actions_for(out)
        self.history.append(out)
        return out

    def actions_for(self, m: dict) -> List[str]:
        """低分时给出**具体**调节动作，而不是「建议加强协作」这种空话。"""
        acts: List[str] = []
        if m["diversity"] < 0.5:
            acts.append("open_values_market:invite_more_plugins")
        if m["fairness"] < 0.5:
            acts.append("rebalance_quota:cap_top_consumer")
        if m["consensus"] < 0.5:
            acts.append("open_debate:dialectic_high")
        # no_harm 是宪法红线（权重 1.0），不设「可容忍的伤害率」：
        # 只要观测到伤害事件，高危动作即刻转人工审批。
        if m["harm_free"] < 1.0:
            acts.append("freeze_risky_actions:require_approval")
        return acts

    def trend(self, n: int = 5) -> float:
        """近 n 次分数的变化（正=在变好）。"""
        h = [x["score"] for x in self.history[-n:]]
        return 0.0 if len(h) < 2 else round(h[-1] - h[0], 4)


@dataclass
class MirrorResult:
    accepted: bool
    before: dict
    after: dict
    delta: float
    reason: str
    side_effects: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "delta": round(self.delta, 4),
                "reason": self.reason, "before": self.before["score"],
                "after": self.after["score"], "side_effects": list(self.side_effects)}


class CivilizationMirror:
    """文明试错镜像：在副本沙盘里预演变更，再决定是否上真身。"""

    def __init__(self, index: Optional[DatongIndex] = None,
                 min_delta: float = -0.02):
        self.index = index or DatongIndex()
        self.min_delta = min_delta      # 允许的最大恶化幅度
        self.log: List[dict] = []

    def rehearse(self, world: dict,
                 change: Callable[[dict], dict],
                 measure: Callable[[dict], dict]) -> MirrorResult:
        """world 是当前世界状态字典；change 在**深拷贝**上施加变更；measure 产出指标。

        深拷贝是硬要求：镜像绝不能污染真身（这是「试错在镜像里」的物理保证）。
        """
        before = measure(world)
        sandbox = copy.deepcopy(world)
        try:
            changed = change(sandbox)
        except Exception as exc:      # 沙盘里炸了，正是镜像存在的意义
            res = MirrorResult(False, before, before, 0.0,
                               f"镜像内变更抛错，拒绝上真身：{type(exc).__name__}: {exc}")
            self.log.append(res.to_dict())
            return res
        after = measure(changed)
        delta = after["score"] - before["score"]
        side: List[str] = []
        for k in ("diversity", "fairness", "consensus", "harm_free"):
            if after.get(k, 1) < before.get(k, 0) - 0.05:
                side.append(f"{k} 下降 {before[k]:.2f}→{after[k]:.2f}")
        if after.get("harm_free", 1.0) < before.get("harm_free", 1.0):
            accepted, reason = False, "无害性下降，任何收益都不足以抵偿（宪法优先）"
        elif delta < self.min_delta:
            accepted, reason = False, f"大同指数恶化 {delta:.4f} < 容忍下限 {self.min_delta}"
        else:
            accepted, reason = True, f"镜像预演通过，大同指数 {delta:+.4f}"
        res = MirrorResult(accepted, before, after, delta, reason, side)
        self.log.append(res.to_dict())
        return res

    def apply_if_accepted(self, world: dict, change: Callable[[dict], dict],
                          measure: Callable[[dict], dict]) -> tuple[dict, MirrorResult]:
        """预演通过才施加到真身；否则原样返回（真身零改动）。"""
        res = self.rehearse(world, change, measure)
        return (change(world), res) if res.accepted else (world, res)


__all__ = ["DatongIndex", "CivilizationMirror", "MirrorResult", "DEFAULT_ALERT"]
