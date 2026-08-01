"""L4B 多文明价值观插件市场 —— 完全自研核心（生命体OS 白皮书 L4B）。

「千人千面」不能只体现在语气上，必须体现在**取舍**上：
不同用户/地区/行业对「什么更重要」有真实分歧（隐私 vs 便利、速度 vs 严谨、
集体 vs 个体）。本模块让价值观成为**可插拔插件**，而不是硬编码在提示词里。

三条铁律：
1. **宪法红线不可覆盖**：任何插件都不能把「禁止伤害人类 / 禁止欺骗 / 禁止不可逆越权」
   调低——试图覆盖直接拒绝装载（对应永恒伦理宪法）。
2. **冲突显式仲裁**：两个插件对同一维度给出相反权重时，不静默取平均，
   而是产出 ValueConflict 供上层（或人）裁决。
3. **可解释**：任何一次取舍都能回答「因为你装了 X 插件，它把隐私权重设为 0.9」。

与 `kernel/soul/value_hierarchy.py`（L3 安全>准确>速度>成本）的分工：
后者是**本体自身**的固定序；本模块是**面向不同文明/租户**的可插拔覆盖层，
且只能在红线以上的空间里调整。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# 宪法红线：维度 -> 最低权重（任何插件不得低于此值）
CONSTITUTION_REDLINES: Dict[str, float] = {
    "no_harm": 1.0,          # 不伤害人类：满权重，永不可降
    "honesty": 0.9,          # 不欺骗（含不谎报成功）
    "reversibility": 0.8,    # 不可逆动作须审批
    "privacy": 0.5,          # 隐私保护地板值
}

# 可自由调整的价值维度（红线以上空间）
FREE_DIMENSIONS: Tuple[str, ...] = (
    "privacy", "speed", "cost", "rigor", "novelty", "collective", "autonomy",
)


class ValueConflict(RuntimeError):
    """两个价值观插件在同一维度上冲突且无法自动化解。"""

    def __init__(self, dimension: str, a: str, b: str, va: float, vb: float):
        super().__init__(
            f"价值观冲突：维度 {dimension} 上 {a}={va:.2f} 与 {b}={vb:.2f} 分歧过大，需仲裁"
        )
        self.dimension, self.a, self.b, self.va, self.vb = dimension, a, b, va, vb


@dataclass
class ValuePlugin:
    """一份价值观插件：名字 + 各维度权重 + 来源说明。"""

    name: str
    weights: Dict[str, float] = field(default_factory=dict)
    origin: str = "community"          # 来源：官方/社区/租户自定义
    priority: int = 0                  # 同维度冲突时的话语权

    def violates_redline(self) -> List[str]:
        return [d for d, floor in CONSTITUTION_REDLINES.items()
                if d in self.weights and self.weights[d] < floor]

    def to_dict(self) -> dict:
        return {"name": self.name, "weights": dict(self.weights),
                "origin": self.origin, "priority": self.priority}


class ValuesMarket:
    """价值观插件市场：上架、装载、冲突仲裁、有效权重解析。"""

    CONFLICT_THRESHOLD = 0.4      # 同维度分歧超过此值视为冲突

    def __init__(self, conflict_threshold: Optional[float] = None):
        self._catalog: Dict[str, ValuePlugin] = {}
        self._installed: List[str] = []
        self.conflict_threshold = conflict_threshold or self.CONFLICT_THRESHOLD
        self.rejected: List[Tuple[str, List[str]]] = []

    # ---------------------------------------------------------------- 上架
    def publish(self, plugin: ValuePlugin) -> ValuePlugin:
        bad = plugin.violates_redline()
        if bad:
            self.rejected.append((plugin.name, bad))
            raise PermissionError(
                f"插件 {plugin.name} 试图突破宪法红线 {bad}，拒绝上架（红线不可覆盖）")
        unknown = [d for d in plugin.weights
                   if d not in FREE_DIMENSIONS and d not in CONSTITUTION_REDLINES]
        if unknown:
            raise ValueError(f"插件 {plugin.name} 含未知价值维度 {unknown}")
        self._catalog[plugin.name] = plugin
        return plugin

    def catalog(self) -> List[str]:
        return sorted(self._catalog)

    # ---------------------------------------------------------------- 装载
    def install(self, name: str) -> None:
        if name not in self._catalog:
            raise KeyError(f"市场中无插件 {name}")
        if name not in self._installed:
            self._installed.append(name)

    def uninstall(self, name: str) -> bool:
        if name in self._installed:
            self._installed.remove(name)
            return True
        return False

    @property
    def installed(self) -> List[str]:
        return list(self._installed)

    # ---------------------------------------------------------------- 解析
    def conflicts(self) -> List[ValueConflict]:
        """列出所有未化解的冲突（不抛异常版，供 UI 展示）。"""
        found: List[ValueConflict] = []
        for dim in set().union(*[set(self._catalog[n].weights) for n in self._installed]) \
                if self._installed else set():
            vals = [(n, self._catalog[n].weights[dim])
                    for n in self._installed if dim in self._catalog[n].weights]
            if len(vals) < 2:
                continue
            (na, va), (nb, vb) = max(vals, key=lambda x: x[1]), min(vals, key=lambda x: x[1])
            if va - vb > self.conflict_threshold and \
                    self._catalog[na].priority == self._catalog[nb].priority:
                found.append(ValueConflict(dim, na, nb, va, vb))
        return found

    def resolve(self, strict: bool = True) -> Dict[str, float]:
        """解析有效权重表。

        strict=True：存在同优先级重大分歧时抛 ValueConflict（不静默取平均）。
        strict=False：按 priority 高者胜，同优先级取均值（并在 last_notes 记录）。
        """
        cs = self.conflicts()
        if cs and strict:
            raise cs[0]
        eff: Dict[str, float] = dict(CONSTITUTION_REDLINES)
        buckets: Dict[str, List[Tuple[int, float]]] = {}
        for n in self._installed:
            for d, v in self._catalog[n].weights.items():
                buckets.setdefault(d, []).append((self._catalog[n].priority, v))
        for d, lst in buckets.items():
            top = max(p for p, _ in lst)
            vals = [v for p, v in lst if p == top]
            merged = sum(vals) / len(vals)
            floor = CONSTITUTION_REDLINES.get(d)
            eff[d] = max(floor, merged) if floor is not None else merged
        return {k: round(v, 4) for k, v in eff.items()}

    def explain(self, dimension: str) -> str:
        """可解释性：这个维度的权重为什么是这个值。"""
        parts = [f"{n}={self._catalog[n].weights[dimension]:.2f}"
                 f"(pri={self._catalog[n].priority})"
                 for n in self._installed if dimension in self._catalog[n].weights]
        floor = CONSTITUTION_REDLINES.get(dimension)
        base = f"宪法地板={floor:.2f}" if floor is not None else "无宪法地板"
        if not parts:
            return f"维度 {dimension}：无插件涉及，{base}"
        return f"维度 {dimension}：{base}；来自 " + " / ".join(parts)


__all__ = ["ValuePlugin", "ValuesMarket", "ValueConflict",
           "CONSTITUTION_REDLINES", "FREE_DIMENSIONS"]
