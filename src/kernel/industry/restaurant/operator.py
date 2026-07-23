"""烧烤店 AI 运营官 —— 数据分析与策划引擎。

核心能力：
1. 数据分析：分析菜品销量、会员消费、渠道效果
2. 智能策划：生成内容计划、活动计划、客服重点
3. 决策建议：给出运营建议和行动项

数据流：
    [订单/会员/渠道数据] → [分析引擎] → [策划引擎] → [运营计划]
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import Counter

from .models import ChannelType, MemberLevel, ContentType, ConversationType

logger = logging.getLogger(__name__)


class BBQShopOperator:
    """烧烤店 AI 运营官。
    
    负责：
    1. 分析经营数据（菜品、订单、会员、渠道）
    2. 生成运营计划（内容、活动、客服）
    3. 给出决策建议
    """
    
    def __init__(self, shop_name: str = "烧烤店", shop_id: str = ""):
        self.shop_name = shop_name
        self.shop_id = shop_id or f"bbq_{int(time.time())}"
        self._lock = threading.RLock()
        
        # 数据存储
        self._dishes: Dict[str, Dict] = {}       # 菜品数据
        self._orders: List[Dict] = []            # 订单数据
        self._members: Dict[str, Dict] = {}      # 会员数据
        self._channels: Dict[str, Dict] = {}     # 渠道数据
        self._contents: List[Dict] = []          # 内容数据
        self._conversations: List[Dict] = []     # 对话数据
        
        # 运营计划缓存
        self._today_plan: Optional[Dict] = None
        self._plan_generated_at: str = ""
        
        # 数据持久化路径
        self._data_dir = os.path.join(os.path.dirname(__file__), "data", self.shop_id)
        os.makedirs(self._data_dir, exist_ok=True)
        
        # 自动加载数据
        self._load_data()
    
    # ─────────────────────────────────────────────────────────────
    # 数据接入
    # ─────────────────────────────────────────────────────────────
    
    def add_dish(self, dish: Dict[str, Any]) -> None:
        """添加/更新菜品"""
        with self._lock:
            dish_id = dish.get("id") or f"dish_{len(self._dishes)}"
            dish["id"] = dish_id
            dish["updated_at"] = datetime.now().isoformat()
            self._dishes[dish_id] = dish
    
    def get_dish(self, dish_name: str) -> Optional[Dict]:
        """根据菜品名称获取菜品"""
        with self._lock:
            for dish in self._dishes.values():
                if dish.get("name") == dish_name:
                    return dish
            return None
    
    def update_dish_stock(self, dish_name: str, delta: int) -> None:
        """更新菜品库存"""
        with self._lock:
            for dish in self._dishes.values():
                if dish.get("name") == dish_name:
                    dish["stock"] = dish.get("stock", 0) + delta
                    dish["updated_at"] = datetime.now().isoformat()
                    break
    
    def add_order(self, order: Dict[str, Any]) -> str:
        """添加订单
        
        Args:
            order: 订单数据
            
        Returns:
            订单ID
            
        Raises:
            ValueError: 订单数据不完整
        """
        if not order.get("items"):
            raise ValueError("订单必须包含菜品项")
        
        items = order.get("items", [])
        for item in items:
            if not item.get("dish_name"):
                raise ValueError("每个菜品项必须包含名称")
        
        with self._lock:
            order_id = order.get("id") or f"order_{int(time.time()*1000)}_{os.getpid()}"
            order["id"] = order_id
            order["created_at"] = order.get("created_at") or datetime.now().isoformat()
            self._orders.append(order)
            
            # 更新菜品销量（累计、本周、本月）
            now = datetime.now()
            is_this_week = now.isocalendar()[1]
            is_this_month = now.month
            
            for item in order.get("items", []):
                dish_id = item.get("dish_id")
                if dish_id in self._dishes:
                    dish = self._dishes[dish_id]
                    qty = item.get("quantity", 1)
                    
                    dish["sales_count"] = dish.get("sales_count", 0) + qty
                    
                    # 更新本周销量
                    week_key = f"week_{is_this_week}"
                    dish["sales_week"] = dish.get("sales_week", 0) + qty
                    
                    # 更新本月销量
                    month_key = f"month_{is_this_month}"
                    dish["sales_month"] = dish.get("sales_month", 0) + qty
            
            return order_id

    def add_member(self, member: Dict[str, Any]) -> None:
        """添加/更新会员"""
        with self._lock:
            member_id = member.get("id") or member.get("phone", "")
            member["id"] = member_id
            member["updated_at"] = datetime.now().isoformat()
            
            # 设置首次访问时间（仅当不存在时）
            if "first_visit" not in member or not member["first_visit"]:
                member["first_visit"] = datetime.now().isoformat()
            
            # 如果已有会员记录，保留首次访问时间
            if member_id in self._members:
                existing = self._members[member_id]
                if existing.get("first_visit"):
                    member["first_visit"] = existing["first_visit"]
            
            self._members[member_id] = member
    
    def get_member(self, member_id: str) -> Optional[Dict]:
        """获取会员信息"""
        with self._lock:
            return self._members.get(member_id)
    
    def update_member_points(self, member_id: str, points: int) -> None:
        """更新会员积分"""
        with self._lock:
            if member_id in self._members:
                self._members[member_id]["points"] = \
                    self._members[member_id].get("points", 0) + points
                self._members[member_id]["updated_at"] = datetime.now().isoformat()
    
    def add_channel(self, channel: Dict[str, Any]) -> None:
        """添加/更新渠道"""
        with self._lock:
            channel_type = channel.get("type", "unknown")
            channel["updated_at"] = datetime.now().isoformat()
            self._channels[channel_type] = channel
    
    def add_content(self, content: Dict[str, Any]) -> None:
        """添加内容记录"""
        with self._lock:
            content_id = content.get("id") or f"content_{int(time.time()*1000)}"
            content["id"] = content_id
            content["created_at"] = datetime.now().isoformat()
            self._contents.append(content)
    
    def add_conversation(self, conversation: Dict[str, Any]) -> None:
        """添加对话记录"""
        with self._lock:
            conv_id = conversation.get("id") or f"conv_{int(time.time()*1000)}"
            conversation["id"] = conv_id
            conversation["created_at"] = datetime.now().isoformat()
            self._conversations.append(conversation)
    
    # ─────────────────────────────────────────────────────────────
    # 数据分析
    # ─────────────────────────────────────────────────────────────
    
    def analyze_sales(self, days: int = 7) -> Dict[str, Any]:
        """分析销售数据"""
        with self._lock:
            # 过滤最近N天的订单
            cutoff = datetime.now() - timedelta(days=days)
            recent_orders = [
                o for o in self._orders
                if self._parse_time(o.get("created_at")) >= cutoff
            ]
            
            # 计算核心指标
            total_revenue = sum(o.get("actual_amount", 0) for o in recent_orders)
            order_count = len(recent_orders)
            avg_order = total_revenue / order_count if order_count > 0 else 0
            
            # 菜品销量排名
            dish_sales = Counter()
            for order in recent_orders:
                for item in order.get("items", []):
                    dish_name = item.get("dish_name", "未知")
                    dish_sales[dish_name] += item.get("quantity", 1)
            
            top_dishes = dish_sales.most_common(10)
            low_dishes = dish_sales.most_common()[-5:] if len(dish_sales) >= 5 else []
            
            # 渠道分布
            channel_stats = Counter()
            for order in recent_orders:
                channel = order.get("channel", "offline")
                channel_stats[channel] += order.get("actual_amount", 0)
            
            return {
                "period_days": days,
                "total_revenue": round(total_revenue, 2),
                "order_count": order_count,
                "avg_order_value": round(avg_order, 2),
                "top_dishes": [{"name": d, "sales": s} for d, s in top_dishes],
                "low_dishes": [{"name": d, "sales": s} for d, s in low_dishes],
                "channel_distribution": dict(channel_stats),
                "analysis_time": datetime.now().isoformat(),
            }
    
    def analyze_members(self, days: int = 30) -> Dict[str, Any]:
        """分析会员数据"""
        with self._lock:
            members = list(self._members.values())
            
            if not members:
                return {
                    "total_members": 0,
                    "active_members": 0,
                    "sleeping_members": 0,
                    "active_rate": 0,
                    "analysis": "暂无会员数据"
                }
            
            level_dist = Counter(m.get("level", "normal") for m in members)
            
            active_count = 0
            sleeping_count = 0
            cutoff = datetime.now() - timedelta(days=30)
            
            for m in members:
                last_visit = self._parse_time(m.get("last_visit", ""))
                if last_visit >= cutoff:
                    active_count += 1
                else:
                    sleeping_count += 1
            
            # 高价值会员
            top_members = sorted(
                members,
                key=lambda m: m.get("total_consume", 0),
                reverse=True
            )[:10]
            
            return {
                "total_members": len(members),
                "level_distribution": dict(level_dist),
                "active_members": active_count,
                "sleeping_members": sleeping_count,
                "active_rate": round(active_count / len(members) * 100, 1) if members else 0,
                "top_members": [
                    {"phone": m.get("phone", "")[:3] + "****", 
                     "consume": m.get("total_consume", 0),
                     "visits": m.get("consume_count", 0)}
                    for m in top_members
                ],
                "analysis_time": datetime.now().isoformat(),
            }
    
    def analyze_channels(self, days: int = 7) -> Dict[str, Any]:
        """分析渠道效果"""
        with self._lock:
            cutoff = datetime.now() - timedelta(days=days)
            
            # 按渠道统计
            channel_data = {}
            for order in self._orders:
                if self._parse_time(order.get("created_at")) >= cutoff:
                    channel = order.get("channel", "offline")
                    if channel not in channel_data:
                        channel_data[channel] = {"revenue": 0, "orders": 0}
                    channel_data[channel]["revenue"] += order.get("actual_amount", 0)
                    channel_data[channel]["orders"] += 1
            
            # 计算渠道占比
            total_revenue = sum(c["revenue"] for c in channel_data.values())
            for channel, data in channel_data.items():
                data["avg_order"] = round(data["revenue"] / data["orders"], 2) if data["orders"] > 0 else 0
                data["share"] = round(data["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0
            
            # 找出最佳渠道
            best_channel = max(channel_data.items(), key=lambda x: x[1]["revenue"], default=(None, {}))
            
            return {
                "period_days": days,
                "channels": channel_data,
                "best_channel": best_channel[0],
                "total_revenue": round(total_revenue, 2),
                "analysis_time": datetime.now().isoformat(),
            }
    
    def analyze_content_performance(self, days: int = 7) -> Dict[str, Any]:
        """分析内容效果"""
        with self._lock:
            cutoff = datetime.now() - timedelta(days=days)
            
            # 过滤最近内容
            recent_contents = [
                c for c in self._contents
                if self._parse_time(c.get("created_at")) >= cutoff
            ]
            
            if not recent_contents:
                return {"total": 0, "analysis": "暂无内容数据"}
            
            # 汇总指标
            total_views = sum(c.get("views", 0) for c in recent_contents)
            total_likes = sum(c.get("likes", 0) for c in recent_contents)
            total_conversions = sum(c.get("conversions", 0) for c in recent_contents)
            total_revenue = sum(c.get("revenue", 0) for c in recent_contents)
            
            # 按类型统计
            type_stats = Counter()
            for c in recent_contents:
                type_stats[c.get("type", "unknown")] += 1
            
            # 按渠道统计
            channel_stats = {}
            for c in recent_contents:
                ch = c.get("channel", "unknown")
                if ch not in channel_stats:
                    channel_stats[ch] = {"views": 0, "likes": 0, "conversions": 0}
                channel_stats[ch]["views"] += c.get("views", 0)
                channel_stats[ch]["likes"] += c.get("likes", 0)
                channel_stats[ch]["conversions"] += c.get("conversions", 0)
            
            return {
                "period_days": days,
                "content_count": len(recent_contents),
                "total_views": total_views,
                "total_likes": total_likes,
                "total_conversions": total_conversions,
                "total_revenue": round(total_revenue, 2),
                "conversion_rate": round(total_conversions / total_views * 100, 2) if total_views > 0 else 0,
                "type_distribution": dict(type_stats),
                "channel_performance": channel_stats,
                "analysis_time": datetime.now().isoformat(),
            }
    
    # ─────────────────────────────────────────────────────────────
    # 智能策划
    # ─────────────────────────────────────────────────────────────
    
    def generate_daily_plan(self, force: bool = False) -> Dict[str, Any]:
        """生成每日运营计划"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        with self._lock:
            # 检查是否已生成（在锁内检查，避免竞态）
            if not force and self._today_plan and self._plan_generated_at.startswith(today):
                return self._today_plan
            
            # 1. 数据分析
            sales_analysis = self.analyze_sales(days=7)
            member_analysis = self.analyze_members(days=30)
            channel_analysis = self.analyze_channels(days=7)
            content_analysis = self.analyze_content_performance(days=7)
            
            # 2. 生成内容计划
            content_plans = self._plan_content(sales_analysis, member_analysis, channel_analysis)
            
            # 3. 生成活动计划
            activity_plans = self._plan_activities(sales_analysis, member_analysis)
            
            # 4. 生成客服重点
            service_focus = self._plan_service(member_analysis, content_analysis)
            
            # 5. 汇总
            plan = {
                "id": f"plan_{today}_{self.shop_id}",
                "date": today,
                "shop_name": self.shop_name,
                "shop_id": self.shop_id,
                
                # 分析结果
                "analysis": {
                    "sales": sales_analysis,
                    "members": member_analysis,
                    "channels": channel_analysis,
                    "content": content_analysis,
                },
                
                # 策划结果
                "content_plans": content_plans,
                "activity_plans": activity_plans,
                "service_focus": service_focus,
                
                # 目标
                "targets": {
                    "daily_revenue": round(sales_analysis["total_revenue"] / 7 * 1.1, 2),  # 目标增长10%
                    "new_members": 5,
                    "content_views": 10000,
                    "conversion_rate": round(content_analysis.get("conversion_rate", 0) + 0.5, 2),
                },
                
                "generated_at": datetime.now().isoformat(),
            }
            
            self._today_plan = plan
            self._plan_generated_at = datetime.now().isoformat()
            
            return plan
    
    def _plan_content(self, sales: Dict, members: Dict, channels: Dict) -> List[Dict]:
        """规划内容"""
        plans = []
        today = datetime.now()
        
        # 热门菜品推荐内容
        top_dishes = sales.get("top_dishes", [])[:3]
        if top_dishes:
            for dish in top_dishes:
                plans.append({
                    "channel": "douyin",
                    "type": "video",
                    "topic": f"招牌推荐：{dish['name']}",
                    "hook": f"每天卖出{dish['sales']}份！",
                    "target_time": "18:00",
                    "priority": "high",
                    "dish": dish["name"],
                })
        else:
            plans.append({
                "channel": "douyin",
                "type": "video",
                "topic": "今日推荐菜品",
                "hook": "今天来尝尝我们的招牌菜！",
                "target_time": "18:00",
                "priority": "high",
                "dish": "招牌菜",
            })
        
        # 唤醒沉睡会员内容
        sleeping = members.get("sleeping_members", 0)
        if sleeping > 10:
            plans.append({
                "channel": "wechat",
                "type": "activity",
                "topic": "老顾客专属福利",
                "hook": "好久不见，这里有你的专属优惠",
                "target_time": "11:00",
                "priority": "medium",
                "target_audience": "sleeping_members",
            })
        
        # 渠道优化内容
        best_channel = channels.get("best_channel", "")
        if best_channel and best_channel != "offline":
            plans.append({
                "channel": best_channel,
                "type": "image_text",
                "topic": "今日特惠",
                "hook": "限时抢购，手慢无！",
                "target_time": "12:00",
                "priority": "high",
            })
        
        return plans
    
    def _plan_activities(self, sales: Dict, members: Dict) -> List[Dict]:
        """规划活动"""
        plans = []
        
        # 低销量菜品促销
        low_dishes = sales.get("low_dishes", [])
        for dish in low_dishes[:2]:
            plans.append({
                "type": "discount",
                "target": "all",
                "dish": dish["name"],
                "offer": f"{dish['name']}限时特价",
                "discount_rate": 0.8,
                "expire_days": 3,
            })
        
        # 新会员拉新活动
        new_members = members.get("active_members", 0)
        if new_members < 50:
            plans.append({
                "type": "new_member",
                "target": "new",
                "offer": "新会员首单立减20元",
                "min_spend": 50,
                "expire_days": 7,
            })
        
        return plans
    
    def _plan_service(self, members: Dict, content: Dict) -> List[str]:
        """规划客服重点"""
        focus = []
        
        # 沉睡会员唤醒
        sleeping = members.get("sleeping_members", 0)
        if sleeping > 10:
            focus.append(f"重点唤醒{min(sleeping, 20)}位沉睡会员")
        
        # 高转化渠道跟进
        if content.get("conversion_rate", 0) > 5:
            focus.append("跟进内容咨询客户，提高到店转化")
        
        # 会员服务
        focus.append("处理会员咨询和预订请求")
        focus.append("收集客户反馈，更新菜品推荐")
        
        return focus
    
    # ─────────────────────────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────────────────────────
    
    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        if not time_str:
            return datetime.min
        try:
            return datetime.fromisoformat(time_str)
        except (ValueError, TypeError):
            return datetime.min
    
    def get_report(self) -> Dict[str, Any]:
        """获取运营报告"""
        return {
            "shop_name": self.shop_name,
            "shop_id": self.shop_id,
            "sales_analysis": self.analyze_sales(days=7),
            "member_analysis": self.analyze_members(days=30),
            "channel_analysis": self.analyze_channels(days=7),
            "content_analysis": self.analyze_content_performance(days=7),
            "today_plan": self.generate_daily_plan(),
            "generated_at": datetime.now().isoformat(),
        }
    
    def get_today_order_count(self) -> int:
        """获取今日订单数"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            count = 0
            for order in self._orders:
                created_at = order.get("created_at", "")
                if created_at.startswith(today):
                    count += 1
            return count
    
    def get_today_revenue(self) -> float:
        """获取今日营收"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            revenue = 0
            for order in self._orders:
                created_at = order.get("created_at", "")
                if created_at.startswith(today):
                    revenue += order.get("actual_amount", 0)
            return round(revenue, 2)
    
    # ─────────────────────────────────────────────────────────────
    # 数据持久化
    # ─────────────────────────────────────────────────────────────
    
    def _load_data(self) -> None:
        """从文件加载数据"""
        data_files = {
            "dishes.json": "_dishes",
            "orders.json": "_orders",
            "members.json": "_members",
            "channels.json": "_channels",
            "contents.json": "_contents",
            "conversations.json": "_conversations",
        }
        
        for filename, attr_name in data_files.items():
            filepath = os.path.join(self._data_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        setattr(self, attr_name, data)
                except Exception as e:
                    logger.warning(f"加载数据失败 {filename}: {e}")
    
    def _save_data(self) -> None:
        """保存数据到文件"""
        try:
            os.makedirs(self._data_dir, exist_ok=True)
        except OSError as e:
            logger.warning(f"创建数据目录失败: {e}")
            return

        data_files = {
            "dishes.json": self._dishes,
            "orders.json": self._orders,
            "members.json": self._members,
            "channels.json": self._channels,
            "contents.json": self._contents,
            "conversations.json": self._conversations,
        }

        for filename, data in data_files.items():
            filepath = os.path.join(self._data_dir, filename)
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except (OSError, TypeError, ValueError) as e:
                logger.warning(f"保存数据失败 {filename}: {e}")
    
    def save(self) -> None:
        """手动触发保存"""
        with self._lock:
            self._save_data()
    
    def backup(self) -> str:
        """创建数据备份"""
        backup_dir = os.path.join(self._data_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join(backup_dir, backup_name)
        
        with self._lock:
            backup_data = {
                "shop_name": self.shop_name,
                "shop_id": self.shop_id,
                "dishes": self._dishes,
                "orders": self._orders,
                "members": self._members,
                "channels": self._channels,
                "contents": self._contents,
                "conversations": self._conversations,
                "backup_time": datetime.now().isoformat(),
            }
            
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        return backup_path


# ─────────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────────

_operator: Optional[BBQShopOperator] = None
_operator_lock = threading.Lock()


def get_bbq_operator(shop_name: str = "烧烤店", shop_id: str = "") -> BBQShopOperator:
    """获取烧烤店运营官单例"""
    global _operator
    if _operator is None:
        with _operator_lock:
            if _operator is None:
                _operator = BBQShopOperator(shop_name=shop_name, shop_id=shop_id)
    return _operator