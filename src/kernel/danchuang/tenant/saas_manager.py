"""SaaS 多租户增强管理模块。

提供用量统计、配额管理、套餐管理和管理员功能，
使用 JSON 文件持久化用量数据，与 TenantManager 兼容。
"""
from __future__ import annotations

import calendar
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Tenant, TenantPlan
from .tenant_manager import TenantManager

logger = logging.getLogger(__name__)

def _default_usage_data_path() -> str:
    """用量数据落盘路径（禁止硬编码绝对路径，对齐理念7 千人千面）。

    优先级：AOS_USAGE_DATA_PATH 环境变量 > 仓库根 data/danchuang/usage_data.json。
    仓库根按本文件位置回溯推导，任何机器 clone 下来都能跑。
    """
    env = os.environ.get("AOS_USAGE_DATA_PATH")
    if env:
        return env
    # src/kernel/danchuang/tenant/saas_manager.py -> 回溯 5 层到仓库根
    root = Path(__file__).resolve().parents[4]
    return str(root / "data" / "danchuang" / "usage_data.json")


DEFAULT_USAGE_DATA_PATH = _default_usage_data_path()


# ---------------------------------------------------------------------------
# 母纲承接：让 AI 不再收割老百姓（AGENTS.md §0.0，效力高于本文件一切商业逻辑）
# ---------------------------------------------------------------------------
# 宪法原则 1「本地优先·数据自持」+ 原则 4「主权归你·永不收割」的**代码承接点**。
#
# 判定规则（默认即自由）：
#   - 默认（未显式开启 SaaS 托管）= 本地自持模式 → **所有配额一律无限**，
#     一个数字都不卡。用户用自己的机器、自己的算力、自己的数据，凭什么限他。
#   - 仅当显式设置 AOS_SAAS_MODE=1（运营方托管多租户，消耗的是运营方资源）
#     才启用套餐配额——此时收的是「托管服务费」，不是「功能准入费」。
#
# 硬约束（对齐 §0.0.3 付费墙检验，由 tests/test_no_harvest_charter.py 守门）：
#   即便在 SaaS 模式下，**任何指标在 free 档都不得为 0**——限量可以，
#   把功能直接锁死是「卖准入」，属于收割，禁止。
UNLIMITED = -1


def is_local_sovereign_mode() -> bool:
    """是否本地自持模式（默认 True）。本地模式下所有配额无限。"""
    return os.environ.get("AOS_SAAS_MODE") != "1"


class UsageMetric(str, Enum):
    """用量指标枚举。

    定义所有可计量的资源使用指标类型。
    """

    AGENT_CALL_COUNT = "agent_call_count"
    GOAL_SET_COUNT = "goal_set_count"
    DAILY_RUN_COUNT = "daily_run_count"
    WORKFLOW_COUNT = "workflow_count"
    STORAGE_MB = "storage_mb"
    API_CALL_COUNT = "api_call_count"


class PlanTier(str, Enum):
    """套餐层级枚举。

    定义不同的套餐层级，与 TenantPlan 保持对应关系。
    """

    FREE = "free"
    STANDARD = "standard"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"

    @classmethod
    def from_tenant_plan(cls, plan: TenantPlan) -> PlanTier:
        """从 TenantPlan 转换为 PlanTier。

        Args:
            plan: TenantPlan 枚举值。

        Returns:
            对应的 PlanTier 枚举值。
        """
        return cls(plan.value)

    def to_tenant_plan(self) -> TenantPlan:
        """转换为 TenantPlan。

        Returns:
            对应的 TenantPlan 枚举值。
        """
        return TenantPlan(self.value)


@dataclass
class PlanQuota:
    """套餐配额数据类。

    表示一个套餐的完整配置信息，包括基本信息和各指标的配额上限。
    """

    tier: PlanTier
    name: str
    price: float
    description: str
    quotas: Dict[UsageMetric, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。

        Returns:
            包含套餐配额所有字段的字典。
        """
        return {
            "tier": self.tier.value if isinstance(self.tier, PlanTier) else self.tier,
            "name": self.name,
            "price": self.price,
            "description": self.description,
            "quotas": {
                k.value if isinstance(k, UsageMetric) else k: v
                for k, v in self.quotas.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlanQuota:
        """从字典创建套餐配额实例。

        Args:
            data: 包含套餐配额字段的字典。

        Returns:
            PlanQuota 实例。
        """
        tier_value = data.get("tier", PlanTier.FREE.value)
        if isinstance(tier_value, str):
            try:
                tier = PlanTier(tier_value)
            except ValueError:
                tier = PlanTier.FREE
        else:
            tier = tier_value

        quotas_data = data.get("quotas", {})
        quotas: Dict[UsageMetric, int] = {}
        for k, v in quotas_data.items():
            try:
                metric = UsageMetric(k) if isinstance(k, str) else k
                quotas[metric] = int(v)
            except ValueError:
                continue

        return cls(
            tier=tier,
            name=data.get("name", ""),
            price=float(data.get("price", 0.0)),
            description=data.get("description", ""),
            quotas=quotas,
        )

    def get_quota(self, metric: UsageMetric) -> int:
        """获取指定指标的配额。

        Args:
            metric: 用量指标。

        Returns:
            配额上限值，-1 表示无限。
        """
        return self.quotas.get(metric, -1)

    def is_unlimited(self, metric: UsageMetric) -> bool:
        """检查指定指标是否为无限配额。

        Args:
            metric: 用量指标。

        Returns:
            True 表示无限配额，False 表示有限配额。
        """
        return self.get_quota(metric) < 0


@dataclass
class UsageRecord:
    """用量记录数据类。

    表示一条具体的用量使用记录。
    """

    tenant_id: str
    metric: UsageMetric
    amount: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。

        Returns:
            包含用量记录所有字段的字典。
        """
        return {
            "tenant_id": self.tenant_id,
            "metric": self.metric.value if isinstance(self.metric, UsageMetric) else self.metric,
            "amount": self.amount,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UsageRecord:
        """从字典创建用量记录实例。

        Args:
            data: 包含用量记录字段的字典。

        Returns:
            UsageRecord 实例。
        """
        metric_value = data.get("metric", UsageMetric.API_CALL_COUNT.value)
        if isinstance(metric_value, str):
            try:
                metric = UsageMetric(metric_value)
            except ValueError:
                metric = UsageMetric.API_CALL_COUNT
        else:
            metric = metric_value

        return cls(
            tenant_id=data["tenant_id"],
            metric=metric,
            amount=int(data.get("amount", 0)),
            timestamp=float(data.get("timestamp", time.time())),
        )


_PLAN_QUOTAS: Dict[PlanTier, PlanQuota] = {
    # 【母纲约束】free 档任何指标都不得为 0——限量可以，锁死功能不行。
    # 原 WORKFLOW_COUNT=0 是典型功能墙（付费才能用工作流），已判定为收割并拆除。
    # 本地自持模式下这张表根本不生效（见 is_local_sovereign_mode，全部无限）；
    # 这里的数字仅用于运营方托管的 SaaS 试用档，收的是托管资源费。
    PlanTier.FREE: PlanQuota(
        tier=PlanTier.FREE,
        name="免费版",
        price=0.0,
        description="托管试用档（本地自持模式下全部无限，不受此表限制）",
        quotas={
            UsageMetric.AGENT_CALL_COUNT: 200,
            UsageMetric.GOAL_SET_COUNT: 10,
            UsageMetric.DAILY_RUN_COUNT: 20,
            UsageMetric.WORKFLOW_COUNT: 5,
            UsageMetric.STORAGE_MB: 500,
            UsageMetric.API_CALL_COUNT: 500,
        },
    ),
    PlanTier.STANDARD: PlanQuota(
        tier=PlanTier.STANDARD,
        name="标准版",
        price=49.0,
        description="个人创业首选，功能齐全",
        quotas={
            UsageMetric.AGENT_CALL_COUNT: 1000,
            UsageMetric.GOAL_SET_COUNT: 30,
            UsageMetric.DAILY_RUN_COUNT: 30,
            UsageMetric.WORKFLOW_COUNT: 20,
            UsageMetric.STORAGE_MB: 2048,
            UsageMetric.API_CALL_COUNT: 5000,
        },
    ),
    PlanTier.PROFESSIONAL: PlanQuota(
        tier=PlanTier.PROFESSIONAL,
        name="专业版",
        price=99.0,
        description="硬件/工业专业，无限能力",
        quotas={
            UsageMetric.AGENT_CALL_COUNT: 5000,
            UsageMetric.GOAL_SET_COUNT: -1,
            UsageMetric.DAILY_RUN_COUNT: -1,
            UsageMetric.WORKFLOW_COUNT: 100,
            UsageMetric.STORAGE_MB: 10240,
            UsageMetric.API_CALL_COUNT: 20000,
        },
    ),
    PlanTier.ENTERPRISE: PlanQuota(
        tier=PlanTier.ENTERPRISE,
        name="企业版",
        price=9800.0,
        description="私有化部署，全部无限+定制化",
        quotas={
            UsageMetric.AGENT_CALL_COUNT: -1,
            UsageMetric.GOAL_SET_COUNT: -1,
            UsageMetric.DAILY_RUN_COUNT: -1,
            UsageMetric.WORKFLOW_COUNT: -1,
            UsageMetric.STORAGE_MB: -1,
            UsageMetric.API_CALL_COUNT: -1,
        },
    ),
}


class UsageManager:
    """用量管理器。

    负责用量记录、统计、配额检查等功能，
    使用 JSON 文件持久化存储用量数据。
    """

    def __init__(
        self,
        data_path: Optional[str] = None,
        tenant_manager: Optional[TenantManager] = None,
    ):
        """初始化用量管理器。

        Args:
            data_path: 用量数据 JSON 文件路径，默认使用 DEFAULT_USAGE_DATA_PATH。
            tenant_manager: 租户管理器实例，可选。
        """
        self.data_path = data_path or DEFAULT_USAGE_DATA_PATH
        self.tenant_manager = tenant_manager or TenantManager()
        self._ensure_data_file()

    def _ensure_data_file(self) -> None:
        """确保用量数据文件存在。"""
        data_dir = os.path.dirname(self.data_path)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

        if not os.path.exists(self.data_path):
            empty_data = {
                "records": [],
                "tenant_usage": {},
            }
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(empty_data, f, ensure_ascii=False, indent=2)

    def _load_data(self) -> Dict[str, Any]:
        """加载用量数据。

        Returns:
            用量数据字典。
        """
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._ensure_data_file()
            return {"records": [], "tenant_usage": {}}

    def _save_data(self, data: Dict[str, Any]) -> None:
        """保存用量数据。

        Args:
            data: 用量数据字典。
        """
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list_plans(self) -> List[PlanQuota]:
        """列出所有可用套餐。

        Returns:
            套餐配额列表。
        """
        return list(_PLAN_QUOTAS.values())

    def get_plan_quota(self, tier: PlanTier | str) -> Optional[PlanQuota]:
        """获取指定套餐的配额配置。

        Args:
            tier: 套餐层级。

        Returns:
            套餐配额实例，不存在返回 None。
        """
        if isinstance(tier, str):
            try:
                tier = PlanTier(tier)
            except ValueError:
                return None
        return _PLAN_QUOTAS.get(tier)

    def _get_month_start(self, ts: float) -> float:
        """获取给定时间戳所在月份的起始时间戳。

        Args:
            ts: 时间戳。

        Returns:
            月份起始时间戳。
        """
        tm = time.localtime(ts)
        month_start = time.mktime((tm.tm_year, tm.tm_mon, 1, 0, 0, 0, 0, 0, 0))
        return month_start

    def _get_day_start(self, ts: float) -> float:
        """获取给定时间戳所在日期的起始时间戳。

        Args:
            ts: 时间戳。

        Returns:
            日期起始时间戳。
        """
        tm = time.localtime(ts)
        day_start = time.mktime((tm.tm_year, tm.tm_mon, tm.tm_mday, 0, 0, 0, 0, 0, 0))
        return day_start

    def _get_usage_key(self, metric: UsageMetric, period: str) -> str:
        """获取用量统计键名。

        Args:
            metric: 用量指标。
            period: 统计周期（monthly/daily/total）。

        Returns:
            用量统计键名。
        """
        return f"{metric.value}_{period}"

    def record_usage(
        self,
        tenant_id: str,
        metric: UsageMetric | str,
        amount: int = 1,
    ) -> UsageRecord:
        """记录用量。

        Args:
            tenant_id: 租户 ID。
            metric: 用量指标。
            amount: 使用数量，默认为 1。

        Returns:
            创建的用量记录。
        """
        if isinstance(metric, str):
            try:
                metric = UsageMetric(metric)
            except ValueError:
                metric = UsageMetric.API_CALL_COUNT

        now = time.time()
        record = UsageRecord(
            tenant_id=tenant_id,
            metric=metric,
            amount=amount,
            timestamp=now,
        )

        data = self._load_data()

        data["records"].append(record.to_dict())

        if tenant_id not in data["tenant_usage"]:
            data["tenant_usage"][tenant_id] = {}

        usage = data["tenant_usage"][tenant_id]
        month_start = self._get_month_start(now)
        day_start = self._get_day_start(now)

        usage["last_record_at"] = now
        usage["current_month_start"] = month_start
        usage["current_day_start"] = day_start

        total_key = self._get_usage_key(metric, "total")
        month_key = self._get_usage_key(metric, "monthly")
        day_key = self._get_usage_key(metric, "daily")

        usage[total_key] = usage.get(total_key, 0) + amount
        usage[month_key] = usage.get(month_key, 0) + amount
        usage[day_key] = usage.get(day_key, 0) + amount

        self._save_data(data)
        logger.debug(f"记录用量: {tenant_id} - {metric.value} +{amount}")

        return record

    def get_current_usage(
        self,
        tenant_id: str,
        metric: Optional[UsageMetric | str] = None,
    ) -> Dict[str, Any]:
        """获取租户当前用量统计。

        Args:
            tenant_id: 租户 ID。
            metric: 可选的指标过滤，不指定则返回所有指标。

        Returns:
            用量统计字典，包含 total/monthly/daily 三个周期的数据。
        """
        data = self._load_data()
        usage = data.get("tenant_usage", {}).get(tenant_id, {})
        now = time.time()

        month_start = usage.get("current_month_start", self._get_month_start(now))
        day_start = usage.get("current_day_start", self._get_day_start(now))

        if month_start != self._get_month_start(now):
            for m in UsageMetric:
                month_key = self._get_usage_key(m, "monthly")
                usage[month_key] = 0
            usage["current_month_start"] = self._get_month_start(now)

        if day_start != self._get_day_start(now):
            for m in UsageMetric:
                day_key = self._get_usage_key(m, "daily")
                usage[day_key] = 0
            usage["current_day_start"] = self._get_day_start(now)

        result: Dict[str, Any] = {}

        metrics_to_check = [UsageMetric(metric)] if metric else list(UsageMetric)
        if metric and isinstance(metric, str):
            try:
                metrics_to_check = [UsageMetric(metric)]
            except ValueError:
                metrics_to_check = list(UsageMetric)

        for m in metrics_to_check:
            total_key = self._get_usage_key(m, "total")
            month_key = self._get_usage_key(m, "monthly")
            day_key = self._get_usage_key(m, "daily")
            result[m.value] = {
                "total": usage.get(total_key, 0),
                "monthly": usage.get(month_key, 0),
                "daily": usage.get(day_key, 0),
            }

        return result

    def get_usage_report(
        self,
        tenant_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """获取用量报告。

        Args:
            tenant_id: 租户 ID。
            start_time: 起始时间戳，默认不限制。
            end_time: 结束时间戳，默认不限制。

        Returns:
            用量报告字典，包含记录列表和各指标汇总。
        """
        data = self._load_data()
        records_data = data.get("records", [])

        filtered_records = []
        for r in records_data:
            if r.get("tenant_id") != tenant_id:
                continue
            ts = r.get("timestamp", 0)
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue
            filtered_records.append(UsageRecord.from_dict(r))

        summary: Dict[str, Dict[str, int]] = {}
        for metric in UsageMetric:
            summary[metric.value] = {
                "count": 0,
                "total_amount": 0,
            }

        for record in filtered_records:
            metric_val = record.metric.value
            summary[metric_val]["count"] += 1
            summary[metric_val]["total_amount"] += record.amount

        current_usage = self.get_current_usage(tenant_id)

        return {
            "tenant_id": tenant_id,
            "start_time": start_time,
            "end_time": end_time,
            "record_count": len(filtered_records),
            "records": [r.to_dict() for r in filtered_records],
            "summary": summary,
            "current_usage": current_usage,
        }

    def check_quota(
        self,
        tenant_id: str,
        metric: UsageMetric | str,
        period: str = "monthly",
    ) -> Dict[str, Any]:
        """检查是否达到配额上限。

        Args:
            tenant_id: 租户 ID。
            metric: 用量指标。
            period: 统计周期（monthly/daily/total），默认 monthly。

        Returns:
            检查结果字典，包含：
                - ok: 是否未超限
                - used: 已用数量
                - quota: 配额上限（-1 表示无限）
                - remaining: 剩余数量（-1 表示无限）
                - percentage: 使用百分比（无限配额为 0）
        """
        # 【母纲短路｜AGENTS.md §0.0 原则1+4】本地自持模式一律无限，不卡任何数字。
        # 用户跑在自己机器上、烧自己的算力、存自己的数据——没有任何理由限制他。
        # 只有显式 AOS_SAAS_MODE=1（运营方托管、消耗运营方资源）才往下走配额逻辑。
        if is_local_sovereign_mode():
            return {
                "ok": True,
                "used": 0,
                "quota": UNLIMITED,
                "remaining": UNLIMITED,
                "percentage": 0,
                "reason": "local_sovereign_mode",
            }

        if isinstance(metric, str):
            try:
                metric = UsageMetric(metric)
            except ValueError:
                return {
                    "ok": False,
                    "used": 0,
                    "quota": 0,
                    "remaining": 0,
                    "percentage": 0,
                }

        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return {
                "ok": False,
                "used": 0,
                "quota": 0,
                "remaining": 0,
                "percentage": 0,
            }

        plan_tier = PlanTier.from_tenant_plan(tenant.plan)
        plan_quota = self.get_plan_quota(plan_tier)
        if not plan_quota:
            return {
                "ok": True,
                "used": 0,
                "quota": -1,
                "remaining": -1,
                "percentage": 0,
            }

        quota = plan_quota.get_quota(metric)

        if quota < 0:
            return {
                "ok": True,
                "used": 0,
                "quota": -1,
                "remaining": -1,
                "percentage": 0,
            }

        current_usage = self.get_current_usage(tenant_id, metric)
        used = current_usage.get(metric.value, {}).get(period, 0)

        remaining = max(0, quota - used)
        percentage = (used / quota * 100) if quota > 0 else 0

        ok = used < quota

        return {
            "ok": ok,
            "used": used,
            "quota": quota,
            "remaining": remaining,
            "percentage": round(percentage, 2),
        }


class AdminManager:
    """管理员管理器。

    提供管理员后台功能，包括仪表盘统计、租户管理、系统健康检查等。
    """

    def __init__(
        self,
        tenant_manager: Optional[TenantManager] = None,
        usage_manager: Optional[UsageManager] = None,
    ):
        """初始化管理员管理器。

        Args:
            tenant_manager: 租户管理器实例，可选。
            usage_manager: 用量管理器实例，可选。
        """
        self.tenant_manager = tenant_manager or TenantManager()
        self.usage_manager = usage_manager or UsageManager(
            tenant_manager=self.tenant_manager
        )

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """获取仪表盘统计数据。

        Returns:
            仪表盘统计字典，包含租户统计、收入统计、用量统计。
        """
        all_tenants = self.tenant_manager.list_tenants()

        total_tenants = len(all_tenants)
        active_tenants = sum(1 for t in all_tenants if t.status == "active")
        suspended_tenants = sum(1 for t in all_tenants if t.status == "suspended")

        plan_counts: Dict[str, int] = {}
        for t in all_tenants:
            plan_val = t.plan.value if isinstance(t.plan, TenantPlan) else t.plan
            plan_counts[plan_val] = plan_counts.get(plan_val, 0) + 1

        monthly_revenue = 0.0
        yearly_revenue = 0.0
        for t in all_tenants:
            if t.status != "active":
                continue
            plan_quota = self.usage_manager.get_plan_quota(
                PlanTier.from_tenant_plan(t.plan)
            )
            if plan_quota:
                if t.plan == TenantPlan.ENTERPRISE:
                    yearly_revenue += plan_quota.price
                else:
                    monthly_revenue += plan_quota.price

        usage_data = self.usage_manager._load_data()
        total_api_calls = 0
        total_agent_calls = 0
        for tenant_id, usage in usage_data.get("tenant_usage", {}).items():
            total_api_calls += usage.get(
                self.usage_manager._get_usage_key(UsageMetric.API_CALL_COUNT, "total"),
                0,
            )
            total_agent_calls += usage.get(
                self.usage_manager._get_usage_key(UsageMetric.AGENT_CALL_COUNT, "total"),
                0,
            )

        return {
            "tenant_stats": {
                "total": total_tenants,
                "active": active_tenants,
                "suspended": suspended_tenants,
                "plan_distribution": plan_counts,
            },
            "revenue_stats": {
                "monthly_revenue": round(monthly_revenue, 2),
                "yearly_revenue": round(yearly_revenue, 2),
                "total_annualized": round(monthly_revenue * 12 + yearly_revenue, 2),
            },
            "usage_stats": {
                "total_api_calls": total_api_calls,
                "total_agent_calls": total_agent_calls,
            },
        }

    def list_all_tenants(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        plan: Optional[PlanTier | str] = None,
    ) -> Dict[str, Any]:
        """列出所有租户（分页、按状态/套餐筛选）。

        Args:
            page: 页码，从 1 开始。
            page_size: 每页数量。
            status: 按状态筛选，可选。
            plan: 按套餐筛选，可选。

        Returns:
            分页结果字典，包含：
                - items: 租户列表
                - total: 总数
                - page: 当前页
                - page_size: 每页数量
                - total_pages: 总页数
        """
        all_tenants = self.tenant_manager.list_tenants(status=status)

        if plan is not None:
            if isinstance(plan, str):
                try:
                    plan = PlanTier(plan)
                except ValueError:
                    plan = None
            if plan:
                tenant_plan = plan.to_tenant_plan()
                all_tenants = [t for t in all_tenants if t.plan == tenant_plan]

        total = len(all_tenants)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_tenants[start:end]

        items = []
        for t in page_items:
            item = t.to_dict()
            current_usage = self.usage_manager.get_current_usage(t.tenant_id)
            item["current_usage"] = current_usage
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def get_tenant_detail(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """获取租户详情（含用量）。

        Args:
            tenant_id: 租户 ID。

        Returns:
            租户详情字典，包含基本信息和用量统计，不存在返回 None。
        """
        tenant = self.tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return None

        plan_quota = self.usage_manager.get_plan_quota(
            PlanTier.from_tenant_plan(tenant.plan)
        )
        current_usage = self.usage_manager.get_current_usage(tenant_id)
        usage_report = self.usage_manager.get_usage_report(tenant_id)

        quota_status = {}
        if plan_quota:
            for metric in UsageMetric:
                quota_status[metric.value] = self.usage_manager.check_quota(
                    tenant_id, metric
                )

        api_keys = self.tenant_manager.get_tenant_api_keys(tenant_id)

        return {
            "tenant": tenant.to_dict(),
            "plan_quota": plan_quota.to_dict() if plan_quota else None,
            "current_usage": current_usage,
            "quota_status": quota_status,
            "usage_report_summary": {
                "record_count": usage_report["record_count"],
                "summary": usage_report["summary"],
            },
            "api_keys": [k.to_dict() for k in api_keys],
        }

    def suspend_tenant(self, tenant_id: str) -> bool:
        """暂停租户。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        return self.tenant_manager.suspend_tenant(tenant_id)

    def activate_tenant(self, tenant_id: str) -> bool:
        """激活租户。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        return self.tenant_manager.activate_tenant(tenant_id)

    def update_tenant_plan(
        self,
        tenant_id: str,
        new_plan: PlanTier | str,
    ) -> bool:
        """更新租户套餐。

        Args:
            tenant_id: 租户 ID。
            new_plan: 新的套餐层级。

        Returns:
            True 表示成功，False 表示租户不存在或套餐无效。
        """
        if isinstance(new_plan, str):
            try:
                new_plan = PlanTier(new_plan)
            except ValueError:
                return False

        tenant_plan = new_plan.to_tenant_plan()
        return self.tenant_manager.update_plan(tenant_id, tenant_plan)

    def get_system_health(self) -> Dict[str, Any]:
        """系统健康检查。

        Returns:
            系统健康状态字典。
        """
        health = {
            "status": "healthy",
            "timestamp": time.time(),
            "checks": {},
        }

        try:
            tenants = self.tenant_manager.list_tenants()
            health["checks"]["tenant_db"] = {
                "status": "ok",
                "tenant_count": len(tenants),
            }
        except Exception as e:
            health["checks"]["tenant_db"] = {
                "status": "error",
                "error": str(e),
            }
            health["status"] = "degraded"

        try:
            usage_data = self.usage_manager._load_data()
            record_count = len(usage_data.get("records", []))
            tenant_count = len(usage_data.get("tenant_usage", {}))
            health["checks"]["usage_data"] = {
                "status": "ok",
                "record_count": record_count,
                "tenant_count": tenant_count,
            }
        except Exception as e:
            health["checks"]["usage_data"] = {
                "status": "error",
                "error": str(e),
            }
            health["status"] = "degraded"

        try:
            data_path = Path(self.usage_manager.data_path)
            if data_path.exists():
                file_size = data_path.stat().st_size
                health["checks"]["usage_storage"] = {
                    "status": "ok",
                    "file_size_bytes": file_size,
                    "file_size_mb": round(file_size / 1024 / 1024, 4),
                }
            else:
                health["checks"]["usage_storage"] = {
                    "status": "warning",
                    "message": "数据文件不存在",
                }
        except Exception as e:
            health["checks"]["usage_storage"] = {
                "status": "error",
                "error": str(e),
            }
            health["status"] = "degraded"

        return health
