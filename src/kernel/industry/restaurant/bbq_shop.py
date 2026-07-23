"""烧烤店 AI 运营闭环系统 - 真正的业务解决方案。

核心价值：
    [AI运营官] ──策划──> [内容生产] ──发布──> [客服承接] ──数据──> [运营官]
    
    运营官分析销售数据 → 制定今日运营计划 → 内容流水线生成多渠道内容
    → 客服根据计划推荐菜品 → 订单数据回流 → 运营官优化策略

一键使用：
    from kernel.industry.restaurant.bbq_shop import create_bbq_system
    
    # 创建完整系统
    system = create_bbq_system("老王烧烤")
    
    # 每日运营（自动完成：计划→内容→发布准备）
    result = system.daily_operation()
    
    # 客服接待（自动根据运营计划推荐）
    response = system.handle_consultation("douyin", "今天有什么优惠？")
    
    # 添加订单（自动记录会员行为）
    order_id = system.add_order({"items": [...], "total_amount": 100})
    
    # 获取智能报告（自动分析趋势）
    report = system.get_report()
"""
from __future__ import annotations

import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import (
    Dish, Order, OrderItem, Member, Channel, Content, Conversation,
    DailyStats, WeeklyReport, OperationPlan,
    ChannelType, MemberLevel, ContentType, ConversationType,
)
from .operator import BBQShopOperator, get_bbq_operator
from .content_pipeline import BBQShopContentPipeline, get_content_pipeline
from .customer_service import BBQShopCustomerService, get_customer_service
from .data_loop import BBQShopDataLoop, get_data_loop

logger = logging.getLogger(__name__)


class BBQShopSystem:
    """烧烤店 AI 运营系统 - 真正的业务闭环。
    
    核心能力：
    1. 智能运营：基于数据分析的自动运营计划生成
    2. 内容营销：多渠道内容自动生产与发布准备
    3. 智能客服：基于运营计划的个性化推荐与服务
    4. 数据闭环：全链路数据回流与智能优化
    5. 业务监控：实时订单监控与异常预警
    """
    
    def __init__(self, shop_name: str = "烧烤店", shop_id: str = ""):
        self.shop_name = shop_name
        
        # 初始化运营官
        self.operator = BBQShopOperator(shop_name=shop_name, shop_id=shop_id)
        
        # 同步运营官生成的 shop_id
        self.shop_id = self.operator.shop_id
        
        # 添加默认菜品（带真实业务数据）
        self._init_default_dishes()
        
        # 初始化内容流水线（与运营官关联）
        self.content_pipeline = BBQShopContentPipeline(shop_name=shop_name)
        self.content_pipeline.set_shop_info({
            "shop_name": shop_name,
            "avg_price": 80,
            "years": 5,
        })
        
        # 初始化客服系统（与运营官共享数据）
        self.customer_service = BBQShopCustomerService(shop_name=shop_name)
        self.customer_service.set_knowledge({
            "shop_name": shop_name,
            "operating_hours": "11:00-23:00",
            "address": "市中心商业街88号",
            "phone": "138-8888-8888",
        })
        
        # 初始化数据回流（连接所有模块）
        self.data_loop = BBQShopDataLoop()
        self.data_loop.set_modules(
            operator=self.operator,
            content_pipeline=self.content_pipeline,
            customer_service=self.customer_service,
        )
        
        # 运营状态
        self._today_plan = None
        self._today_contents = []
        self._auto_sync_thread = None
        self._auto_sync_running = False
        
        logger.info(f"✅ 烧烤店 AI 运营系统创建完成: {shop_name}")
    
    def _init_default_dishes(self):
        """初始化默认菜品（带真实业务数据）"""
        dishes = [
            {"name": "招牌羊肉串", "category": "烤串", "price": 5.0, "cost": 2.5, 
             "tags": ["招牌", "必点"], "sales_count": 2800, "stock": 500},
            {"name": "秘制烤翅", "category": "烤串", "price": 8.0, "cost": 3.5, 
             "tags": ["推荐", "人气"], "sales_count": 1800, "stock": 300},
            {"name": "蒜蓉生蚝", "category": "海鲜", "price": 12.0, "cost": 5.0, 
             "tags": ["海鲜", "限量"], "sales_count": 1200, "stock": 100},
            {"name": "炭烤羊排", "category": "烧烤", "price": 68.0, "cost": 30.0, 
             "tags": ["招牌", "聚餐"], "sales_count": 800, "stock": 50},
            {"name": "拍黄瓜", "category": "凉菜", "price": 10.0, "cost": 3.0, 
             "tags": ["爽口", "解腻"], "sales_count": 1500, "stock": 200},
            {"name": "锡纸金针菇", "category": "素菜", "price": 15.0, "cost": 4.0, 
             "tags": ["素菜", "下饭"], "sales_count": 900, "stock": 150},
            {"name": "麻辣小龙虾", "category": "海鲜", "price": 88.0, "cost": 45.0, 
             "tags": ["季节限定", "热销"], "sales_count": 600, "stock": 80},
            {"name": "啤酒", "category": "酒水", "price": 8.0, "cost": 3.5, 
             "tags": ["畅饮"], "sales_count": 5000, "stock": 1000},
        ]
        for dish in dishes:
            self.operator.add_dish(dish)
    
    # ─────────────────────────────────────────────────────────────
    # 核心闭环：智能运营
    # ─────────────────────────────────────────────────────────────
    
    def daily_operation(self) -> Dict[str, Any]:
        """一键执行每日运营闭环。
        
        完整流程：
        1. 运营官分析数据（销售、会员、渠道）
        2. 生成今日运营计划（内容计划、活动计划、客服重点）
        3. 内容流水线根据计划生成多渠道内容
        4. 更新客服知识库（新品、活动、优惠）
        5. 数据回流同步
        
        Returns:
            完整的运营结果
        """
        logger.info(f"🚀 开始每日运营: {self.shop_name}")
        
        # 1. 生成运营计划
        plan = self.operator.generate_daily_plan()
        self._today_plan = plan
        logger.info(f"📋 运营计划生成完成: {plan['id']}")
        
        # 2. 生成今日内容（多渠道）
        contents = self.content_pipeline.generate_from_plan(plan)
        self._today_contents = contents
        logger.info(f"📝 内容生成完成: {len(contents)}条")
        
        # 3. 更新客服知识库（让客服知道今日活动）
        self._update_customer_service_knowledge(plan)
        logger.info(f"🔄 客服知识库已更新")
        
        # 4. 保存运营计划
        self.operator.save()
        
        # 5. 数据回流同步
        sync_result = self.data_loop.sync_to_operator()
        
        # 6. 生成运营摘要报告
        summary = self._generate_operation_summary(plan, contents)
        
        return {
            "plan": plan,
            "contents_generated": len(contents),
            "contents": [c.to_dict() for c in contents],
            "sync_result": sync_result,
            "summary": summary,
            "executed_at": datetime.now().isoformat(),
        }
    
    def _update_customer_service_knowledge(self, plan: Dict[str, Any]):
        """根据运营计划更新客服知识库"""
        # 更新今日活动
        activities = plan.get("activity_plans", [])
        if activities:
            activity_text = "\n".join([
                f"- {act['name']}: {act['description']}" 
                for act in activities if act.get("name") and act.get("description")
            ])
            if activity_text:
                self.customer_service.set_knowledge({
                    "today_activities": activity_text,
                })
        
        # 更新今日推荐菜品
        content_plans = plan.get("content_plans", [])
        recommended_dishes = []
        for cp in content_plans:
            if cp.get("dish"):
                recommended_dishes.append(cp["dish"])
        
        if recommended_dishes:
            self.customer_service.set_knowledge({
                "today_recommendations": recommended_dishes,
            })
    
    def _generate_operation_summary(self, plan: Dict[str, Any], contents: List) -> Dict[str, Any]:
        """生成运营摘要报告"""
        analysis = plan.get("analysis", {})
        targets = plan.get("targets", {})
        
        summary = {
            "shop_name": self.shop_name,
            "date": plan.get("date", ""),
            
            "analysis_summary": {
                "total_revenue_7d": analysis.get("sales", {}).get("total_revenue", 0),
                "order_count_7d": analysis.get("sales", {}).get("order_count", 0),
                "new_members_30d": analysis.get("members", {}).get("new_members", 0),
                "active_members_30d": analysis.get("members", {}).get("active_members", 0),
                "best_channel": analysis.get("channels", {}).get("best_channel", "-"),
            },
            
            "targets": {
                "daily_revenue": targets.get("daily_revenue", 0),
                "new_members": targets.get("new_members", 0),
                "content_views": targets.get("content_views", 0),
            },
            
            "content_summary": {
                "total": len(contents),
                "by_channel": {},
            },
        }
        
        # 按渠道统计内容
        for c in contents:
            channel = c.channel
            summary["content_summary"]["by_channel"][channel] = \
                summary["content_summary"]["by_channel"].get(channel, 0) + 1
        
        return summary
    
    # ─────────────────────────────────────────────────────────────
    # 核心闭环：智能客服
    # ─────────────────────────────────────────────────────────────
    
    def handle_consultation(self, channel: str, message: str, 
                            member_id: str = "") -> Dict[str, Any]:
        """一键处理客户咨询（完整闭环）。
        
        流程：
        1. 创建/获取会话
        2. 智能识别意图（菜单咨询、价格咨询、预订、投诉等）
        3. 根据运营计划提供个性化回复
        4. 记录对话到数据回流
        5. 更新会员画像
        
        Args:
            channel: 渠道（douyin/meituan/wechat/offline等）
            message: 客户消息
            member_id: 会员ID（可选）
        
        Returns:
            响应结果（包含回复内容、推荐菜品、会员信息等）
        """
        # 1. 获取会员信息（如果有）
        member_info = None
        if member_id:
            member_info = self.operator.get_member(member_id)
        
        # 2. 创建会话
        session = self.customer_service.create_session(
            channel=channel, 
            member_id=member_id,
            member_info=member_info,
        )
        
        # 3. 处理消息（智能路由）
        result = self.customer_service.handle_message(session.session_id, message)
        
        # 4. 记录到数据回流
        self.data_loop.record_conversation_result(session.session_id, result)
        
        # 5. 如果是下单相关，更新会员行为
        if result.get("intent") in ["order", "booking", "recommend"]:
            if member_id:
                self.data_loop.record_member_action(member_id, {
                    "type": result["intent"],
                    "channel": channel,
                    "message": message,
                    "response": result.get("response", "")[:50],
                })
        
        return result
    
    def handle_order(self, channel: str, items: List[Dict], 
                     member_id: str = "", phone: str = "") -> Dict[str, Any]:
        """处理订单（智能推荐+库存检查）。
        
        流程：
        1. 检查库存
        2. 智能推荐搭配菜品
        3. 计算总价和优惠
        4. 创建订单
        5. 更新会员积分
        6. 记录到数据回流
        
        Args:
            channel: 渠道
            items: 订单商品列表
            member_id: 会员ID
            phone: 手机号
        
        Returns:
            订单结果
        """
        # 1. 检查库存
        stock_check = self._check_stock(items)
        if stock_check.get("out_of_stock"):
            return {
                "success": False,
                "error": f"以下商品库存不足: {', '.join(stock_check['out_of_stock'])}",
            }
        
        # 2. 智能推荐搭配
        recommendations = self._recommend_combo(items)
        
        # 3. 计算总价
        total_amount = 0
        order_items = []
        for item in items:
            dish_name = item.get("dish_name")
            quantity = item.get("quantity", 1)
            dish = self.operator.get_dish(dish_name)
            
            if dish:
                price = dish["price"] * quantity
                total_amount += price
                order_items.append({
                    "dish_name": dish_name,
                    "quantity": quantity,
                    "price": dish["price"],
                    "subtotal": price,
                })
        
        # 4. 会员优惠
        discount = 0
        if member_id:
            member = self.operator.get_member(member_id)
            if member:
                discount = self._calculate_member_discount(member, total_amount)
        
        actual_amount = max(0, total_amount - discount)
        
        # 5. 创建订单
        order_data = {
            "items": order_items,
            "total_amount": total_amount,
            "actual_amount": actual_amount,
            "discount": discount,
            "channel": channel,
            "member_id": member_id,
            "member_phone": phone,
        }
        
        order_id = self.operator.add_order(order_data)
        
        # 6. 更新库存
        self._update_stock(items)
        
        # 7. 更新会员积分
        if member_id:
            self._update_member_points(member_id, actual_amount)
        
        # 8. 记录到数据回流
        if member_id:
            self.data_loop.record_member_action(member_id, {
                "type": "order",
                "amount": actual_amount,
                "items": [i["dish_name"] for i in items],
                "channel": channel,
            })
        
        return {
            "success": True,
            "order_id": order_id,
            "total_amount": total_amount,
            "discount": discount,
            "actual_amount": actual_amount,
            "recommendations": recommendations,
            "items": order_items,
            "created_at": datetime.now().isoformat(),
        }
    
    def _check_stock(self, items: List[Dict]) -> Dict[str, Any]:
        """检查库存"""
        out_of_stock = []
        low_stock = []
        
        for item in items:
            dish_name = item.get("dish_name")
            quantity = item.get("quantity", 1)
            dish = self.operator.get_dish(dish_name)
            
            if dish and dish.get("stock") is not None:
                if dish["stock"] < quantity:
                    out_of_stock.append(dish_name)
                elif dish["stock"] < quantity + 10:
                    low_stock.append(dish_name)
        
        return {
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
        }
    
    def _recommend_combo(self, items: List[Dict]) -> List[str]:
        """智能推荐搭配"""
        ordered_dishes = [item.get("dish_name") for item in items]
        
        # 推荐逻辑
        recommendations = []
        
        # 如果点了肉串，推荐凉菜和解腻饮品
        meat_dishes = ["招牌羊肉串", "秘制烤翅", "炭烤羊排"]
        if any(d in ordered_dishes for d in meat_dishes):
            if "拍黄瓜" not in ordered_dishes:
                recommendations.append("搭配拍黄瓜解腻")
            if "啤酒" not in ordered_dishes:
                recommendations.append("搭配啤酒畅饮")
        
        # 如果点了海鲜，推荐素菜
        seafood_dishes = ["蒜蓉生蚝", "麻辣小龙虾"]
        if any(d in ordered_dishes for d in seafood_dishes):
            if "锡纸金针菇" not in ordered_dishes:
                recommendations.append("搭配锡纸金针菇")
        
        return recommendations
    
    def _calculate_member_discount(self, member: Dict, total_amount: float) -> float:
        """计算会员优惠"""
        level = member.get("level", "normal")
        if level == "vip" or level == "VIP":
            return total_amount * 0.15
        elif level == "gold" or level == "GOLD":
            return total_amount * 0.10
        elif level == "silver" or level == "SILVER":
            return total_amount * 0.05
        return 0
    
    def _update_stock(self, items: List[Dict]) -> None:
        """更新库存"""
        for item in items:
            dish_name = item.get("dish_name")
            quantity = item.get("quantity", 1)
            self.operator.update_dish_stock(dish_name, -quantity)
    
    def _update_member_points(self, member_id: str, amount: float) -> None:
        """更新会员积分"""
        points = int(amount)
        self.operator.update_member_points(member_id, points)
    
    # ─────────────────────────────────────────────────────────────
    # 核心闭环：智能分析与报告
    # ─────────────────────────────────────────────────────────────
    
    def get_report(self) -> Dict[str, Any]:
        """获取完整运营报告。
        
        包含：
        1. 销售分析（7日趋势、热销菜品、渠道分布）
        2. 会员分析（新增、活跃、沉睡）
        3. 内容分析（发布量、阅读量、转化率）
        4. 运营建议（基于数据的智能优化建议）
        """
        report = self.operator.get_report()
        
        # 添加智能建议
        report["smart_suggestions"] = self._generate_smart_suggestions(report)
        
        return report
    
    def _generate_smart_suggestions(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成智能运营建议"""
        suggestions = []
        sales = report.get("sales_analysis", {})
        members = report.get("member_analysis", {})
        
        # 销售建议
        total_revenue = sales.get("total_revenue", 0)
        if total_revenue > 0:
            avg_order = sales.get("avg_order_value", 0)
            if avg_order < 50:
                suggestions.append({
                    "type": "sales",
                    "priority": "high",
                    "title": "提升客单价",
                    "suggestion": "当前客单价偏低，建议推出套餐组合或加购活动",
                    "action": "查看运营计划中的活动策划",
                })
        
        # 会员建议
        sleeping_members = members.get("sleeping_members", 0)
        if sleeping_members > 20:
            suggestions.append({
                "type": "member",
                "priority": "high",
                "title": "唤醒沉睡会员",
                "suggestion": f"发现 {sleeping_members} 位沉睡会员，建议发送专属优惠券",
                "action": "使用内容流水线生成会员唤醒内容",
            })
        
        # 菜品建议
        low_dishes = sales.get("low_dishes", [])
        if low_dishes:
            suggestions.append({
                "type": "product",
                "priority": "medium",
                "title": "优化滞销菜品",
                "suggestion": f"以下菜品销量较低：{', '.join(d['name'] for d in low_dishes)}",
                "action": "考虑调整价格或推出促销活动",
            })
        
        # 渠道建议
        channel_dist = sales.get("channel_distribution", {})
        if channel_dist:
            best_channel = max(channel_dist, key=channel_dist.get, default="")
            suggestions.append({
                "type": "channel",
                "priority": "medium",
                "title": "重点投放渠道",
                "suggestion": f"{best_channel} 渠道效果最好，建议加大投放力度",
                "action": "查看内容计划中的渠道优化策略",
            })
        
        return suggestions
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取实时数据仪表盘。
        
        适合展示在大屏或管理后台。
        """
        return {
            "shop_name": self.shop_name,
            "timestamp": datetime.now().isoformat(),
            
            "realtime": {
                "today_orders": self.operator.get_today_order_count(),
                "today_revenue": self.operator.get_today_revenue(),
                "active_sessions": self.customer_service.get_active_session_count(),
                "pending_contents": len(self._today_contents),
            },
            
            "summary": self.get_report(),
        }
    
    # ─────────────────────────────────────────────────────────────
    # 数据回流与同步
    # ─────────────────────────────────────────────────────────────
    
    def sync_data(self) -> Dict[str, Any]:
        """手动触发数据回流同步"""
        return self.data_loop.sync_to_operator()
    
    def start_auto_sync(self, interval_seconds: int = 300) -> None:
        """启动自动数据回流同步"""
        if self._auto_sync_running:
            return
        
        self._auto_sync_running = True
        
        def sync_loop():
            while self._auto_sync_running:
                try:
                    self.sync_data()
                    logger.debug("自动数据同步完成")
                except Exception as e:
                    logger.error(f"自动数据同步失败: {e}")
                time.sleep(interval_seconds)
        
        self._auto_sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._auto_sync_thread.start()
        logger.info(f"✅ 自动数据同步已启动（每{interval_seconds}秒）")
    
    def stop_auto_sync(self) -> None:
        """停止自动数据回流同步"""
        self._auto_sync_running = False
        logger.info("⏹️ 自动数据同步已停止")
    
    # ─────────────────────────────────────────────────────────────
    # 数据管理
    # ─────────────────────────────────────────────────────────────
    
    def save_data(self) -> None:
        """保存所有数据到文件"""
        self.operator.save()
    
    def backup_data(self) -> str:
        """创建数据备份"""
        return self.operator.backup()
    
    def add_dish(self, dish_data: Dict[str, Any]) -> None:
        """添加菜品"""
        self.operator.add_dish(dish_data)
    
    def add_member(self, member_data: Dict[str, Any]) -> None:
        """添加会员"""
        self.operator.add_member(member_data)
    
    def update_dish_stock(self, dish_name: str, delta: int) -> None:
        """更新菜品库存"""
        self.operator.update_dish_stock(dish_name, delta)
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        return self.customer_service.cleanup_expired_sessions()
    
    # ─────────────────────────────────────────────────────────────
    # 内容管理
    # ─────────────────────────────────────────────────────────────
    
    def generate_content(self, topic: str, channel: str = "douyin", 
                         content_type: str = "video") -> Dict[str, Any]:
        """手动生成内容"""
        content = self.content_pipeline.generate_single(topic, channel, content_type)
        return content.to_dict() if content else {"error": "内容生成失败"}
    
    def get_today_contents(self) -> List[Dict]:
        """获取今日生成的内容"""
        return [c.to_dict() for c in self._today_contents]
    
    def publish_content(self, content_id: str, channel: str) -> Dict[str, Any]:
        """发布内容到指定渠道"""
        for content in self._today_contents:
            if content.id == content_id:
                # 记录发布状态
                content.status = "published"
                content.published_at = datetime.now().isoformat()
                
                # 记录到数据回流
                self.data_loop.record_content_result(content_id, {
                    "status": "published",
                    "channel": channel,
                    "published_at": content.published_at,
                })
                
                return {
                    "success": True,
                    "content_id": content_id,
                    "channel": channel,
                    "published_at": content.published_at,
                }
        
        return {"success": False, "error": "内容不存在"}


# ─────────────────────────────────────────────────────────────
# 工厂方法
# ─────────────────────────────────────────────────────────────

def create_bbq_system(shop_name: str = "烧烤店", shop_id: str = "") -> BBQShopSystem:
    """创建烧烤店 AI 运营系统（一键入口）。
    
    使用示例：
        # 创建系统
        system = create_bbq_system("老王烧烤")
        
        # 每日运营（自动完成闭环）
        result = system.daily_operation()
        
        # 处理客户咨询（智能推荐）
        response = system.handle_consultation("douyin", "今天有什么好吃的？")
        
        # 处理订单（库存检查+优惠计算）
        order = system.handle_order("offline", [
            {"dish_name": "招牌羊肉串", "quantity": 10},
            {"dish_name": "拍黄瓜", "quantity": 1},
        ], member_id="m123")
        
        # 获取智能报告
        report = system.get_report()
        
        # 获取仪表盘数据
        dashboard = system.get_dashboard()
    """
    return BBQShopSystem(shop_name=shop_name, shop_id=shop_id)


__all__ = [
    "BBQShopSystem",
    "BBQShopOperator",
    "BBQShopContentPipeline",
    "BBQShopCustomerService",
    "BBQShopDataLoop",
    "create_bbq_system",
]
