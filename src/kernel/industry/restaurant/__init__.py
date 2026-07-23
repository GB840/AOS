"""餐饮行业模板包。

包含：
- 烧烤店（bbq_shop）
- 更多行业模板待扩展...
"""
from .bbq_shop import (
    BBQShopOperator,
    BBQShopContentPipeline,
    BBQShopCustomerService,
    BBQShopDataLoop,
    BBQShopSystem,
    create_bbq_system,
)
from .models import (
    Dish,
    Order,
    OrderItem,
    Member,
    Channel,
    Content,
    Conversation,
    DailyStats,
    WeeklyReport,
    OperationPlan,
)

__all__ = [
    # 核心模块
    "BBQShopOperator",
    "BBQShopContentPipeline",
    "BBQShopCustomerService",
    "BBQShopDataLoop",
    "BBQShopSystem",
    
    # 数据模型
    "Dish",
    "Order",
    "OrderItem",
    "Member",
    "Channel",
    "Content",
    "Conversation",
    "DailyStats",
    "WeeklyReport",
    "OperationPlan",
    
    # 工厂方法
    "create_bbq_system",
]