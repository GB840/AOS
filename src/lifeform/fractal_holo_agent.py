"""L2/L6 分形全息自适应 Agent（自研，对应白皮书 11.10 之 Holo 转化项）。

外部声称：Holo「分形全息 Agent · 3.02× / 98.1%」。
核验结论：❌ 指标伪造（署名/基准均无第三方来源）。
保留能力：分形全息自适应 Agent（自学习 → 自完善 → 自适应）。
自研落地：本模块实现「自学习→自完善→自适应」三阶段闭环 + 分形子节点隔离派生的
骨架；指标（如加速比/准确率）一律由调用方注入，模块本身**不编造任何性能数字**。

诚实分级：②（代码 + 单测可跑）；未做 ③（真任务驱动的全链路端到端验证）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FractalNode:
    """分形子节点：每个隔离执行的子粒子。"""

    node_id: str
    depth: int
    state: Dict[str, Any] = field(default_factory=dict)
    children: List["FractalNode"] = field(default_factory=list)


class FractalHoloAgent:
    """分形全息自适应 Agent。

    三阶段：
    - self_learn：从经验更新内部策略权重（纯增量，可单测）
    - self_improve：在护栏内派生子节点承担子任务（分形）
    - self_adapt：根据环境反馈调整自身参数（不假装万能）
    """

    def __init__(self, max_depth: int = 6, max_children_per_node: int = 4) -> None:
        self.max_depth = max_depth
        self.max_children_per_node = max_children_per_node
        self.strategy: Dict[str, float] = {}
        self.metrics: Dict[str, float] = {}
        self.root = FractalNode(node_id="root", depth=0)

    # 阶段一：自学习
    def self_learn(self, experience: Dict[str, float]) -> Dict[str, float]:
        """用新经验指数滑动更新策略权重（纯函数式，可单测）。"""
        if not experience:
            return dict(self.strategy)
        for k, v in experience.items():
            old = self.strategy.get(k, 0.0)
            # 学习率 0.1 的 EMA
            self.strategy[k] = old * 0.9 + v * 0.1
        return dict(self.strategy)

    # 阶段二：分形派生（自完善）
    def self_improve(self, subtask: str, parent: Optional[FractalNode] = None) -> Optional[FractalNode]:
        """派生一个隔离子节点执行子任务；越界即拒绝（返回 None，不静默成功）。"""
        parent = parent or self.root
        if parent.depth >= self.max_depth:
            return None
        if len(parent.children) >= self.max_children_per_node:
            return None
        child = FractalNode(node_id=f"{parent.node_id}.{len(parent.children)}", depth=parent.depth + 1)
        child.state["subtask"] = subtask
        parent.children.append(child)
        return child

    # 阶段三：自适应
    def self_adapt(self, feedback: Dict[str, float]) -> Dict[str, float]:
        """根据环境反馈调整自身指标基准（不编造提升，只记录真实反馈）。"""
        if not feedback:
            return dict(self.metrics)
        for k, v in feedback.items():
            self.metrics[k] = v  # 直接采用外部注入的真实反馈，不自行放大
        return dict(self.metrics)

    def count_nodes(self, node: Optional[FractalNode] = None) -> int:
        node = node or self.root
        return 1 + sum(self.count_nodes(c) for c in node.children)
