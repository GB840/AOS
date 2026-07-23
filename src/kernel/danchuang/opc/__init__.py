"""OPC（一人公司）数字组织内核。

5大岗位智能体协作，模拟真实公司运营：
- 产品研发：从需求到上线的完整产品开发
- 市场调研：竞品分析、用户研究、趋势洞察
- 内容营销：文案、设计、视频、社媒全链路
- 客户服务：咨询、售后、反馈、工单
- 财务核算：成本、营收、利润、税务、报表
"""

from .roles import (
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

__all__ = [
    "OPCRole",
    "OPCAgentRole",
    "ProductRDAgent",
    "MarketResearchAgent",
    "ContentMarketingAgent",
    "CustomerServiceAgent",
    "FinanceAgent",
    "create_agent",
    "get_all_roles",
]
