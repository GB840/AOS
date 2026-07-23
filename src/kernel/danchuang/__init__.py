"""单创OS（DanchuangOS）：AI一人公司操作系统。

整合 OPC 数字组织内核 + 创业调度引擎 + 多租户隔离 + 行业模板。
"""

from .opc.roles import (
    OPCRole,
    OPCAgentRole,
    ProductRDAgent,
    MarketResearchAgent,
    ContentMarketingAgent,
    CustomerServiceAgent,
    FinanceAgent,
    create_agent,
    get_all_roles,
)
from .engine.startup_engine import StartupEngine
from .engine.goal_decomposer import GoalDecomposer
from .engine.task_scheduler import TaskScheduler
from .tenant.tenant_manager import TenantManager
from .tenant.isolation import TenantDataIsolation
from .tenant.models import Tenant, TenantPlan, TenantAPIKey
from .templates import IndustryType, IndustryTemplate, get_template, list_templates
from .core import DanchuangOS, get_danchuang_os, DanchuangOSStatus

__all__ = [
    # OPC 岗位
    "OPCRole",
    "OPCAgentRole",
    "ProductRDAgent",
    "MarketResearchAgent",
    "ContentMarketingAgent",
    "CustomerServiceAgent",
    "FinanceAgent",
    "create_agent",
    "get_all_roles",
    # 调度引擎
    "StartupEngine",
    "GoalDecomposer",
    "TaskScheduler",
    # 多租户
    "TenantManager",
    "TenantDataIsolation",
    "Tenant",
    "TenantPlan",
    "TenantAPIKey",
    # 行业模板
    "IndustryType",
    "IndustryTemplate",
    "get_template",
    "list_templates",
    # 总入口
    "DanchuangOS",
    "DanchuangOSStatus",
    "get_danchuang_os",
]
