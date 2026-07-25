import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

"""支付API基础测试。"""
import tempfile
import pytest
from api.billing_api import BillingManager, PaymentOrder, ORDER_PENDING


class TestBillingManager:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.manager = BillingManager(data_dir=self.tmp_dir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_order(self):
        """创建订单。"""
        result = self.manager.create_order("tenant1", "standard", "alipay")
        assert result["ok"] is True
        assert "order_id" in result
        assert result["amount"] == 49.0

    def test_create_order_invalid_plan(self):
        """无效套餐创建订单失败。"""
        result = self.manager.create_order("tenant1", "nonexistent", "alipay")
        assert result["ok"] is False

    def test_query_order(self):
        """查询订单。"""
        result = self.manager.create_order("tenant1", "standard", "alipay")
        order_id = result["order_id"]
        query = self.manager.query_order(order_id)
        assert query["ok"] is True
        assert query["order"]["status"] == ORDER_PENDING

    def test_query_nonexistent_order(self):
        """查询不存在的订单。"""
        result = self.manager.query_order("nonexistent")
        assert result["error"]
