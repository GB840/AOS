"""烧烤店运营数据模型 —— AI 运营闭环的核心数据结构。

数据流：
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   [运营数据] → [AI运营官] → [内容生产] → [客服承接]          │
│       ↑                                           │          │
│       └───────────── 数据回流 ────────────────────┘          │
│                                                              │
└─────────────────────────────────────────────────────────────┘

核心数据实体：
- Dish: 菜品（名称、价格、成本、销量、毛利）
- Order: 订单（时间、桌号、菜品、金额、来源渠道）
- Member: 会员（手机号、等级、消费金额、偏好、标签）
- Channel: 渠道（抖音、美团、大众点评、微信、线下）
- Content: 内容（视频、图文、活动、优惠券）
- Conversation: 对话（咨询、投诉、预订、售后）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from enum import Enum


class ChannelType(Enum):
    """渠道类型"""
    DOUYIN = "douyin"           # 抖音
    MEITUAN = "meituan"         # 美团
    DIANPING = "dianping"       # 大众点评
    WECHAT = "wechat"           # 微信/社群
    OFFLINE = "offline"         # 线下门店
    XIAOHONGSHU = "xiaohongshu" # 小红书
    KUAISHOU = "kuaishou"       # 快手


class MemberLevel(Enum):
    """会员等级"""
    NORMAL = "normal"           # 普通会员
    SILVER = "silver"           # 银卡
    GOLD = "gold"               # 金卡
    PLATINUM = "platinum"       # 铂金
    DIAMOND = "diamond"         # 钻石


class ContentType(Enum):
    """内容类型"""
    VIDEO = "video"             # 短视频
    IMAGE_TEXT = "image_text"   # 图文
    ACTIVITY = "activity"       # 活动
    COUPON = "coupon"           # 优惠券
    LIVE = "live"               # 直播


class ConversationType(Enum):
    """对话类型"""
    CONSULT = "consult"         # 咨询
    RESERVE = "reserve"         # 预订
    COMPLAINT = "complaint"     # 投诉
    AFTER_SALE = "after_sale"   # 售后
    FEEDBACK = "feedback"       # 反馈


# ─────────────────────────────────────────────────────────────
# 核心数据实体
# ─────────────────────────────────────────────────────────────

@dataclass
class Dish:
    """菜品信息"""
    id: str = ""
    name: str = ""              # 菜品名称
    category: str = ""          # 分类：烤串/凉菜/酒水/主食
    price: float = 0.0          # 售价
    cost: float = 0.0           # 成本
    image_url: str = ""         # 图片URL
    description: str = ""       # 描述
    tags: List[str] = field(default_factory=list)  # 标签：招牌/新品/推荐/辣
    sales_count: int = 0        # 累计销量
    sales_week: int = 0         # 本周销量
    sales_month: int = 0        # 本月销量
    rating: float = 4.5         # 评分
    rating_count: int = 0       # 评价数
    is_active: bool = True      # 是否上架
    created_at: str = ""
    updated_at: str = ""
    
    @property
    def profit_margin(self) -> float:
        """毛利率"""
        if self.price <= 0:
            return 0.0
        return (self.price - self.cost) / self.price
    
    @property
    def profit(self) -> float:
        """单份毛利"""
        return self.price - self.cost
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrderItem:
    """订单中的菜品项"""
    dish_id: str = ""
    dish_name: str = ""
    quantity: int = 1
    price: float = 0.0
    subtotal: float = 0.0
    
    def __post_init__(self):
        if self.subtotal == 0:
            self.subtotal = self.price * self.quantity


@dataclass
class Order:
    """订单信息"""
    id: str = ""
    table_number: str = ""      # 桌号
    items: List[OrderItem] = field(default_factory=list)
    total_amount: float = 0.0   # 总金额
    discount: float = 0.0       # 折扣
    actual_amount: float = 0.0  # 实付金额
    channel: str = "offline"    # 来源渠道
    member_id: str = ""         # 会员ID
    member_phone: str = ""      # 会员手机号
    status: str = "completed"   # pending/preparing/completed/cancelled
    created_at: str = ""
    paid_at: str = ""
    rating: int = 0             # 评价（1-5星）
    comment: str = ""           # 评价内容
    
    def __post_init__(self):
        if self.actual_amount == 0:
            self.actual_amount = self.total_amount - self.discount
    
    @property
    def dish_count(self) -> int:
        """菜品数量"""
        return sum(item.quantity for item in self.items)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["items"] = [asdict(item) for item in self.items]
        return data


@dataclass
class Member:
    """会员信息"""
    id: str = ""
    phone: str = ""
    name: str = ""
    level: str = "normal"       # 会员等级
    points: int = 0             # 积分
    balance: float = 0.0        # 余额
    total_consume: float = 0.0  # 累计消费
    consume_count: int = 0      # 消费次数
    first_visit: str = ""       # 首次到店
    last_visit: str = ""        # 最近到店
    favorite_dishes: List[str] = field(default_factory=list)  # 喜好菜品
    tags: List[str] = field(default_factory=list)  # 标签：喜欢辣/不吃蒜/重口
    source: str = ""            # 来源渠道
    notes: str = ""             # 备注
    created_at: str = ""
    updated_at: str = ""
    
    @property
    def avg_consume(self) -> float:
        """客单价"""
        if self.consume_count == 0:
            return 0.0
        return self.total_consume / self.consume_count
    
    @property
    def days_since_last_visit(self) -> int:
        """距离上次到店天数"""
        if not self.last_visit:
            return 999
        try:
            last = datetime.fromisoformat(self.last_visit)
            return (datetime.now() - last).days
        except (ValueError, TypeError):
            return 999
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Channel:
    """渠道信息"""
    type: str = ""
    name: str = ""
    account_id: str = ""        # 账号ID
    fans_count: int = 0         # 粉丝数
    posts_count: int = 0        # 发帖数
    views_month: int = 0        # 本月曝光
    interactions_month: int = 0 # 本月互动
    conversions_month: int = 0  # 本月转化
    revenue_month: float = 0.0  # 本月营收
    last_post_at: str = ""      # 最后发帖时间
    is_active: bool = True
    
    @property
    def conversion_rate(self) -> float:
        """转化率"""
        if self.views_month == 0:
            return 0.0
        return self.conversions_month / self.views_month * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Content:
    """内容信息"""
    id: str = ""
    type: str = "video"         # video/image_text/activity/coupon
    title: str = ""
    content: str = ""           # 正文/脚本
    images: List[str] = field(default_factory=list)  # 图片URL列表
    video_url: str = ""         # 视频URL
    channel: str = ""           # 发布渠道
    status: str = "draft"       # draft/pending/published/expired
    views: int = 0              # 曝光量
    likes: int = 0              # 点赞数
    comments: int = 0           # 评论数
    shares: int = 0             # 分享数
    conversions: int = 0        # 转化数（到店/下单）
    revenue: float = 0.0        # 带来营收
    publish_at: str = ""        # 发布时间
    expire_at: str = ""         # 过期时间
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    
    @property
    def engagement_rate(self) -> float:
        """互动率"""
        if self.views == 0:
            return 0.0
        return (self.likes + self.comments + self.shares) / self.views * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Conversation:
    """对话/咨询记录"""
    id: str = ""
    type: str = "consult"       # consult/reserve/complaint/after_sale
    channel: str = ""
    member_id: str = ""
    member_phone: str = ""
    member_name: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)  # 消息列表
    status: str = "pending"     # pending/processing/resolved/closed
    satisfaction: int = 0       # 满意度（1-5）
    resolution: str = ""        # 解决方案
    handled_by: str = "ai"      # ai/human
    created_at: str = ""
    resolved_at: str = ""
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息"""
        self.messages.append({
            "role": role,  # user/assistant/system
            "content": content,
            "time": datetime.now().isoformat(),
        })
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# 运营数据汇总
# ─────────────────────────────────────────────────────────────

@dataclass
class DailyStats:
    """每日运营数据汇总"""
    date: str = ""
    # 营收数据
    total_revenue: float = 0.0
    order_count: int = 0
    avg_order_value: float = 0.0
    # 客流数据
    customer_count: int = 0
    new_member_count: int = 0
    returning_rate: float = 0.0
    # 渠道数据
    channel_revenue: Dict[str, float] = field(default_factory=dict)
    channel_orders: Dict[str, int] = field(default_factory=dict)
    # 菜品数据
    top_dishes: List[Dict[str, Any]] = field(default_factory=list)
    low_dishes: List[Dict[str, Any]] = field(default_factory=list)
    # 内容数据
    content_views: int = 0
    content_conversions: int = 0
    # 客服数据
    conversations: int = 0
    resolved_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WeeklyReport:
    """周报数据"""
    week_start: str = ""
    week_end: str = ""
    # 核心指标
    total_revenue: float = 0.0
    revenue_change: float = 0.0  # 环比变化
    order_count: int = 0
    order_change: float = 0.0
    # 趋势分析
    daily_trend: List[Dict[str, Any]] = field(default_factory=list)
    peak_days: List[str] = field(default_factory=list)
    peak_hours: List[int] = field(default_factory=list)
    # 渠道分析
    channel_performance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    best_channel: str = ""
    # 菜品分析
    dish_performance: List[Dict[str, Any]] = field(default_factory=list)
    recommended_promotions: List[Dict[str, Any]] = field(default_factory=list)
    # 运营建议
    suggestions: List[str] = field(default_factory=list)
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# 运营决策
# ─────────────────────────────────────────────────────────────

@dataclass
class OperationPlan:
    """运营计划（AI运营官输出）"""
    id: str = ""
    date: str = ""
    
    # 数据分析结果
    analysis: Dict[str, Any] = field(default_factory=dict)
    
    # 内容计划
    content_plans: List[Dict[str, Any]] = field(default_factory=list)
    # 格式：[{
    #     "channel": "douyin",
    #     "type": "video",
    #     "topic": "新品推荐：蒜香烤翅",
    #     "target_time": "18:00",
    #     "priority": "high"
    # }]
    
    # 活动计划
    activity_plans: List[Dict[str, Any]] = field(default_factory=list)
    # 格式：[{
    #     "type": "coupon",
    #     "target": "inactive_members",
    #     "offer": "满100减20",
    #     "expire_days": 7
    # }]
    
    # 客服重点
    service_focus: List[str] = field(default_factory=list)
    
    # 预算分配
    budget_allocation: Dict[str, float] = field(default_factory=dict)
    
    # 预期目标
    targets: Dict[str, Any] = field(default_factory=dict)
    
    created_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)