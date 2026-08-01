"""L3 价值排序器：多目标冲突时有确定取舍顺序（白皮书 L3）。

默认序（可在宪法层约束下覆盖）：安全 > 准确 > 速度 > 成本。
强制硬约束（safety）不可被任何低优先级目标越过，对应永恒伦理宪法第 1/2 条。
"""
from __future__ import annotations

DEFAULT_ORDER = ["safety", "accuracy", "speed", "cost"]


class ValueHierarchy:
    def __init__(self, order: list[str] = None):
        self.order = list(order) if order else list(DEFAULT_ORDER)

    def rank(self, value: str) -> int:
        return self.order.index(value) if value in self.order else len(self.order)

    def resolve(self, a: str, b: str) -> str:
        """冲突时返回优先级更高（rank 更小）的一方。"""
        return a if self.rank(a) <= self.rank(b) else b

    def permitted(self, action: str, required: list[str]) -> bool:
        """动作 action 是否被 required 中的硬价值盖过。

        若 required 里任一项 rank 高于 action（即更优先），则禁止。
        例：required=['safety'] 时，speed(rank2) 被 safety(rank0) 否决 → False；
            safety 自身 → True。
        """
        return all(self.rank(action) <= self.rank(r) for r in required)
