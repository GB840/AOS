"""租户管理器。

提供租户的创建、查询、更新、删除等核心管理功能，
使用 SQLite 作为数据存储后端，支持 API 密钥管理和限流。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Tenant, TenantAPIKey, TenantPlan

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = r"d:\AOS\data\danchuang\tenants.db"


class TenantManager:
    """租户管理器。

    负责租户生命周期管理、API 密钥管理、限流检查和使用量统计。
    使用 SQLite 数据库持久化存储租户数据。
    """

    def __init__(self, db_path: Optional[str] = None):
        """初始化租户管理器。

        Args:
            db_path: SQLite 数据库文件路径，默认使用 DEFAULT_DB_PATH。
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._rate_limit_cache: Dict[str, List[float]] = {}
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接。

        Returns:
            sqlite3 连接对象。
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        """确保数据库和表结构存在。"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL DEFAULT 0,
                    industry TEXT NOT NULL DEFAULT 'service',
                    settings TEXT NOT NULL DEFAULT '{}',
                    usage TEXT NOT NULL DEFAULT '{}'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_used_at REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    cost REAL NOT NULL DEFAULT 0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_log_tenant ON usage_log(tenant_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_log_timestamp ON usage_log(timestamp)")

            conn.commit()
            logger.info(f"租户数据库初始化完成: {self.db_path}")
        finally:
            conn.close()

    def create_tenant(
        self,
        name: str,
        email: str,
        plan: TenantPlan | str = TenantPlan.FREE,
        industry: str = "service",
    ) -> Tenant:
        """创建新租户。

        Args:
            name: 租户名称。
            email: 联系邮箱。
            plan: 套餐类型，默认为免费版。
            industry: 行业模板，默认为 service。

        Returns:
            创建的 Tenant 实例。

        Raises:
            ValueError: 当邮箱已存在时抛出。
        """
        if isinstance(plan, str):
            try:
                plan = TenantPlan(plan)
            except ValueError:
                plan = TenantPlan.FREE
        tenant_id = f"tnt_{uuid.uuid4().hex[:12]}"
        now = time.time()

        default_settings = {
            "industry": industry,
            "language": "zh-CN",
            "timezone": "Asia/Shanghai",
        }
        default_usage = {
            "total_api_calls": 0,
            "total_agents": 0,
            "storage_used_mb": 0.0,
            "current_month_calls": 0,
            "current_month_start": now,
        }

        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT tenant_id FROM tenants WHERE email = ?", (email,))
            if cursor.fetchone():
                raise ValueError(f"邮箱已注册: {email}")

            cursor.execute(
                """
                INSERT INTO tenants (
                    tenant_id, name, email, plan, status, created_at,
                    expires_at, industry, settings, usage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    name,
                    email,
                    plan.value,
                    "active",
                    now,
                    0.0,
                    industry,
                    json.dumps(default_settings, ensure_ascii=False),
                    json.dumps(default_usage, ensure_ascii=False),
                ),
            )

            conn.commit()
            logger.info(f"创建租户成功: {tenant_id} ({name})")

            return Tenant(
                tenant_id=tenant_id,
                name=name,
                email=email,
                plan=plan,
                status="active",
                created_at=now,
                expires_at=0.0,
                industry=industry,
                settings=default_settings,
                usage=default_usage,
            )
        finally:
            conn.close()

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户信息。

        Args:
            tenant_id: 租户 ID。

        Returns:
            Tenant 实例，如果不存在返回 None。
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_tenant(row)
        finally:
            conn.close()

    def _row_to_tenant(self, row: sqlite3.Row) -> Tenant:
        """将数据库行转换为 Tenant 对象。

        Args:
            row: 数据库行对象。

        Returns:
            Tenant 实例。
        """
        return Tenant(
            tenant_id=row["tenant_id"],
            name=row["name"],
            email=row["email"],
            plan=TenantPlan(row["plan"]) if row["plan"] else TenantPlan.FREE,
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            industry=row["industry"],
            settings=json.loads(row["settings"]) if row["settings"] else {},
            usage=json.loads(row["usage"]) if row["usage"] else {},
        )

    def update_plan(self, tenant_id: str, plan: TenantPlan | str) -> bool:
        """升级或降级租户套餐。

        Args:
            tenant_id: 租户 ID。
            plan: 新的套餐类型。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        if isinstance(plan, str):
            try:
                plan = TenantPlan(plan)
            except ValueError:
                return False
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tenants SET plan = ? WHERE tenant_id = ?",
                (plan.value, tenant_id),
            )
            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(f"租户套餐更新: {tenant_id} -> {plan.value}")
            return success
        finally:
            conn.close()

    def suspend_tenant(self, tenant_id: str) -> bool:
        """暂停租户。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        return self._update_status(tenant_id, "suspended")

    def activate_tenant(self, tenant_id: str) -> bool:
        """激活租户。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        return self._update_status(tenant_id, "active")

    def _update_status(self, tenant_id: str, status: str) -> bool:
        """更新租户状态。

        Args:
            tenant_id: 租户 ID。
            status: 新状态。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tenants SET status = ? WHERE tenant_id = ?",
                (status, tenant_id),
            )
            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(f"租户状态更新: {tenant_id} -> {status}")
            return success
        finally:
            conn.close()

    def delete_tenant(self, tenant_id: str) -> bool:
        """删除租户。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示成功，False 表示租户不存在。
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM api_keys WHERE tenant_id = ?", (tenant_id,))
            cursor.execute("DELETE FROM usage_log WHERE tenant_id = ?", (tenant_id,))
            cursor.execute("DELETE FROM tenants WHERE tenant_id = ?", (tenant_id,))

            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(f"删除租户: {tenant_id}")
            return success
        finally:
            conn.close()

    def list_tenants(self, status: Optional[str] = None) -> List[Tenant]:
        """列出租户列表。

        Args:
            status: 可选的状态过滤条件。

        Returns:
            租户列表。
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM tenants WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
                cursor.execute("SELECT * FROM tenants ORDER BY created_at DESC")

            rows = cursor.fetchall()
            return [self._row_to_tenant(row) for row in rows]
        finally:
            conn.close()

    def check_rate_limit(self, tenant_id: str) -> bool:
        """检查租户是否超过限流。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示未超限可以调用，False 表示已超限。
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False

        if not tenant.is_active():
            return False

        rate_limit = tenant.plan.rate_limit_per_min
        if rate_limit < 0:
            return True

        now = time.time()
        window_start = now - 60.0

        if tenant_id not in self._rate_limit_cache:
            self._rate_limit_cache[tenant_id] = []

        timestamps = self._rate_limit_cache[tenant_id]
        timestamps = [t for t in timestamps if t > window_start]
        self._rate_limit_cache[tenant_id] = timestamps

        if len(timestamps) >= rate_limit:
            logger.warning(f"租户限流触发: {tenant_id} ({len(timestamps)}/{rate_limit} 次/分钟)")
            return False

        timestamps.append(now)
        return True

    def record_usage(self, tenant_id: str, action: str, cost: float = 0.0) -> None:
        """记录租户使用量。

        Args:
            tenant_id: 租户 ID。
            action: 操作名称。
            cost: 资源消耗量。
        """
        now = time.time()
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO usage_log (tenant_id, action, cost, timestamp) VALUES (?, ?, ?, ?)",
                (tenant_id, action, cost, now),
            )

            cursor.execute("SELECT usage FROM tenants WHERE tenant_id = ?", (tenant_id,))
            row = cursor.fetchone()
            if row:
                usage = json.loads(row["usage"]) if row["usage"] else {}
                usage["total_api_calls"] = usage.get("total_api_calls", 0) + 1

                month_start = usage.get("current_month_start", now)
                if now - month_start > 30 * 24 * 3600:
                    usage["current_month_calls"] = 1
                    usage["current_month_start"] = now
                else:
                    usage["current_month_calls"] = usage.get("current_month_calls", 0) + 1

                cursor.execute(
                    "UPDATE tenants SET usage = ? WHERE tenant_id = ?",
                    (json.dumps(usage, ensure_ascii=False), tenant_id),
                )

            conn.commit()
            logger.debug(f"记录使用量: {tenant_id} - {action} (cost={cost})")
        finally:
            conn.close()

    def generate_api_key(self, tenant_id: str) -> str:
        """生成 API 密钥。

        Args:
            tenant_id: 租户 ID。

        Returns:
            生成的 API Key 明文（仅返回一次，后续无法找回）。

        Raises:
            ValueError: 当租户不存在时抛出。
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"租户不存在: {tenant_id}")

        key_id = f"key_{uuid.uuid4().hex[:8]}"
        api_key = f"sk-{secrets.token_hex(24)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        now = time.time()

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO api_keys (key_id, tenant_id, key_hash, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key_id, tenant_id, key_hash, now, 0.0),
            )
            conn.commit()
            logger.info(f"生成 API Key: {key_id} (租户: {tenant_id})")
            return api_key
        finally:
            conn.close()

    def validate_api_key(self, api_key: str) -> Optional[Tenant]:
        """验证 API 密钥并返回对应租户。

        Args:
            api_key: API 密钥明文。

        Returns:
            对应的 Tenant 实例，验证失败返回 None。
        """
        if not api_key or not api_key.startswith("sk-"):
            return None

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        now = time.time()

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tenant_id FROM api_keys WHERE key_hash = ?",
                (key_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            tenant_id = row["tenant_id"]

            cursor.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?",
                (now, key_hash),
            )
            conn.commit()

            return self.get_tenant(tenant_id)
        finally:
            conn.close()

    def get_tenant_api_keys(self, tenant_id: str) -> List[TenantAPIKey]:
        """获取租户的所有 API 密钥。

        Args:
            tenant_id: 租户 ID。

        Returns:
            API 密钥列表（不包含密钥明文，仅包含元数据）。
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM api_keys WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            )
            rows = cursor.fetchall()
            return [
                TenantAPIKey(
                    key_id=row["key_id"],
                    tenant_id=row["tenant_id"],
                    key_hash=row["key_hash"],
                    created_at=row["created_at"],
                    last_used_at=row["last_used_at"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def revoke_api_key(self, tenant_id: str, key_id: str) -> bool:
        """吊销 API 密钥。

        Args:
            tenant_id: 租户 ID。
            key_id: 密钥 ID。

        Returns:
            True 表示成功，False 表示密钥不存在。
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM api_keys WHERE tenant_id = ? AND key_id = ?",
                (tenant_id, key_id),
            )
            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(f"吊销 API Key: {key_id} (租户: {tenant_id})")
            return success
        finally:
            conn.close()
