"""L6 虚实交互闭环 · 人本因果仿真 —— 完全自研核心（生命体OS 白皮书 L0/L6）。

**问题**：`action_arbiter` 判「该不该做」靠的是规则分级，`causal.py` 算的是「历史上这么干成没成」
（观测相关，事后归因）。两者都缺一件事——**这个行动落到"人"身上会怎样**。
白皮书 L0 是"人本生命状态"，可行动前从没有人替人算过账：占了他多少时间、耗了多少注意力、
花了多少钱、动了什么关系、削了多少自主权。

本模块做**事前反事实推演**：给定拟执行动作的标签集，在人本六维上推演 do(action) vs do(nothing)，
输出 `HumanImpact`，供 `action_arbiter` / 紧急制动做决策。

**方法（诚实说明，不吹成"因果发现"）**：
这是**结构因果模型（SCM）的先验版本** —— 边是人写死的领域先验（谁影响谁、强度多少、
衰减多快、置信几何），不是从数据里学出来的因果结构。所以：
- 有经验数据时（传入 `kernel.causal.CausalModel`），用经验成功率**调制**先验强度（融合，不替代）；
- 每条边带 `confidence`，最终输出附 `confidence` 与 `evidence`，**绝不报"已证因果"**；
- 样本/边缺失时如实标 `unknown`，宁可不判也不瞎判（理念6）。

**宪法接线**：
- 任一维度出现 `harm`（越过 `HARM_THRESHOLD` 的负向冲击）→ 判决 `deny`，no_harm 是红线；
- 不可逆性 ≥ `IRREVERSIBLE_GATE` → `needs_approval`（对应宪法 reversibility≥0.8）；
- 自主权（autonomy）被削是**加权最重**的负项——生命体不能把人变成它的外设。

诚实度：② 单元验证（tests/test_interact_layer.py）。真实人本回访校准为 ③ 待验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 人本六维（L0 人本生命状态的可推演投影）
DIM_TIME = "time"                  # 时间占用（负=被占）
DIM_ATTENTION = "attention"        # 注意力/认知负荷
DIM_EMOTION = "emotion"            # 情绪
DIM_MONEY = "money"                # 金钱
DIM_RELATION = "relationship"      # 社会关系
DIM_AUTONOMY = "autonomy"          # 自主权（最重）

DIMENSIONS = (DIM_TIME, DIM_ATTENTION, DIM_EMOTION, DIM_MONEY, DIM_RELATION, DIM_AUTONOMY)

# 福祉聚合权重：自主权最重，其次情绪与关系（钱可再赚，人不可复原）
DIM_WEIGHTS: Dict[str, float] = {
    DIM_TIME: 1.0,
    DIM_ATTENTION: 1.0,
    DIM_EMOTION: 1.4,
    DIM_MONEY: 0.8,
    DIM_RELATION: 1.3,
    DIM_AUTONOMY: 1.8,
}

ALLOW = "allow"
NEEDS_APPROVAL = "needs_approval"
DENY = "deny"


@dataclass
class CausalEdge:
    """一条人本因果先验边：动作标签 → 人本维度。"""
    tag: str
    dim: str
    effect: float                  # 单位强度的即时冲击（正=有益，负=有害）
    decay: float = 0.5             # 每期衰减系数（0=一次性，接近1=长期累积）
    confidence: float = 0.6        # 该先验的置信度
    irreversible: bool = False     # 该冲击是否不可撤销（如"发出去的公开言论"）
    note: str = ""

    def horizon_effect(self, magnitude: float, horizon: int) -> float:
        """多期累计冲击：effect * magnitude * Σ decay^t（t=0..horizon-1）。"""
        total = 0.0
        for t in range(max(1, horizon)):
            total += self.effect * magnitude * (self.decay ** t)
        return total


@dataclass
class HumanImpact:
    """推演结果。所有数字都带出处，可复核。"""
    deltas: Dict[str, float] = field(default_factory=dict)
    net_wellbeing: float = 0.0
    regret_risk: float = 0.0
    irreversibility: float = 0.0
    confidence: float = 0.0
    harmful_dims: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    unknown: bool = False

    def to_dict(self) -> dict:
        return {
            "deltas": {k: round(v, 4) for k, v in self.deltas.items()},
            "net_wellbeing": round(self.net_wellbeing, 4),
            "regret_risk": round(self.regret_risk, 4),
            "irreversibility": round(self.irreversibility, 4),
            "confidence": round(self.confidence, 4),
            "harmful_dims": list(self.harmful_dims),
            "unknown": self.unknown,
            "evidence": list(self.evidence),
        }


class HumanCausalSimulator:
    """人本因果仿真器：行动前替人算账。"""

    HARM_THRESHOLD = -0.6        # 单维负向冲击越过此值即视为伤害（宪法红线）
    IRREVERSIBLE_GATE = 0.5      # 不可逆度闸门
    REGRET_GATE = 0.6            # 后悔风险闸门

    def __init__(self, empirical: Any = None) -> None:
        """`empirical` 可传 `kernel.causal.CausalModel`，用真实成败调制先验（可为 None）。"""
        self.edges: List[CausalEdge] = []
        self.empirical = empirical

    # ---------------- 构建 ----------------

    def add_edge(self, tag: str, dim: str, effect: float, *,
                 decay: float = 0.5, confidence: float = 0.6,
                 irreversible: bool = False, note: str = "") -> "HumanCausalSimulator":
        if dim not in DIMENSIONS:
            raise ValueError(f"未知人本维度：{dim}（只允许 {DIMENSIONS}）")
        self.edges.append(CausalEdge(tag, dim, effect, decay, confidence, irreversible, note))
        return self

    @classmethod
    def with_defaults(cls, empirical: Any = None) -> "HumanCausalSimulator":
        """内置一组保守的人本先验（宁可高估伤害，不可低估）。"""
        s = cls(empirical)
        # 打扰类
        s.add_edge("notify", DIM_ATTENTION, -0.3, decay=0.2, confidence=0.8,
                   note="推送打断注意力")
        s.add_edge("notify_night", DIM_EMOTION, -0.5, decay=0.4, confidence=0.7,
                   note="深夜打扰影响情绪与睡眠")
        # 代人发声类（不可逆）
        s.add_edge("public_post", DIM_RELATION, -0.4, decay=0.8, confidence=0.6,
                   irreversible=True, note="以用户名义公开发言，覆水难收")
        s.add_edge("send_message", DIM_RELATION, -0.2, decay=0.7, confidence=0.6,
                   irreversible=True, note="消息发出不可撤回")
        # 花钱类
        s.add_edge("spend", DIM_MONEY, -0.5, decay=0.1, confidence=0.9,
                   irreversible=True, note="支出不可逆")
        # 替人决策类（削自主权）
        s.add_edge("auto_decide", DIM_AUTONOMY, -0.7, decay=0.6, confidence=0.7,
                   note="替人做决定，长期削弱自主性")
        s.add_edge("ask_first", DIM_AUTONOMY, +0.4, decay=0.5, confidence=0.8,
                   note="先问后做，交还控制权")
        # 省时省力类（正向）
        s.add_edge("automate_chore", DIM_TIME, +0.6, decay=0.6, confidence=0.7,
                   note="替人干杂活省时间")
        s.add_edge("summarize", DIM_ATTENTION, +0.4, decay=0.4, confidence=0.7,
                   note="压缩信息降低认知负荷")
        s.add_edge("teach", DIM_AUTONOMY, +0.5, decay=0.7, confidence=0.6,
                   note="教会用户，增强自主能力")
        return s

    # ---------------- 推演 ----------------

    def _empirical_modulate(self, tag: str, context: str) -> Optional[float]:
        """用经验成功率调制先验强度：成功率高 → 负面冲击打折、正面冲击放大。

        经验模型样本不足会返回 success_rate=None，此时**不调制**（诚实：没数据就别装有）。
        """
        if self.empirical is None:
            return None
        try:
            r = self.empirical.effect_of(context, tag) or {}
        except Exception:  # noqa: BLE001
            return None
        rate = r.get("success_rate")
        if rate is None:
            return None
        # 0.5 成功率 → 系数 1.0；成功率越高系数越小（越不容易搞砸）
        return max(0.5, min(1.5, 1.5 - float(rate)))

    def simulate(self, tags: List[str], *, magnitude: float = 1.0,
                 horizon: int = 3, context: str = "default") -> HumanImpact:
        """推演一组动作标签的人本影响。tags 无匹配边时返回 unknown=True。"""
        deltas: Dict[str, float] = {d: 0.0 for d in DIMENSIONS}
        confs: List[float] = []
        evidence: List[str] = []
        irrev_hits: List[float] = []
        matched = 0

        for tag in tags:
            mod = self._empirical_modulate(tag, context)
            for e in self.edges:
                if e.tag != tag:
                    continue
                matched += 1
                eff = e.horizon_effect(magnitude, horizon)
                if mod is not None and eff < 0:
                    eff *= mod           # 有经验数据：干得好的事，负面冲击打折
                    evidence.append(f"{tag}→{e.dim}: 经验调制系数 {mod:.2f}")
                deltas[e.dim] += eff
                confs.append(e.confidence)
                if e.irreversible:
                    irrev_hits.append(e.confidence)
                evidence.append(
                    f"{tag}→{e.dim}: {eff:+.3f}（先验 {e.effect:+.2f} × 幅度 {magnitude:.2f}"
                    f" × {horizon} 期衰减 {e.decay}，置信 {e.confidence:.2f}）"
                    + (f"｜{e.note}" if e.note else "")
                )

        if matched == 0:
            return HumanImpact(deltas=deltas, unknown=True, confidence=0.0,
                               evidence=[f"无匹配先验边（tags={tags}），不瞎判（理念6）"])

        net = sum(deltas[d] * DIM_WEIGHTS[d] for d in DIMENSIONS)
        harmful = [d for d in DIMENSIONS if deltas[d] <= self.HARM_THRESHOLD]
        confidence = sum(confs) / len(confs)
        irreversibility = max(irrev_hits) if irrev_hits else 0.0

        # 后悔风险 = 负向冲击量 × 不确定度 × (1 + 不可逆度)
        neg = -sum(min(0.0, deltas[d]) * DIM_WEIGHTS[d] for d in DIMENSIONS)
        regret = min(1.0, (neg / 6.0) * (1.6 - confidence) * (1.0 + irreversibility))

        return HumanImpact(deltas=deltas, net_wellbeing=net, regret_risk=regret,
                           irreversibility=irreversibility, confidence=confidence,
                           harmful_dims=harmful, evidence=evidence)

    def counterfactual(self, tags: List[str], alt_tags: Optional[List[str]] = None,
                       **kw) -> Dict[str, Any]:
        """反事实对照：do(tags) vs do(alt_tags 或 什么都不做)。"""
        a = self.simulate(tags, **kw)
        b = self.simulate(alt_tags or [], **kw)
        better = a.net_wellbeing - b.net_wellbeing
        return {
            "action": a.to_dict(),
            "alternative": b.to_dict(),
            "wellbeing_delta": round(better, 4),
            "recommendation": "do_action" if better > 0 else "do_alternative",
            "note": "此为先验结构因果模型推演，非已证因果；置信见各自 confidence 字段",
        }

    def verdict(self, impact: HumanImpact) -> Dict[str, Any]:
        """把推演转成可执行判决（供 action_arbiter / 紧急制动消费）。"""
        if impact.unknown:
            return {"verdict": NEEDS_APPROVAL,
                    "reason": "无人本先验可依，未知即需人审（不默认放行）"}
        if impact.harmful_dims:
            return {"verdict": DENY,
                    "reason": f"人本维度 {impact.harmful_dims} 越过伤害阈值 "
                              f"{self.HARM_THRESHOLD}，宪法 no_harm 红线不可覆盖"}
        if impact.irreversibility >= self.IRREVERSIBLE_GATE:
            return {"verdict": NEEDS_APPROVAL,
                    "reason": f"不可逆度 {impact.irreversibility:.2f} ≥ "
                              f"{self.IRREVERSIBLE_GATE}，宪法 reversibility 要求人审"}
        if impact.regret_risk >= self.REGRET_GATE:
            return {"verdict": NEEDS_APPROVAL,
                    "reason": f"后悔风险 {impact.regret_risk:.2f} ≥ {self.REGRET_GATE}，先问再做"}
        if impact.net_wellbeing < 0:
            return {"verdict": NEEDS_APPROVAL,
                    "reason": f"净人本福祉为负（{impact.net_wellbeing:+.2f}），不替人做亏本决定"}
        return {"verdict": ALLOW,
                "reason": f"净人本福祉 {impact.net_wellbeing:+.2f}，无伤害维度，可执行"}
