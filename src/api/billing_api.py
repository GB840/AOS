"""支付集成API——支付宝/微信支付对接。

集成流程：
1. 创建订单 → 生成支付链接/二维码
2. 支付回调 → 验证签名 → 更新租户套餐
3. 订单查询 → 检查支付状态

设计原则：
- 不持有支付凭证（由env配置）
- 回调签名验证防伪造
- 幂等性：同一订单多次回调只处理一次
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 支付渠道
PAYMENT_ALIPAY = "alipay"
PAYMENT_WECHAT = "wechat"

# 订单状态
ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_FAILED = "failed"
ORDER_REFUNDED = "refunded"

# 套餐价格映射（与saas_manager.py的PlanQuota保持一致）
PLAN_PRICES = {
    "free": 0.0,
    "standard": 49.0,
    "professional": 99.0,
    "enterprise": 9800.0,
}


@dataclass
class PaymentOrder:
    order_id: str
    tenant_id: str
    plan: str
    amount: float
    channel: str  # alipay / wechat
    status: str = ORDER_PENDING
    created_at: float = field(default_factory=time.time)
    paid_at: float = 0.0
    trade_no: str = ""  # 支付平台交易号
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "tenant_id": self.tenant_id,
            "plan": self.plan,
            "amount": self.amount,
            "channel": self.channel,
            "status": self.status,
            "created_at": self.created_at,
            "paid_at": self.paid_at,
            "trade_no": self.trade_no,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentOrder":
        return cls(
            order_id=data["order_id"],
            tenant_id=data["tenant_id"],
            plan=data["plan"],
            amount=float(data["amount"]),
            channel=data["channel"],
            status=data.get("status", ORDER_PENDING),
            created_at=float(data.get("created_at", 0)),
            paid_at=float(data.get("paid_at", 0)),
            trade_no=data.get("trade_no", ""),
            raw=data.get("raw", {}),
        )


class BillingManager:
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "billing"
        )
        os.makedirs(self.data_dir, exist_ok=True)
        self.orders_path = os.path.join(self.data_dir, "orders.json")
        self._alipay_app_id = os.environ.get("ALIPAY_APP_ID", "")
        self._alipay_private_key = os.environ.get("ALIPAY_PRIVATE_KEY", "")
        self._alipay_public_key = os.environ.get("ALIPAY_PUBLIC_KEY", "")
        self._wechat_mch_id = os.environ.get("WECHAT_MCH_ID", "")
        self._wechat_api_key = os.environ.get("WECHAT_API_KEY", "")

    def create_order(self, tenant_id: str, plan: str, channel: str) -> Dict[str, Any]:
        """创建支付订单。返回支付链接或二维码URL。"""
        if plan not in PLAN_PRICES:
            return {"ok": False, "error": f"未知套餐: {plan}"}
        if channel not in (PAYMENT_ALIPAY, PAYMENT_WECHAT):
            return {"ok": False, "error": f"不支持的支付渠道: {channel}"}

        amount = PLAN_PRICES[plan]
        if amount <= 0:
            return {"ok": False, "error": "免费套餐无需支付"}

        order_id = f"ORD{int(time.time()*1000)}{uuid.uuid4().hex[:8].upper()}"
        order = PaymentOrder(
            order_id=order_id,
            tenant_id=tenant_id,
            plan=plan,
            amount=amount,
            channel=channel,
        )

        self._persist_order(order)

        if channel == PAYMENT_ALIPAY:
            pay_url = f"https://openapi.alipay.com/gateway.do?trade_no={order_id}&total_amount={amount}"
        else:
            pay_url = f"https://api.mch.weixin.qq.com/pay/unifiedorder?out_trade_no={order_id}&total_fee={int(amount*100)}"

        return {
            "ok": True,
            "order_id": order_id,
            "amount": amount,
            "plan": plan,
            "channel": channel,
            "pay_url": pay_url,
            "expires_at": order.created_at + 1800,
        }

    def handle_callback(self, channel: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理支付回调。验证签名 + 更新订单 + 升级租户套餐。"""
        if channel == PAYMENT_ALIPAY:
            order_id = payload.get("out_trade_no", "")
            trade_no = payload.get("trade_no", "")
            sign = payload.get("sign", "")
            params = {k: v for k, v in payload.items() if k not in ("sign", "sign_type")}
            if not self._verify_alipay_sign(params, sign):
                logger.warning("支付宝回调签名验证失败: %s", order_id)
                return {"ok": False, "error": "签名验证失败"}
        elif channel == PAYMENT_WECHAT:
            order_id = payload.get("out_trade_no", "")
            trade_no = payload.get("transaction_id", "")
            sign = payload.get("sign", "")
            sign_str = "&".join(f"{k}={v}" for k, v in sorted(payload.items()) if k not in ("sign",))
            if not self._verify_wechat_sign(sign_str.encode(), sign):
                logger.warning("微信回调签名验证失败: %s", order_id)
                return {"ok": False, "error": "签名验证失败"}
        else:
            return {"ok": False, "error": f"未知渠道: {channel}"}

        orders = self._load_orders()
        if order_id not in orders:
            return {"ok": False, "error": f"订单不存在: {order_id}"}

        order = orders[order_id]
        if order.status == ORDER_PAID:
            return {"ok": True, "message": "订单已处理，幂等跳过"}

        order.status = ORDER_PAID
        order.paid_at = time.time()
        order.trade_no = trade_no
        order.raw = payload
        self._persist_order(order)

        self._upgrade_tenant_plan(order.tenant_id, order.plan)

        logger.info("支付成功: %s -> 租户 %s 升级至 %s", order_id, order.tenant_id, order.plan)
        return {"ok": True, "order_id": order_id, "plan": order.plan}

    def query_order(self, order_id: str) -> Dict[str, Any]:
        """查询订单状态。"""
        orders = self._load_orders()
        if order_id not in orders:
            return {"ok": False, "error": f"订单不存在: {order_id}"}
        return {"ok": True, "order": orders[order_id].to_dict()}

    def _verify_alipay_sign(self, params: Dict[str, str], sign: str) -> bool:
        """验证支付宝回调签名。"""
        if not self._alipay_public_key:
            if os.environ.get("APP_ENV") == "production":
                logger.error("支付安全: 生产环境未配置支付宝密钥，拒绝回调")
                return False
            logger.warning("支付安全: 开发模式跳过支付宝签名验证")
            return True
        sorted_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(
            self._alipay_public_key.encode(), sorted_str.encode(), hashlib.sha256
        ).hexdigest() == sign

    def _verify_wechat_sign(self, payload: bytes, signature: str) -> bool:
        """验证微信支付回调签名。"""
        if not self._wechat_api_key:
            if os.environ.get("APP_ENV") == "production":
                logger.error("支付安全: 生产环境未配置微信密钥，拒绝回调")
                return False
            logger.warning("支付安全: 开发模式跳过微信签名验证")
            return True
        computed = hmac.new(
            self._wechat_api_key.encode(), payload, hashlib.sha256
        ).hexdigest()
        return computed == signature

    def _upgrade_tenant_plan(self, tenant_id: str, plan: str) -> None:
        """升级租户套餐（通过TenantManager）。"""
        try:
            from ..kernel.danchuang.tenant.tenant_manager import TenantManager
            from ..kernel.danchuang.tenant.models import TenantPlan

            tm = TenantManager()
            tenant_plan = TenantPlan(plan)
            tm.update_plan(tenant_id, tenant_plan)
            logger.info("租户 %s 套餐已升级至 %s", tenant_id, plan)
        except Exception as e:
            logger.error("升级租户套餐失败: %s", e)

    def _persist_order(self, order: PaymentOrder) -> None:
        orders = self._load_orders()
        orders[order.order_id] = order
        with open(self.orders_path, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in orders.items()}, f, ensure_ascii=False, indent=2)

    def _load_orders(self) -> Dict[str, PaymentOrder]:
        if not os.path.exists(self.orders_path):
            return {}
        try:
            with open(self.orders_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: PaymentOrder.from_dict(v) for k, v in data.items()}
        except (json.JSONDecodeError, KeyError):
            return {}


# ── FastAPI 路由 ─────────────────────────────────────────────
from fastapi import APIRouter, Request as FastAPIRequest

router = APIRouter(prefix="/api/billing", tags=["billing"])
_billing_manager = BillingManager()


@router.post("/orders")
def create_order_api(tenant_id: str, plan: str, channel: str = "alipay"):
    return _billing_manager.create_order(tenant_id, plan, channel)


@router.get("/orders/{order_id}")
def query_order_api(order_id: str):
    return _billing_manager.query_order(order_id)


@router.post("/callback/alipay")
async def alipay_callback(request: FastAPIRequest):
    body = await request.body()
    payload = json.loads(body) if body else {}
    return _billing_manager.handle_callback("alipay", payload)


@router.post("/callback/wechat")
async def wechat_callback(request: FastAPIRequest):
    body = await request.body()
    payload = json.loads(body) if body else {}
    return _billing_manager.handle_callback("wechat", payload)


def mount_billing_api(app):
    app.include_router(router)
