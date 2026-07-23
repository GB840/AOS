"""烧烤店数据回流机制 —— 三模块数据闭环。

闭环流程：
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   [运营数据] → [AI运营官] → [内容生产] → [客服承接]              │
│       ↑                              │              │            │
│       │                              ↓              ↓            │
│       │                        [内容效果]      [咨询数据]         │
│       │                              │              │            │
│       └──────────────────────────────┴──────────────┘            │
│                           数据回流                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

数据回流内容：
1. 内容效果数据 → 运营官（曝光、转化、营收）
2. 客服咨询数据 → 运营官（咨询量、满意度、热门问题）
3. 会员行为数据 → 运营官（消费、偏好、活跃度）
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DataFlowEvent:
    """数据回流事件"""
    event_type: str = ""        # content_result / conversation_result / member_action
    source: str = ""            # content_pipeline / customer_service / order_system
    timestamp: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    processed: bool = False
    processed_at: str = ""


class BBQShopDataLoop:
    """烧烤店数据回流系统。
    
    负责：
    1. 收集三模块的运营数据
    2. 汇总分析后反馈给运营官
    3. 触发自动化决策
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 事件缓冲区
        self._events: List[DataFlowEvent] = []
        self._max_events = 1000
        
        # 各模块引用（懒加载）
        self._operator = None
        self._content_pipeline = None
        self._customer_service = None
        
        # 回流统计
        self._stats = {
            "total_events": 0,
            "content_events": 0,
            "conversation_events": 0,
            "member_events": 0,
            "last_sync": "",
        }
        
        # 自动同步配置
        self._auto_sync_enabled = False
        self._auto_sync_interval_seconds = 300  # 5分钟自动同步
        self._auto_sync_thread = None
    
    def set_modules(self, operator=None, content_pipeline=None, customer_service=None) -> None:
        """设置模块引用"""
        self._operator = operator
        self._content_pipeline = content_pipeline
        self._customer_service = customer_service
    
    # ─────────────────────────────────────────────────────────────
    # 事件收集
    # ─────────────────────────────────────────────────────────────
    
    def record_content_result(self, content_id: str, result: Dict[str, Any]) -> None:
        """记录内容效果数据"""
        event = DataFlowEvent(
            event_type="content_result",
            source="content_pipeline",
            timestamp=datetime.now().isoformat(),
            data={
                "content_id": content_id,
                "views": result.get("views", 0),
                "likes": result.get("likes", 0),
                "comments": result.get("comments", 0),
                "shares": result.get("shares", 0),
                "conversions": result.get("conversions", 0),
                "revenue": result.get("revenue", 0),
                "channel": result.get("channel", "unknown"),
                "content_type": result.get("type", "unknown"),
            },
        )
        self._add_event(event)
        self._stats["content_events"] += 1
    
    def record_conversation_result(self, session_id: str, result: Dict[str, Any]) -> None:
        """记录客服对话数据"""
        event = DataFlowEvent(
            event_type="conversation_result",
            source="customer_service",
            timestamp=datetime.now().isoformat(),
            data={
                "session_id": session_id,
                "channel": result.get("channel", "unknown"),
                "intent": result.get("intent", "unknown"),
                "satisfaction": result.get("satisfaction", 0),
                "resolution": result.get("resolution", ""),
                "duration": result.get("duration", 0),
                "handled_by": result.get("handled_by", "ai"),
            },
        )
        self._add_event(event)
        self._stats["conversation_events"] += 1
    
    def record_member_action(self, member_id: str, action: Dict[str, Any]) -> None:
        """记录会员行为数据"""
        event = DataFlowEvent(
            event_type="member_action",
            source="order_system",
            timestamp=datetime.now().isoformat(),
            data={
                "member_id": member_id,
                "action_type": action.get("type", "unknown"),
                "amount": action.get("amount", 0),
                "dishes": action.get("dishes", []),
                "channel": action.get("channel", "offline"),
                "source_content": action.get("source_content", ""),  # 来源内容ID
            },
        )
        self._add_event(event)
        self._stats["member_events"] += 1
    
    def _add_event(self, event: DataFlowEvent) -> None:
        """添加事件到缓冲区"""
        with self._lock:
            self._events.append(event)
            self._stats["total_events"] += 1
            
            # 超出限制时清理旧事件
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]
    
    # ─────────────────────────────────────────────────────────────
    # 数据回流处理
    # ─────────────────────────────────────────────────────────────
    
    def sync_to_operator(self) -> Dict[str, Any]:
        """将数据同步到运营官"""
        with self._lock:
            if not self._operator:
                return {"error": "运营官未初始化"}
            
            # 汇总最近事件
            recent_events = self._get_recent_events(hours=24)
            
            # 内容效果汇总
            content_data = self._aggregate_content_events(recent_events)
            
            # 客服数据汇总
            conversation_data = self._aggregate_conversation_events(recent_events)
            
            # 会员行为汇总
            member_data = self._aggregate_member_events(recent_events)
            
            # 同步到运营官
            for content in content_data:
                self._operator.add_content(content)
            
            for conv in conversation_data:
                self._operator.add_conversation(conv)
            
            # 标记事件已处理
            for event in recent_events:
                event.processed = True
                event.processed_at = datetime.now().isoformat()
            
            self._stats["last_sync"] = datetime.now().isoformat()
            
            return {
                "synced_events": len(recent_events),
                "content_records": len(content_data),
                "conversation_records": len(conversation_data),
                "member_records": len(member_data),
                "synced_at": self._stats["last_sync"],
            }
    
    def _get_recent_events(self, hours: int = 24) -> List[DataFlowEvent]:
        """获取最近N小时的事件"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            e for e in self._events
            if datetime.fromisoformat(e.timestamp) >= cutoff and not e.processed
        ]
    
    def _aggregate_content_events(self, events: List[DataFlowEvent]) -> List[Dict]:
        """汇总内容事件"""
        records = []
        for event in events:
            if event.event_type == "content_result":
                records.append({
                    "id": event.data.get("content_id"),
                    "views": event.data.get("views", 0),
                    "likes": event.data.get("likes", 0),
                    "comments": event.data.get("comments", 0),
                    "shares": event.data.get("shares", 0),
                    "conversions": event.data.get("conversions", 0),
                    "revenue": event.data.get("revenue", 0),
                    "channel": event.data.get("channel"),
                    "type": event.data.get("content_type"),
                    "created_at": event.timestamp,
                })
        return records
    
    def _aggregate_conversation_events(self, events: List[DataFlowEvent]) -> List[Dict]:
        """汇总对话事件"""
        records = []
        for event in events:
            if event.event_type == "conversation_result":
                records.append({
                    "id": event.data.get("session_id"),
                    "channel": event.data.get("channel"),
                    "intent": event.data.get("intent"),
                    "satisfaction": event.data.get("satisfaction", 0),
                    "resolution": event.data.get("resolution", ""),
                    "handled_by": event.data.get("handled_by"),
                    "created_at": event.timestamp,
                })
        return records
    
    def _aggregate_member_events(self, events: List[DataFlowEvent]) -> List[Dict]:
        """汇总会员事件"""
        records = []
        for event in events:
            if event.event_type == "member_action":
                records.append({
                    "member_id": event.data.get("member_id"),
                    "action_type": event.data.get("action_type"),
                    "amount": event.data.get("amount", 0),
                    "dishes": event.data.get("dishes", []),
                    "channel": event.data.get("channel"),
                    "source_content": event.data.get("source_content"),
                    "created_at": event.timestamp,
                })
        return records
    
    # ─────────────────────────────────────────────────────────────
    # 自动化决策触发
    # ─────────────────────────────────────────────────────────────
    
    def check_auto_actions(self) -> List[Dict[str, Any]]:
        """检查是否需要自动执行某些操作"""
        actions = []
        
        with self._lock:
            # 获取最近1小时的统计
            recent_events = self._get_recent_events(hours=1)
            
            # 检查内容表现差
            content_events = [e for e in recent_events if e.event_type == "content_result"]
            if content_events:
                avg_conversion = sum(
                    e.data.get("conversions", 0) for e in content_events
                ) / len(content_events)
                
                if avg_conversion < 5:  # 平均转化低于5
                    actions.append({
                        "type": "content_optimize",
                        "reason": "内容转化率偏低",
                        "suggestion": "建议调整内容策略，尝试更热门话题",
                    })
            
            # 检查客服满意度低
            conv_events = [e for e in recent_events if e.event_type == "conversation_result"]
            if conv_events:
                avg_satisfaction = sum(
                    e.data.get("satisfaction", 0) for e in conv_events
                ) / len(conv_events)
                
                if avg_satisfaction < 3:  # 满意度低于3分
                    actions.append({
                        "type": "service_improve",
                        "reason": "客服满意度偏低",
                        "suggestion": "建议增加人工客服介入，优化回复策略",
                    })
        
        return actions
    
    # ─────────────────────────────────────────────────────────────
    # 统计报告
    # ─────────────────────────────────────────────────────────────
    
    def get_stats(self) -> Dict[str, Any]:
        """获取回流统计"""
        with self._lock:
            return {
                **self._stats,
                "pending_events": len([e for e in self._events if not e.processed]),
                "events_last_24h": len(self._get_recent_events(hours=24)),
            }
    
    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近事件列表"""
        with self._lock:
            events = sorted(
                self._events,
                key=lambda e: e.timestamp,
                reverse=True
            )[:limit]
            return [asdict(e) for e in events]
    
    # ─────────────────────────────────────────────────────────────
    # 自动同步
    # ─────────────────────────────────────────────────────────────
    
    def start_auto_sync(self, interval_seconds: int = 300) -> None:
        """启动自动同步线程"""
        if self._auto_sync_thread and self._auto_sync_thread.is_alive():
            return
        
        self._auto_sync_interval_seconds = interval_seconds
        self._auto_sync_enabled = True
        
        def _auto_sync_loop():
            while self._auto_sync_enabled:
                try:
                    self.sync_to_operator()
                    time.sleep(self._auto_sync_interval_seconds)
                except Exception as e:
                    logger.error(f"自动同步失败: {e}")
                    time.sleep(60)  # 出错后等待1分钟重试
        
        self._auto_sync_thread = threading.Thread(target=_auto_sync_loop, daemon=True)
        self._auto_sync_thread.start()
    
    def stop_auto_sync(self) -> None:
        """停止自动同步线程"""
        self._auto_sync_enabled = False
        if self._auto_sync_thread and self._auto_sync_thread.is_alive():
            self._auto_sync_thread.join(timeout=5)


# ─────────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────────

_data_loop: Optional[BBQShopDataLoop] = None
_data_loop_lock = threading.Lock()


def get_data_loop() -> BBQShopDataLoop:
    """获取数据回流系统单例"""
    global _data_loop
    if _data_loop is None:
        with _data_loop_lock:
            if _data_loop is None:
                _data_loop = BBQShopDataLoop()
    return _data_loop