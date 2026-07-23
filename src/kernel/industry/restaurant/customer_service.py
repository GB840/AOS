"""烧烤店 AI 客服系统 —— 多渠道承接与转化。

核心能力：
1. 多渠道接入：抖音、美团、大众点评、微信、小红书
2. 智能应答：基于店铺知识库的自动回复
3. 订单转化：预订引导、优惠券推送、会员注册
4. 人工兜底：复杂问题转人工 + 审批闸门

数据流：
    [客户咨询] → [渠道适配] → [意图识别] → [智能应答/转人工]
                              ↓
                        [数据回流] → [运营分析]
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """客户意图类型"""
    INQUIRE_PRICE = "inquire_price"       # 询价
    INQUIRE_MENU = "inquire_menu"         # 问菜单
    RESERVE = "reserve"                   # 预订
    ORDER = "order"                       # 下单
    COMPLAINT = "complaint"               # 投诉
    AFTER_SALE = "after_sale"             # 售后
    FEEDBACK = "feedback"                 # 反馈
    OTHER = "other"                       # 其他


class ResponseStrategy(Enum):
    """响应策略"""
    AUTO_REPLY = "auto_reply"             # 自动回复
    OFFER_COUPON = "offer_coupon"         # 推送优惠券
    GUIDE_RESERVE = "guide_reserve"       # 引导预订
    GUIDE_MEMBER = "guide_member"         # 引导会员
    TRANSFER_HUMAN = "transfer_human"     # 转人工


# ─────────────────────────────────────────────────────────────
# 知识库
# ─────────────────────────────────────────────────────────────

DEFAULT_KNOWLEDGE = {
    "shop_name": "烧烤店",
    "address": "详细地址请私信或查看主页",
    "open_hours": "每天11:00-凌晨2:00",
    "phone": "请私信获取联系方式",
    "avg_price": "人均80元左右",
    "reservation": "支持预订，请告知人数和时间",
    "parking": "门口有停车位，建议提前到店",
    "popular_dishes": [
        {"name": "招牌羊肉串", "price": 5, "desc": "外焦里嫩，每日新鲜"},
        {"name": "秘制烤翅", "price": 8, "desc": "独家秘方，口味一绝"},
        {"name": "蒜蓉生蚝", "price": 12, "desc": "新鲜生蚝，蒜香浓郁"},
        {"name": "烤韭菜", "price": 10, "desc": "爽脆可口，配酒绝配"},
    ],
    "activities": [
        {"name": "新会员福利", "desc": "首单立减20元"},
        {"name": "满减活动", "desc": "满100减20，满200减50"},
    ],
    "faq": {
        "需要预约吗": "建议提前预约，周末和节假日较忙",
        "可以外带吗": "支持外带和外卖，请提前电话联系",
        "有包间吗": "有包间，可容纳10-20人，建议提前预订",
        "能不能开发票": "可以开具发票，请在用餐时告知服务员",
        "有什么优惠": "新会员首单减20元，充值还有额外优惠",
    },
}


# ─────────────────────────────────────────────────────────────
# 意图识别与响应
# ─────────────────────────────────────────────────────────────

INTENT_KEYWORDS = {
    IntentType.INQUIRE_PRICE: ["多少钱", "价格", "人均", "收费", "费用"],
    IntentType.INQUIRE_MENU: ["菜单", "有什么菜", "招牌", "推荐", "吃什么", "好吃的"],
    IntentType.RESERVE: ["预订", "预约", "订位", "订桌", "包间"],
    IntentType.ORDER: ["点菜", "下单", "外卖", "送餐"],
    IntentType.COMPLAINT: ["投诉", "差评", "不满意", "问题", "不好"],
    IntentType.AFTER_SALE: ["退款", "退货", "发票", "售后"],
    IntentType.FEEDBACK: ["建议", "反馈", "意见", "评价"],
}


@dataclass
class ConversationSession:
    """对话会话"""
    session_id: str = ""
    channel: str = ""
    member_id: str = ""
    member_phone: str = ""
    member_name: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    intent: str = ""
    status: str = "active"       # active/transferred/resolved/closed
    satisfaction: int = 0
    resolution: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "time": datetime.now().isoformat(),
        })
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeBase:
    """店铺知识库"""
    shop_name: str = ""
    address: str = ""
    open_hours: str = ""
    phone: str = ""
    avg_price: str = ""
    reservation: str = ""
    parking: str = ""
    popular_dishes: List[Dict] = field(default_factory=list)
    activities: List[Dict] = field(default_factory=list)
    faq: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "KnowledgeBase":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BBQShopCustomerService:
    """烧烤店 AI 客服。
    
    负责：
    1. 多渠道咨询接入
    2. 智能应答
    3. 订单转化引导
    4. 复杂问题转人工
    """
    
    def __init__(self, shop_name: str = "烧烤店"):
        self.shop_name = shop_name
        self._lock = threading.RLock()
        
        # 知识库
        self._knowledge = KnowledgeBase.from_dict(DEFAULT_KNOWLEDGE)
        self._knowledge.shop_name = shop_name
        
        # 会话管理
        self._sessions: Dict[str, ConversationSession] = {}
        self._session_timeout_minutes = 30  # 会话超时时间
        
        # 统计数据
        self._stats = {
            "total_conversations": 0,
            "resolved_conversations": 0,
            "transferred_conversations": 0,
            "avg_response_time": 0.0,
            "satisfaction_avg": 0.0,
        }
        
        # 人工客服回调（可选）
        self._human_transfer_callback: Optional[Callable] = None
    
    def set_knowledge(self, knowledge: Dict[str, Any]) -> None:
        """设置知识库"""
        with self._lock:
            self._knowledge = KnowledgeBase.from_dict(knowledge)
    
    def set_human_transfer_callback(self, callback: Callable) -> None:
        """设置人工转接回调"""
        self._human_transfer_callback = callback
    
    # ─────────────────────────────────────────────────────────────
    # 会话管理
    # ─────────────────────────────────────────────────────────────
    
    def create_session(self, channel: str, member_id: str = "", 
                       member_phone: str = "", member_name: str = "",
                       member_info: Any = None) -> ConversationSession:
        """创建新会话"""
        session_id = f"session_{int(time.time()*1000)}"
        
        if member_info:
            member_phone = member_phone or getattr(member_info, 'phone', '')
            member_name = member_name or getattr(member_info, 'name', '')
        
        session = ConversationSession(
            session_id=session_id,
            channel=channel,
            member_id=member_id,
            member_phone=member_phone,
            member_name=member_name,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        with self._lock:
            self._sessions[session_id] = session
            self._stats["total_conversations"] += 1
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """获取会话（自动检查超时）"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                # 检查超时
                try:
                    updated_at = datetime.fromisoformat(session.updated_at)
                    if (datetime.now() - updated_at).total_seconds() > self._session_timeout_minutes * 60:
                        session.status = "timeout"
                        return None
                except (ValueError, TypeError):
                    pass
            return session
    
    def get_active_session_count(self) -> int:
        """获取活跃会话数"""
        with self._lock:
            count = 0
            now = datetime.now()
            for session in self._sessions.values():
                if session.status == "active":
                    try:
                        updated_at = datetime.fromisoformat(session.updated_at)
                        if (now - updated_at).total_seconds() <= self._session_timeout_minutes * 60:
                            count += 1
                    except (ValueError, TypeError):
                        count += 1
            return count
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        with self._lock:
            expired_ids = []
            now = datetime.now()
            
            for session_id, session in list(self._sessions.items()):
                try:
                    updated_at = datetime.fromisoformat(session.updated_at)
                    if (now - updated_at).total_seconds() > self._session_timeout_minutes * 60:
                        if session.status == "active":
                            session.status = "timeout"
                        expired_ids.append(session_id)
                except (ValueError, TypeError):
                    expired_ids.append(session_id)

            # 限制会话总量，防止内存无限增长（保留最近1000条）
            if len(self._sessions) > 1000:
                sorted_sessions = sorted(
                    self._sessions.items(),
                    key=lambda x: x[1].updated_at or "",
                    reverse=True
                )
                for session_id, _ in sorted_sessions[1000:]:
                    if session_id not in expired_ids:
                        expired_ids.append(session_id)

            for session_id in expired_ids:
                self._sessions.pop(session_id, None)

            return len(expired_ids)
    
    def close_session(self, session_id: str, satisfaction: int = 0, resolution: str = "") -> bool:
        """关闭会话"""
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.status = "closed"
                session.satisfaction = satisfaction
                session.resolution = resolution
                session.updated_at = datetime.now().isoformat()
                self._stats["resolved_conversations"] += 1
                if satisfaction > 0:
                    self._update_satisfaction(satisfaction)
                return True
            return False
    
    # ─────────────────────────────────────────────────────────────
    # 消息处理
    # ─────────────────────────────────────────────────────────────
    
    def handle_message(self, session_id: str, message: str, 
                        requires_approval: bool = False) -> Dict[str, Any]:
        """处理消息"""
        session = self.get_session(session_id)
        if not session:
            return {"error": "会话不存在"}
        
        # 记录用户消息
        session.add_message("user", message)
        
        # 识别意图
        intent = self._detect_intent(message)
        session.intent = intent.value
        
        # 生成响应
        response, strategy = self._generate_response(intent, message, session)
        
        # 检查是否需要转人工
        if strategy == ResponseStrategy.TRANSFER_HUMAN:
            session.status = "transferred"
            self._stats["transferred_conversations"] += 1
            if self._human_transfer_callback:
                self._human_transfer_callback(session, message)
        
        # 检查是否需要审批（敏感响应）
        needs_approval = requires_approval and strategy in [
            ResponseStrategy.OFFER_COUPON,
            ResponseStrategy.GUIDE_MEMBER,
        ]
        
        # 记录响应
        session.add_message("assistant", response)
        
        return {
            "response": response,
            "intent": intent.value,
            "strategy": strategy.value,
            "needs_approval": needs_approval,
            "session_status": session.status,
        }
    
    def _detect_intent(self, message: str) -> IntentType:
        """识别意图"""
        message_lower = message.lower()
        
        for intent, keywords in INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return intent
        
        return IntentType.OTHER
    
    def _generate_response(self, intent: IntentType, message: str, 
                           session: ConversationSession) -> tuple[str, ResponseStrategy]:
        """生成响应"""
        kb = self._knowledge
        
        if intent == IntentType.INQUIRE_PRICE:
            return (
                f"{kb.shop_name}人均消费约{kb.avg_price}，丰俭由人~还有新会员首单减20元的福利哦！",
                ResponseStrategy.GUIDE_MEMBER
            )
        
        elif intent == IntentType.INQUIRE_MENU:
            dishes_str = "\n".join([
                f"• {d['name']}：{d['price']}元/份，{d['desc']}"
                for d in kb.popular_dishes[:4]
            ])
            return (
                f"为您推荐{kb.shop_name}的招牌菜品：\n{dishes_str}\n\n需要预订的话可以告诉我人数和时间哦~",
                ResponseStrategy.GUIDE_RESERVE
            )
        
        elif intent == IntentType.RESERVE:
            return (
                f"好的，请告诉我：\n1. 预计几位用餐？\n2. 预计什么时间到店？\n3. 需要包间吗？\n\n我会为您安排位置~",
                ResponseStrategy.AUTO_REPLY
            )
        
        elif intent == IntentType.ORDER:
            return (
                f"您可以通过美团/大众点评下单，也可以直接电话联系我们。\n\n需要我帮您推送一张{kb.shop_name}的优惠券吗？",
                ResponseStrategy.OFFER_COUPON
            )
        
        elif intent == IntentType.COMPLAINT:
            # 投诉类转人工
            return (
                f"非常抱歉给您带来不好的体验！我会立即为您转接人工客服处理，请稍候...",
                ResponseStrategy.TRANSFER_HUMAN
            )
        
        elif intent == IntentType.AFTER_SALE:
            return (
                f"关于售后问题，我会为您转接人工客服，请稍候...\n\n同时您也可以拨打店铺电话咨询。",
                ResponseStrategy.TRANSFER_HUMAN
            )
        
        elif intent == IntentType.FEEDBACK:
            return (
                f"感谢您的反馈！我们会认真听取您的意见，不断改进。还有其他需要帮助的吗？",
                ResponseStrategy.AUTO_REPLY
            )
        
        else:
            # 默认响应
            for question, answer in kb.faq.items():
                if question in message:
                    return (answer, ResponseStrategy.AUTO_REPLY)
            
            return (
                f"您好！{kb.shop_name}欢迎您~\n\n"
                f"📍 地址：{kb.address}\n"
                f"🕐 营业时间：{kb.open_hours}\n"
                f"💰 人均：{kb.avg_price}\n\n"
                f"请问有什么可以帮您的？可以问我菜单、价格、预订等问题~",
                ResponseStrategy.AUTO_REPLY
            )
    
    # ─────────────────────────────────────────────────────────────
    # 数据回流
    # ─────────────────────────────────────────────────────────────
    
    def get_conversation_stats(self) -> Dict[str, Any]:
        """获取客服统计数据"""
        with self._lock:
            return {
                **self._stats,
                "active_sessions": len([s for s in self._sessions.values() if s.status == "active"]),
                "sessions": [s.to_dict() for s in self._sessions.values()][-10:],  # 最近10条
            }
    
    def get_recent_conversations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近对话"""
        with self._lock:
            sessions = sorted(
                self._sessions.values(),
                key=lambda s: s.updated_at,
                reverse=True
            )[:limit]
            return [s.to_dict() for s in sessions]
    
    def _update_satisfaction(self, satisfaction: int) -> None:
        """更新满意度"""
        # 简单移动平均
        current = self._stats["satisfaction_avg"]
        total = self._stats["resolved_conversations"]
        self._stats["satisfaction_avg"] = (
            (current * (total - 1) + satisfaction) / total
        )
    
    # ─────────────────────────────────────────────────────────────
    # 便捷方法
    # ─────────────────────────────────────────────────────────────
    
    def quick_reply(self, channel: str, message: str, member_id: str = "") -> Dict[str, Any]:
        """快速回复（无状态，适合单次咨询）"""
        session = self.create_session(channel=channel, member_id=member_id)
        result = self.handle_message(session.session_id, message)
        self.close_session(session.session_id)
        # 更新返回的状态
        result["session_status"] = "closed"
        return result


# ─────────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────────

_service: Optional[BBQShopCustomerService] = None
_service_lock = threading.Lock()


def get_customer_service(shop_name: str = "烧烤店") -> BBQShopCustomerService:
    """获取客服系统单例"""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = BBQShopCustomerService(shop_name=shop_name)
    return _service