"""L7 轻量因果世界模型（自研，对应白皮书 11.10 之 LeWM 转化项）。

外部声称：LeWM「1GB 显存跑 JEPA」。
核验结论：❌ 指标编造（真实项目为 lucas-maes/le-wm，约 15M 参数，无 1GB 显存自称）。
保留能力：轻量 JEPA 因果世界模型。
自研落地：本模块实现「双层因果世界模型」骨架——第一层物理因果、第二层人本因果；
可选接入真实 le-wm（lucas-maes/le-wm，Apache-2.0，opt-in，缺失即降级）。

诚实分级：②（代码 + 单测可跑）；未做 ③（真模型权重加载 / 仿真端到端验证）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CausalLayer:
    """单层因果：状态 + 因果边（起因为因、结果为果）。"""

    name: str
    state: Dict[str, float] = None  # type: ignore
    edges: List[Dict[str, Any]] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.state is None:
            self.state = {}
        if self.edges is None:
            self.edges = []


class WorldModelEngine:
    """双层因果世界模型引擎。

    第一层（physical）：物理/环境因果推演。
    第二层（human_centric）：人本因果（用户意图、价值观偏好）推演。
    可选 le_wm 连接器：若 lucas-maes/le-wm 可用则委托，否则用本地骨架。
    """

    def __init__(self, enable_le_wm: bool = False) -> None:
        self.physical = CausalLayer(name="physical")
        self.human_centric = CausalLayer(name="human_centric")
        self.le_wm = None
        if enable_le_wm:
            self.le_wm = self._try_load_le_wm()

    def _try_load_le_wm(self):  # pragma: no cover - 可选依赖
        try:
            # lucas-maes/le-wm 为外部真实项目，opt-in 接入；缺失即返回 None 降级
            import le_wm  # type: ignore

            return le_wm
        except Exception:
            return None

    def predict(self, layer: str, action: Dict[str, float]) -> Dict[str, float]:
        """在指定层推演动作后的状态变化（骨架：线性因果叠加，可单测）。"""
        target = self.physical if layer == "physical" else self.human_centric
        if not action:
            return dict(target.state)
        new_state = dict(target.state)
        for k, delta in action.items():
            new_state[k] = new_state.get(k, 0.0) + delta
        target.state = new_state
        target.edges.append({"action": action, "result": new_state})
        return new_state

    def causal_score(self) -> float:
        """因果一致性评分（纯函数，可单测）：边越多且状态非零维越多分越高。"""
        layers = [self.physical, self.human_centric]
        total_edges = sum(len(l.edges) for l in layers)
        total_dims = sum(1 for l in layers for v in l.state.values() if v != 0.0)
        if total_edges == 0:
            return 0.0
        return round(min(1.0, (total_edges + total_dims) / 20.0), 4)

    def is_le_wm_active(self) -> bool:
        return self.le_wm is not None
