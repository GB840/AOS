"""多租户数据模型定义。

包含租户套餐枚举、租户主数据模型、API密钥模型等核心数据结构，
为整个多租户隔离层提供统一的数据表示。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TenantPlan(str, Enum):
    """租户套餐枚举。

    定义不同套餐的名称、价格、资源限制和功能特性。
    """

    FREE = "free"
    STANDARD = "standard"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"

    @property
    def name(self) -> str:
        """获取套餐显示名称。"""
        return _PLAN_CONFIGS[self]["name"]

    @property
    def price_monthly(self) -> float:
        """获取月费（元）。"""
        return _PLAN_CONFIGS[self]["price_monthly"]

    @property
    def price_yearly(self) -> float:
        """获取年费（元）。"""
        return _PLAN_CONFIGS[self]["price_yearly"]

    @property
    def max_agents(self) -> int:
        """获取最大智能体数量。"""
        return _PLAN_CONFIGS[self]["max_agents"]

    @property
    def max_storage_mb(self) -> int:
        """获取最大存储容量（MB）。"""
        return _PLAN_CONFIGS[self]["max_storage_mb"]

    @property
    def features(self) -> List[str]:
        """获取功能列表。"""
        return _PLAN_CONFIGS[self]["features"]

    @property
    def rate_limit_per_min(self) -> int:
        """获取每分钟调用上限。"""
        return _PLAN_CONFIGS[self]["rate_limit_per_min"]


_PLAN_CONFIGS: Dict[TenantPlan, Dict[str, Any]] = {
    TenantPlan.FREE: {
        "name": "免费试用版",
        "price_monthly": 0.0,
        "price_yearly": 0.0,
        "max_agents": 3,
        "max_storage_mb": 100,
        "features": ["基础对话", "单个知识库", "基础模板"],
        "rate_limit_per_min": 20,
    },
    TenantPlan.STANDARD: {
        "name": "个人创业标准版",
        "price_monthly": 49.0,
        "price_yearly": 490.0,
        "max_agents": 10,
        "max_storage_mb": 2048,
        "features": ["全部基础功能", "多知识库", "自定义人设", "API调用", "数据分析"],
        "rate_limit_per_min": 100,
    },
    TenantPlan.PROFESSIONAL: {
        "name": "硬件/工业专业版",
        "price_monthly": 99.0,
        "price_yearly": 990.0,
        "max_agents": 50,
        "max_storage_mb": 10240,
        "features": ["全部标准版功能", "硬件设备接入", "工业协议支持", "实时监控", "团队协作", "优先技术支持"],
        "rate_limit_per_min": 500,
    },
    TenantPlan.ENTERPRISE: {
        "name": "私有化部署版",
        "price_monthly": -1.0,
        "price_yearly": -1.0,
        "max_agents": -1,
        "max_storage_mb": -1,
        "features": ["全部专业版功能", "私有化部署", "定制化开发", "专属技术支持", "SLA保障", "数据安全审计"],
        "rate_limit_per_min": -1,
    },
}


@dataclass
class Tenant:
    """租户数据模型。

    表示一个租户的完整信息，包括基本信息、套餐状态、行业模板和配置等。
    """

    tenant_id: str
    name: str
    email: str
    plan: TenantPlan
    status: str
    created_at: float
    expires_at: float
    industry: str
    settings: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。

        Returns:
            包含租户所有字段的字典。
        """
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "email": self.email,
            "plan": self.plan.value if isinstance(self.plan, TenantPlan) else self.plan,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "industry": self.industry,
            "settings": self.settings,
            "usage": self.usage,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Tenant:
        """从字典创建租户实例。

        Args:
            data: 包含租户字段的字典。

        Returns:
            Tenant 实例。
        """
        plan_value = data.get("plan", TenantPlan.FREE.value)
        if isinstance(plan_value, str):
            try:
                plan = TenantPlan(plan_value)
            except ValueError:
                plan = TenantPlan.FREE
        else:
            plan = plan_value

        return cls(
            tenant_id=data["tenant_id"],
            name=data.get("name", ""),
            email=data.get("email", ""),
            plan=plan,
            status=data.get("status", "active"),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at", 0.0),
            industry=data.get("industry", "service"),
            settings=data.get("settings", {}),
            usage=data.get("usage", {}),
        )

    def is_active(self) -> bool:
        """检查租户是否处于活跃状态。

        Returns:
            True 表示活跃，False 表示非活跃。
        """
        if self.status != "active":
            return False
        if self.expires_at > 0 and time.time() > self.expires_at:
            return False
        return True

    def can_create_agent(self, current_count: int) -> bool:
        """检查是否可以创建新的智能体。

        Args:
            current_count: 当前已创建的智能体数量。

        Returns:
            True 表示可以创建，False 表示已达上限。
        """
        max_agents = self.plan.max_agents
        if max_agents < 0:
            return True
        return current_count < max_agents

    def check_storage_limit(self, current_usage_mb: float) -> bool:
        """检查存储使用量是否在限制范围内。

        Args:
            current_usage_mb: 当前已使用的存储量（MB）。

        Returns:
            True 表示未超限，False 表示已超限。
        """
        max_storage = self.plan.max_storage_mb
        if max_storage < 0:
            return True
        return current_usage_mb <= max_storage


@dataclass
class TenantAPIKey:
    """租户 API 密钥模型。

    用于 API 访问认证，存储密钥哈希和使用记录。
    """

    key_id: str
    tenant_id: str
    key_hash: str
    created_at: float
    last_used_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。

        Returns:
            包含 API 密钥所有字段的字典。
        """
        return {
            "key_id": self.key_id,
            "tenant_id": self.tenant_id,
            "key_hash": self.key_hash,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TenantAPIKey:
        """从字典创建 API 密钥实例。

        Args:
            data: 包含 API 密钥字段的字典。

        Returns:
            TenantAPIKey 实例。
        """
        return cls(
            key_id=data["key_id"],
            tenant_id=data["tenant_id"],
            key_hash=data["key_hash"],
            created_at=data.get("created_at", time.time()),
            last_used_at=data.get("last_used_at", 0.0),
        )
