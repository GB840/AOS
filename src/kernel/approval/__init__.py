"""Human-in-the-Loop 审批模块（Task 4）。

通用 ApprovalStore：任何模块（Evolve/WorkflowRunner/Autopilot）都可发起
审批请求，中高风险操作进入 pending 队列等人工确认，审批后从中断处恢复。

入口：
- ApprovalRequest / ApprovalStore / get_approval_store
"""
from .approval_store import (
    ApprovalRequest,
    ApprovalStore,
    get_approval_store,
)

__all__ = [
    "ApprovalRequest",
    "ApprovalStore",
    "get_approval_store",
]
