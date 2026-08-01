"""L7 分形派生器：母体按自相似规则生成结构缩微的子体（白皮书 L7）。

子体 = Adapter 实例 + 裁剪状态 + 独立 mem 命名空间。
生长约束硬编码常量（不可配置为无限）：
  MAX_GEN = 3        最大递归派生代数
  QUOTA_DECAY = 1/3  每代资源配额衰减
  MAX_SIBLINGS = 8   单代最大兄弟数
参考：plasma-ai/fractal 递归硬上限（vendor/plasma-ai-fractal，只读借鉴）。
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_GEN: int = 3
QUOTA_DECAY: float = 1.0 / 3.0
MAX_SIBLINGS: int = 8


@dataclass
class FractalNode:
    name: str
    gen: int
    quota: float
    parent: str = ""
    mem_ns: str = ""
    alive: bool = True


class FractalSpawner:
    def __init__(self):
        self.nodes: dict[str, FractalNode] = {}

    def spawn(self, parent_name: str, child_name: str,
              parent_gen: int = 0, parent_quota: float = 1.0) -> FractalNode:
        """按自相似规则派生子体。超出 3 代 / 兄弟超 8 / 配额耗尽 一律拒绝。"""
        if parent_gen + 1 > MAX_GEN:
            raise RuntimeError(f"生长约束：已达最大派生代数 {MAX_GEN}，禁止继续派生")
        siblings = [n for n in self.nodes.values()
                    if n.parent == parent_name and n.alive]
        if len(siblings) >= MAX_SIBLINGS:
            raise RuntimeError(
                f"生长约束：父 {parent_name} 兄弟数已达 {MAX_SIBLINGS}，排队或拒绝")
        child_quota = parent_quota * QUOTA_DECAY
        if child_quota <= 0:
            raise RuntimeError("生长约束：子代配额耗尽，禁止派生")
        node = FractalNode(
            name=child_name,
            gen=parent_gen + 1,
            quota=round(child_quota, 6),
            parent=parent_name,
            mem_ns=f"{parent_name}.{child_name}",
        )
        self.nodes[child_name] = node
        return node

    def kill(self, name: str) -> None:
        """标记子体死亡（芯粒 crash boundary 的对等逻辑：死亡可记录、不影响母体）。"""
        if name in self.nodes:
            self.nodes[name].alive = False
