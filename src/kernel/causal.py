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

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

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


def _wilson_ci(success: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson 95% 置信区间（小样本也稳健，避免 Wald 在极端比率下越界）。

    D4：样本量小 → 区间宽 → 置信低，把「不确定度」显式交出去，而非报一个假精确比率。
    """
    if n <= 0:
        return (0.0, 0.0)
    p = success / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


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
        """干预认知（第二层）：估计「在 context 下采取 action 的预期成功率」。

        D4 关键修正：返回 **观测相关**（observational_association）而非「已证因果」——
        路由成败吸收了大量未控混淆变量（prompt 复杂度/模型版本/时段/负载），本模块做的是
        Pearl 之梯**第一层关联**，不是 do-intervention。同时输出 Wilson 95% 置信区间与
        置信级别，样本不足仍诚实 unknown，杜绝 5 样本就敢报确定比率（理念6 量化置信）。
        """
        s = self._series(context, action)
        n = len(s)
        if n < self.MIN_SAMPLES:
            return {
                "action": action, "context": context, "samples": n,
                "success_rate": None,
                "ci_low": None, "ci_high": None,
                "inference_type": "observational_association",
                "verdict": "unknown",
                "confidence": "insufficient_samples",
                "reason": f"样本不足（{n}/{self.MIN_SAMPLES}），不瞎估（理念9 事前可验证）",
            }
        succ = sum(1 for x in s if x.outcome)
        rate = succ / n
        ci_low, ci_high = _wilson_ci(succ, n)
        width = ci_high - ci_low
        # 置信级别随区间宽度下降（区间越宽越不确定）。
        conf = "low" if width > 0.4 else ("medium" if width > 0.25 else "high")
        return {
            "action": action, "context": context, "samples": n,
            "success_rate": rate,
            "ci_low": round(ci_low, 4), "ci_high": round(ci_high, 4),
            "inference_type": "observational_association",
            "verdict": "reliable" if rate >= 0.5 else "unreliable",
            "confidence": conf,
            "reason": f"{succ}/{n} 次成功，95% 置信区间[{ci_low:.2f},{ci_high:.2f}]"
                      f"（此为观测相关，非已证因果，吸收未控混淆变量）",
        }

    def counterfactual(self, context: str, actual_action: str,
                       alt_action: str,
                       costs: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """反事实认知（第三层）：估计「若当初换做 alt_action，会比实际 actual_action 如何」。

        D5 决策论层：除成功率差（delta）外，额外给出**效用差**（utility_delta）——
        当注入各动作成本（costs）后，「成功率更高」未必「更值」。autopilot 反思可据此
        选择「次优成功率但更省成本」的动作，而非盲目追最高准确率。
        """
        costs = costs or {}
        actual = self.effect_of(context, actual_action)
        alt = self.effect_of(context, alt_action)
        if actual["success_rate"] is None or alt["success_rate"] is None:
            return {
                "context": context, "actual": actual, "alt": alt,
                "delta": None, "utility_delta": None, "verdict": "unknown",
                "inference_type": "observational_association",
                "reason": "实际或备选动作样本不足，无法做反事实复盘"
                         "（且此为观测相关，非已证因果）",
            }
        delta = round(alt["success_rate"] - actual["success_rate"], 4)
        util_actual = actual["success_rate"] - costs.get(actual_action, 0.0)
        util_alt = alt["success_rate"] - costs.get(alt_action, 0.0)
        util_delta = round(util_alt - util_actual, 4)
        return {
            "context": context,
            "actual": actual, "alt": alt,
            "delta": delta,
            "utility_actual": round(util_actual, 4),
            "utility_alt": round(util_alt, 4),
            "utility_delta": util_delta,
            "verdict": ("alt_better" if util_delta > 0 else
                        "actual_better" if util_delta < 0 else "parity"),
            "inference_type": "observational_association",
            "reason": f"备选 {alt_action} 成功率 {alt['success_rate']:.2f} "
                      f"vs 实际 {actual_action} {actual['success_rate']:.2f} "
                      f"(Δ成功={delta:+.2f}, Δ效用={util_delta:+.2f})"
                      f"；此为观测相关（非已证因果），仅供换做法参考",
        }

    def best_action(self, context: str, actions: List[str],
                    weights: Optional[Dict[str, float]] = None,
                    costs: Optional[Dict[str, float]] = None,
                    latencies: Optional[Dict[str, float]] = None,
                    scorer: Optional[Callable[[Dict[str, Any], str], float]] = None
                    ) -> Optional[Dict[str, Any]]:
        """在候选动作里挑预期效用最高且样本充足的；都不足则返回 None（诚实）。

        D5 决策论层（默认退化为「比成功率」，向后兼容）：
        - weights: 决策权重 {rate, cost, latency}，utility = rate·成功率 − cost·成本 − latency·时延
        - costs/latencies: {action: 数值}
        - scorer: 自定义打分函数 (effect_dict, action) -> float，优先级最高
        返回的是 effect dict（含 success_rate/ci/confidence），并附 utility 字段。
        """
        if weights is None:
            weights = {"rate": 1.0, "cost": 0.0, "latency": 0.0}
        costs = costs or {}
        latencies = latencies or {}
        best: Optional[Dict[str, Any]] = None
        best_util: Optional[float] = None
        for a in actions:
            e = self.effect_of(context, a)
            if e["success_rate"] is None:
                continue
            if scorer is not None:
                util = scorer(e, a)
            else:
                util = (e["success_rate"] * weights.get("rate", 1.0)
                        - costs.get(a, 0.0) * weights.get("cost", 0.0)
                        - latencies.get(a, 0.0) * weights.get("latency", 0.0))
            if best_util is None or util > best_util:
                best_util = util
                best = dict(e)
                best["utility"] = round(util, 4)
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
