"""因果世界模型（Causal World Model）落地 AOS 的核心推理层。

把中数睿智《因果世界模型技术体系蓝皮书》(WAIC2026，已多源核实) 的「三层因果阶梯」
对接到 AOS 既有能力，使系统从「描述发生了什么」升级到「理解干预会怎样、
复盘若换做法会如何」：

  - 关联认知 (association)     → AOS 既有 Trace 观测（记录 WHAT happened）
  - 干预认知 (intervention)    → 本模块 CausalModel.effect_of：估计「若采取动作 A，
                                 预期成功率」—— Pearl 因果之梯第二层
  - 反事实认知 (counterfactual) → CausalModel.counterfactual：估计「若当初换做 B，
                                 会比实际 A 好多少」——第三层，可直接喂给 autopilot 反思
  - 事前可验证 (verifiable)     → 所有估计都来自**可计数样本**（success/total），
                                 带样本量下限，样本不足时诚实返回 unknown（理念9）

这与 AOS 的「失败即训练 / 反思闭环 / 白盒蒸馏」天然咬合：EvolutionDistiller 已
在收集 (capability,engine)→成败，本模块把它上升为「干预效应」与「反事实复盘」，
让路由与反思能用因果语言做决策，而非拍脑袋。

仅用标准库，无第三方依赖；全部方法可单测、可审计（理念8 白盒）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kernel.evolution_distiller import EvolutionDistiller  # 复用既有白盒蒸馏统计


@dataclass
class Intervention:
    """一条「在 context 下采取 action，得到 outcome」的干预记录。

    这是白盒 Trace 的最小因果单元：每个样本都是一次真实闸门的成败判定，
    而非模型臆测——保证因果估计可复核（理念6/9）。
    """

    context: str           # 任务/能力上下文（如 "web.search"）
    action: str            # 采取的动作/引擎（如 "anysearch" / "bing"）
    outcome: bool          # 是否成功（真实闸门判定）
    value: float = 1.0     # 可选量化指标（如置信分）；默认 1.0
    timestamp: float = field(default_factory=time.time)


class CausalModel:
    """轻量经验因果模型：从可计数干预样本估计干预效应与反事实复盘。

    不做任何不可验证的「黑盒推演」——样本不足即诚实 unknown，与 AOS 诚实铁律一致。
    """

    MIN_SAMPLES = 5  # 样本不足时诚实返回 unknown（事前不可验证→不瞎估）

    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str], List[Intervention]] = {}

    def ingest(self, iv: Intervention) -> None:
        self._data.setdefault((iv.context, iv.action), []).append(iv)

    def ingest_batch(self, items: List[Intervention]) -> None:
        for iv in items:
            self.ingest(iv)

    def _series(self, context: str, action: str) -> List[Intervention]:
        return self._data.get((context, action), [])

    def effect_of(self, context: str, action: str) -> Dict[str, Any]:
        """干预认知（第二层）：估计「在 context 下采取 action 的预期成功率」。"""
        s = self._series(context, action)
        n = len(s)
        if n < self.MIN_SAMPLES:
            return {
                "action": action, "context": context, "samples": n,
                "success_rate": None, "verdict": "unknown",
                "reason": f"样本不足（{n}/{self.MIN_SAMPLES}），不瞎估（理念9 事前可验证）",
            }
        succ = sum(1 for x in s if x.outcome)
        rate = succ / n
        return {
            "action": action, "context": context, "samples": n,
            "success_rate": rate,
            "verdict": "reliable" if rate >= 0.5 else "unreliable",
            "reason": f"{succ}/{n} 次成功",
        }

    def counterfactual(self, context: str, actual_action: str,
                       alt_action: str) -> Dict[str, Any]:
        """反事实认知（第三层）：估计「若当初换做 alt_action，会比实际 actual_action 好多少」。"""
        actual = self.effect_of(context, actual_action)
        alt = self.effect_of(context, alt_action)
        if actual["success_rate"] is None or alt["success_rate"] is None:
            return {
                "context": context, "actual": actual, "alt": alt,
                "delta": None, "verdict": "unknown",
                "reason": "实际或备选动作样本不足，无法做反事实复盘",
            }
        delta = round(alt["success_rate"] - actual["success_rate"], 4)
        return {
            "context": context,
            "actual": actual, "alt": alt,
            "delta": delta,
            "verdict": ("alt_better" if delta > 0 else
                        "actual_better" if delta < 0 else "parity"),
            "reason": f"备选 {alt_action} 成功率 {alt['success_rate']:.2f} "
                      f"vs 实际 {actual_action} {actual['success_rate']:.2f} "
                      f"(Δ={delta:+.2f})",
        }

    def best_action(self, context: str, actions: List[str]) -> Optional[Dict[str, Any]]:
        """在候选动作里挑预期成功率最高且样本充足的；都不足则返回 None（诚实）。"""
        best: Optional[Dict[str, Any]] = None
        for a in actions:
            e = self.effect_of(context, a)
            if e["success_rate"] is None:
                continue
            if best is None or e["success_rate"] > best["success_rate"]:
                best = e
        return best

    def from_distiller(self, distiller: EvolutionDistiller) -> "CausalModel":
        """把 EvolutionDistiller 的 (capability,engine)→成败 统计上升为因果干预记录。

        蒸馏器已在路由热路径收集真实成败；这里复用它，把「白盒蒸馏」直接变成
        「因果干预效应」，避免重复采集、且保证数据源一致可复核。
        """
        for key, st in distiller.stats.items():
            ctx, act = key.split("::", 1) if "::" in key else ("unknown", key)
            ok = getattr(st, "ok", 0)
            fail = getattr(st, "fail", 0)
            for _ in range(int(ok)):
                self.ingest(Intervention(context=ctx, action=act, outcome=True))
            for _ in range(int(fail)):
                self.ingest(Intervention(context=ctx, action=act, outcome=False))
        return self
