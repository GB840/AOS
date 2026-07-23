"""行业模板包 —— 针对特定行业的 AI 运营自动化模板。

设计原则：
- 一个行业 = 一套完整闭环：运营官 → 内容生产 → 客服承接 → 数据回流
- 数据驱动：所有决策基于真实的经营数据
- 可定制：模板可按具体店铺调整

当前支持行业：
- restaurant: 餐饮（烧烤店、火锅店、快餐店等）
- retail: 零售（便利店、超市、专卖店等）
- beauty: 美业（美容院、美发店、美甲店等）
- education: 教培（培训机构、工作室等）
"""
from .restaurant.bbq_shop import (
    BBQShopOperator,
    BBQShopContentPipeline,
    BBQShopCustomerService,
    BBQShopDataLoop,
    BBQShopSystem,
    create_bbq_system,
)

__all__ = [
    "BBQShopOperator",
    "BBQShopContentPipeline",
    "BBQShopCustomerService",
    "BBQShopDataLoop",
    "BBQShopSystem",
    "create_bbq_system",
]