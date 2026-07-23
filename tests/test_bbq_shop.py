"""烧烤店 AI 运营闭环系统测试。

测试完整闭环：
    运营数据 → AI运营官 → 内容生产 → 客服承接 → 数据回流
"""
import pytest
import time
from datetime import datetime


class TestBBQShopModels:
    """测试数据模型"""
    
    def test_dish_model(self):
        """测试菜品模型"""
        from kernel.industry.restaurant.models import Dish
        
        dish = Dish(
            id="dish_001",
            name="招牌羊肉串",
            category="烤串",
            price=5.0,
            cost=2.5,
            sales_count=100,
        )
        
        assert dish.name == "招牌羊肉串"
        assert dish.profit_margin == 0.5  # (5-2.5)/5
        assert dish.profit == 2.5
    
    def test_order_model(self):
        """测试订单模型"""
        from kernel.industry.restaurant.models import Order, OrderItem
        
        order = Order(
            id="order_001",
            table_number="A01",
            items=[
                OrderItem(dish_name="羊肉串", quantity=10, price=5.0),
                OrderItem(dish_name="烤翅", quantity=5, price=8.0),
            ],
            total_amount=90.0,
            channel="offline",
        )
        
        assert order.dish_count == 15
        assert order.total_amount == 90.0
    
    def test_member_model(self):
        """测试会员模型"""
        from kernel.industry.restaurant.models import Member
        
        member = Member(
            id="member_001",
            phone="138****1234",
            name="张三",
            total_consume=1000.0,
            consume_count=10,
        )
        
        assert member.avg_consume == 100.0


class TestBBQShopOperator:
    """测试 AI 运营官"""
    
    def test_operator_creation(self):
        """测试运营官创建"""
        from kernel.industry.restaurant.operator import BBQShopOperator
        
        operator = BBQShopOperator(shop_name="测试烧烤店")
        
        assert operator.shop_name == "测试烧烤店"
        assert operator.shop_id != ""
    
    def test_add_dish_and_order(self):
        """测试添加菜品和订单"""
        from kernel.industry.restaurant.operator import BBQShopOperator
        
        operator = BBQShopOperator(shop_name="测试店")
        
        # 添加菜品
        operator.add_dish({
            "name": "羊肉串",
            "price": 5.0,
            "cost": 2.5,
        })
        
        # 添加订单
        operator.add_order({
            "items": [{"dish_name": "羊肉串", "quantity": 10, "price": 5.0}],
            "total_amount": 50.0,
            "actual_amount": 50.0,
            "channel": "offline",
        })
        
        # 分析销售
        analysis = operator.analyze_sales(days=1)
        
        assert analysis["order_count"] == 1
        assert analysis["total_revenue"] == 50.0
    
    def test_generate_daily_plan(self):
        """测试生成每日运营计划"""
        from kernel.industry.restaurant.operator import BBQShopOperator
        
        operator = BBQShopOperator(shop_name="测试店")
        
        # 添加一些数据
        for i in range(3):
            operator.add_order({
                "items": [{"dish_name": f"菜品{i}", "quantity": 5, "price": 20.0}],
                "total_amount": 100.0,
                "actual_amount": 100.0,
                "channel": "douyin",
            })
        
        # 生成计划
        plan = operator.generate_daily_plan()
        
        assert "content_plans" in plan
        assert "activity_plans" in plan
        assert "service_focus" in plan


class TestBBQShopContentPipeline:
    """测试内容生产流水线"""
    
    def test_pipeline_creation(self):
        """测试流水线创建"""
        from kernel.industry.restaurant.content_pipeline import BBQShopContentPipeline
        
        pipeline = BBQShopContentPipeline(shop_name="测试烧烤店")
        
        assert pipeline.shop_name == "测试烧烤店"
    
    def test_generate_douyin_content(self):
        """测试生成抖音内容"""
        from kernel.industry.restaurant.content_pipeline import BBQShopContentPipeline
        
        pipeline = BBQShopContentPipeline(shop_name="测试烧烤店")
        
        # 生成内容
        contents = pipeline.generate_from_plan({
            "content_plans": [
                {
                    "channel": "douyin",
                    "type": "video",
                    "topic": "招牌推荐：羊肉串",
                    "dish": "羊肉串",
                }
            ],
            "analysis": {"sales": {"top_dishes": [{"name": "羊肉串", "sales": 100}]}}
        })
        
        assert len(contents) == 1
        assert contents[0].channel == "douyin"
        assert "羊肉串" in contents[0].title or "羊肉串" in contents[0].content
    
    def test_generate_xiaohongshu_content(self):
        """测试生成小红书内容"""
        from kernel.industry.restaurant.content_pipeline import BBQShopContentPipeline
        
        pipeline = BBQShopContentPipeline(shop_name="测试烧烤店")
        
        contents = pipeline.generate_from_plan({
            "content_plans": [
                {
                    "channel": "xiaohongshu",
                    "type": "image_text",
                    "topic": "烧烤探店",
                    "dish": "招牌烤串",
                }
            ],
            "analysis": {}
        })
        
        assert len(contents) == 1
        assert contents[0].channel == "xiaohongshu"


class TestBBQShopCustomerService:
    """测试 AI 客服系统"""
    
    def test_service_creation(self):
        """测试客服系统创建"""
        from kernel.industry.restaurant.customer_service import BBQShopCustomerService
        
        service = BBQShopCustomerService(shop_name="测试烧烤店")
        
        assert service.shop_name == "测试烧烤店"
    
    def test_create_session(self):
        """测试创建会话"""
        from kernel.industry.restaurant.customer_service import BBQShopCustomerService
        
        service = BBQShopCustomerService(shop_name="测试店")
        
        session = service.create_session(channel="douyin")
        
        assert session.channel == "douyin"
        assert session.status == "active"
    
    def test_handle_menu_inquiry(self):
        """测试菜单咨询"""
        from kernel.industry.restaurant.customer_service import BBQShopCustomerService
        
        service = BBQShopCustomerService(shop_name="测试店")
        session = service.create_session(channel="douyin")
        
        result = service.handle_message(session.session_id, "有什么好吃的？")
        
        assert "response" in result
        # 应该触发菜单咨询意图或返回欢迎语（包含菜单/价格等问题引导）
        assert result["intent"] == "inquire_menu" or "菜单" in result["response"] or "推荐" in result["response"] or "价格" in result["response"]
    
    def test_handle_price_inquiry(self):
        """测试价格咨询"""
        from kernel.industry.restaurant.customer_service import BBQShopCustomerService
        
        service = BBQShopCustomerService(shop_name="测试店")
        session = service.create_session(channel="wechat")
        
        result = service.handle_message(session.session_id, "人均多少钱？")
        
        assert "response" in result
        assert "人均" in result["response"] or "价格" in result["response"] or "80" in result["response"]
    
    def test_handle_complaint_transfers(self):
        """测试投诉转人工"""
        from kernel.industry.restaurant.customer_service import BBQShopCustomerService
        
        service = BBQShopCustomerService(shop_name="测试店")
        session = service.create_session(channel="douyin")
        
        result = service.handle_message(session.session_id, "我要投诉，服务太差了！")
        
        assert result["strategy"] == "transfer_human"
        assert session.status == "transferred"
    
    def test_quick_reply(self):
        """测试快速回复"""
        from kernel.industry.restaurant.customer_service import BBQShopCustomerService
        
        service = BBQShopCustomerService(shop_name="测试店")
        
        result = service.quick_reply("douyin", "有什么好吃的？")
        
        assert "response" in result
        assert result["session_status"] == "closed"


class TestBBQShopDataLoop:
    """测试数据回流机制"""
    
    def test_dataloop_creation(self):
        """测试数据回流创建"""
        from kernel.industry.restaurant.data_loop import BBQShopDataLoop
        
        loop = BBQShopDataLoop()
        
        assert loop is not None
    
    def test_record_content_result(self):
        """测试记录内容效果"""
        from kernel.industry.restaurant.data_loop import BBQShopDataLoop
        
        loop = BBQShopDataLoop()
        
        loop.record_content_result("content_001", {
            "views": 1000,
            "likes": 50,
            "conversions": 10,
            "revenue": 500.0,
            "channel": "douyin",
        })
        
        stats = loop.get_stats()
        
        assert stats["content_events"] == 1
        assert stats["total_events"] == 1
    
    def test_record_conversation_result(self):
        """测试记录对话结果"""
        from kernel.industry.restaurant.data_loop import BBQShopDataLoop
        
        loop = BBQShopDataLoop()
        
        loop.record_conversation_result("session_001", {
            "channel": "douyin",
            "intent": "inquire_menu",
            "satisfaction": 5,
            "handled_by": "ai",
        })
        
        stats = loop.get_stats()
        
        assert stats["conversation_events"] == 1
    
    def test_sync_to_operator(self):
        """测试同步到运营官"""
        from kernel.industry.restaurant.data_loop import BBQShopDataLoop
        from kernel.industry.restaurant.operator import BBQShopOperator
        
        loop = BBQShopDataLoop()
        operator = BBQShopOperator(shop_name="测试店")
        
        loop.set_modules(operator=operator)
        
        # 记录事件
        loop.record_content_result("content_001", {
            "views": 1000,
            "conversions": 10,
            "channel": "douyin",
        })
        
        # 同步
        result = loop.sync_to_operator()
        
        assert "synced_events" in result


class TestBBQShopFullLoop:
    """测试完整闭环"""
    
    def test_full_loop(self):
        """测试完整运营闭环"""
        from kernel.industry.restaurant.bbq_shop import create_bbq_system
        
        # 创建系统
        system = create_bbq_system("测试烧烤店")
        
        # 1. 添加订单数据
        system.add_order({
            "items": [
                {"dish_name": "羊肉串", "quantity": 10, "price": 5.0},
            ],
            "total_amount": 50.0,
            "actual_amount": 50.0,
            "channel": "douyin",
            "member_phone": "13800138000",
        })
        
        # 2. 生成运营计划
        plan = system.operator.generate_daily_plan()
        
        assert "content_plans" in plan
        assert len(plan["content_plans"]) > 0
        
        # 3. 生成内容
        contents = system.content_pipeline.generate_from_plan(plan)
        
        assert len(contents) > 0
        
        # 4. 处理客户咨询
        result = system.handle_consultation("douyin", "有什么好吃的？")
        
        assert "response" in result
        
        # 5. 数据回流
        sync_result = system.sync_data()
        
        assert "synced_events" in sync_result
    
    def test_daily_operation(self):
        """测试一键运营"""
        from kernel.industry.restaurant.bbq_shop import create_bbq_system
        
        system = create_bbq_system("测试烧烤店")
        
        # 执行每日运营
        result = system.daily_operation()
        
        assert "plan" in result
        assert "contents_generated" in result
        assert result["contents_generated"] >= 0
        assert "sync_result" in result
    
    def test_get_report(self):
        """测试获取报告"""
        from kernel.industry.restaurant.bbq_shop import create_bbq_system
        
        system = create_bbq_system("测试烧烤店")
        
        # 添加一些数据
        for i in range(3):
            system.add_order({
                "items": [{"dish_name": f"菜品{i}", "quantity": 5, "price": 20.0}],
                "total_amount": 100.0,
                "actual_amount": 100.0,
                "channel": "douyin",
            })
        
        # 获取报告
        report = system.get_report()
        
        assert "sales_analysis" in report
        assert "member_analysis" in report
        assert "today_plan" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])