"""L7 生长约束执行器：集中校验派生请求，并在写/联网/花钱时触发审批。

常量与 spawner.py 保持一致（硬编码，不可配置为无限）。
审批触发对应永恒伦理宪法第 2 条「物理行动授权分级」与第 4 条「虚实从属」。
"""
from __future__ import annotations

from .spawner import MAX_GEN, MAX_SIBLINGS, QUOTA_DECAY

# 必须人工审批的动作类型（宪法：高风险操作永久禁止全自动执行）
APPROVAL_REQUIRED = ("write", "network", "spend")


class GrowthGuard:
    def __init__(self, max_gen: int = MAX_GEN, max_siblings: int = MAX_SIBLINGS,
                 quota_decay: float = QUOTA_DECAY):
        self.max_gen = max_gen
        self.max_siblings = max_siblings
        self.quota_decay = quota_decay

    def can_spawn(self, parent_gen: int, sibling_count: int,
                  parent_quota: float) -> tuple[bool, str]:
        if parent_gen + 1 > self.max_gen:
            return False, f"已达最大派生代数 {self.max_gen}"
        if sibling_count >= self.max_siblings:
            return False, f"兄弟数已达 {self.max_siblings}"
        if parent_quota * self.quota_decay <= 0:
            return False, "子代配额耗尽"
        return True, "ok"

    def requires_approval(self, action: str) -> bool:
        """写 / 联网 / 花钱 三类动作必须人工审批。"""
        return action in APPROVAL_REQUIRED
