"""数据隔离层。

提供租户数据的物理隔离能力，包括工作目录管理、知识库隔离、
配置隔离、沙箱环境隔离等功能，确保不同租户的数据完全独立。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TENANTS_ROOT = r"d:\AOS\data\danchuang\tenants"


class TenantDataIsolation:
    """租户数据隔离层。

    负责管理租户的独立数据空间，包括工作目录、知识库、配置文件、
    使用量统计和日志目录的创建与隔离。
    """

    def __init__(self, tenants_root: Optional[str] = None):
        """初始化数据隔离层。

        Args:
            tenants_root: 租户数据根目录，默认使用 DEFAULT_TENANTS_ROOT。
        """
        self.tenants_root = Path(tenants_root or DEFAULT_TENANTS_ROOT)
        self._sandbox_counter: Dict[str, int] = {}

    def _get_tenant_dir(self, tenant_id: str) -> Path:
        """获取租户根目录路径。

        Args:
            tenant_id: 租户 ID。

        Returns:
            租户根目录 Path 对象。
        """
        return self.tenants_root / tenant_id

    def get_tenant_workspace(self, tenant_id: str) -> Path:
        """获取租户工作目录。

        工作目录用于存放租户的临时文件、工作产物等。

        Args:
            tenant_id: 租户 ID。

        Returns:
            工作目录 Path 对象。
        """
        return self._get_tenant_dir(tenant_id) / "workspace"

    def get_tenant_kb_dir(self, tenant_id: str) -> Path:
        """获取租户知识库目录。

        知识库目录用于存放租户的知识库文件、向量索引等。

        Args:
            tenant_id: 租户 ID。

        Returns:
            知识库目录 Path 对象。
        """
        return self._get_tenant_dir(tenant_id) / "knowledge"

    def get_tenant_log_dir(self, tenant_id: str) -> Path:
        """获取租户日志目录。

        Args:
            tenant_id: 租户 ID。

        Returns:
            日志目录 Path 对象。
        """
        return self._get_tenant_dir(tenant_id) / "logs"

    def get_tenant_config_path(self, tenant_id: str) -> Path:
        """获取租户配置文件路径。

        Args:
            tenant_id: 租户 ID。

        Returns:
            配置文件 Path 对象。
        """
        return self._get_tenant_dir(tenant_id) / "config.json"

    def get_tenant_usage_path(self, tenant_id: str) -> Path:
        """获取租户使用量统计文件路径。

        Args:
            tenant_id: 租户 ID。

        Returns:
            使用量统计文件 Path 对象。
        """
        return self._get_tenant_dir(tenant_id) / "usage.json"

    def get_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """获取租户配置。

        读取租户的配置文件，如果配置文件不存在则返回默认配置。

        Args:
            tenant_id: 租户 ID。

        Returns:
            配置字典。
        """
        config_path = self.get_tenant_config_path(tenant_id)
        if not config_path.exists():
            return self._get_default_config(tenant_id)

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取租户配置失败: {tenant_id}, 错误: {e}")
            return self._get_default_config(tenant_id)

    def _get_default_config(self, tenant_id: str) -> Dict[str, Any]:
        """获取默认配置。

        Args:
            tenant_id: 租户 ID。

        Returns:
            默认配置字典。
        """
        return {
            "tenant_id": tenant_id,
            "language": "zh-CN",
            "timezone": "Asia/Shanghai",
            "theme": "default",
            "notification": {
                "email": True,
                "in_app": True,
            },
            "security": {
                "ip_whitelist": [],
                "session_timeout": 3600,
            },
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def save_tenant_config(self, tenant_id: str, config: Dict[str, Any]) -> None:
        """保存租户配置。

        Args:
            tenant_id: 租户 ID。
            config: 配置字典。
        """
        self.ensure_tenant_space(tenant_id)
        config_path = self.get_tenant_config_path(tenant_id)
        config["updated_at"] = time.time()

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.debug(f"保存租户配置: {tenant_id}")
        except IOError as e:
            logger.error(f"保存租户配置失败: {tenant_id}, 错误: {e}")
            raise

    def update_tenant_config(self, tenant_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新租户配置（部分更新）。

        Args:
            tenant_id: 租户 ID。
            updates: 需要更新的配置项。

        Returns:
            更新后的完整配置。
        """
        config = self.get_tenant_config(tenant_id)
        config.update(updates)
        self.save_tenant_config(tenant_id, config)
        return config

    def ensure_tenant_space(self, tenant_id: str) -> None:
        """确保租户空间存在。

        创建租户所需的所有目录和默认配置文件（如果不存在）。

        Args:
            tenant_id: 租户 ID。
        """
        tenant_dir = self._get_tenant_dir(tenant_id)
        workspace_dir = self.get_tenant_workspace(tenant_id)
        kb_dir = self.get_tenant_kb_dir(tenant_id)
        log_dir = self.get_tenant_log_dir(tenant_id)

        created = []
        if not tenant_dir.exists():
            tenant_dir.mkdir(parents=True, exist_ok=True)
            created.append("root")

        if not workspace_dir.exists():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            created.append("workspace")

        if not kb_dir.exists():
            kb_dir.mkdir(parents=True, exist_ok=True)
            created.append("knowledge")

        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
            created.append("logs")

        config_path = self.get_tenant_config_path(tenant_id)
        if not config_path.exists():
            default_config = self._get_default_config(tenant_id)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            created.append("config.json")

        usage_path = self.get_tenant_usage_path(tenant_id)
        if not usage_path.exists():
            default_usage = {
                "tenant_id": tenant_id,
                "total_api_calls": 0,
                "total_agents": 0,
                "storage_used_mb": 0.0,
                "current_month_calls": 0,
                "current_month_start": time.time(),
                "last_updated": time.time(),
            }
            with open(usage_path, "w", encoding="utf-8") as f:
                json.dump(default_usage, f, ensure_ascii=False, indent=2)
            created.append("usage.json")

        if created:
            logger.info(f"初始化租户空间: {tenant_id}, 创建项: {', '.join(created)}")

    def isolate_sandbox(self, tenant_id: str, sandbox_name: str) -> str:
        """为租户创建隔离沙箱。

        在租户工作目录下创建独立的沙箱环境，用于执行不受信代码或
        隔离特定任务的运行环境。

        Args:
            tenant_id: 租户 ID。
            sandbox_name: 沙箱名称。

        Returns:
            沙箱目录的绝对路径字符串。
        """
        self.ensure_tenant_space(tenant_id)

        if tenant_id not in self._sandbox_counter:
            self._sandbox_counter[tenant_id] = 0

        self._sandbox_counter[tenant_id] += 1
        counter = self._sandbox_counter[tenant_id]

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in sandbox_name)
        sandbox_dir_name = f"sandbox_{safe_name}_{counter}_{int(time.time())}"
        sandbox_dir = self.get_tenant_workspace(tenant_id) / sandbox_dir_name

        sandbox_dir.mkdir(parents=True, exist_ok=True)

        input_dir = sandbox_dir / "input"
        output_dir = sandbox_dir / "output"
        tmp_dir = sandbox_dir / "tmp"

        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        tmp_dir.mkdir(exist_ok=True)

        logger.info(f"创建隔离沙箱: {tenant_id}/{sandbox_dir_name}")
        return str(sandbox_dir.resolve())

    def cleanup_sandbox(self, tenant_id: str, sandbox_path: str) -> bool:
        """清理沙箱目录。

        Args:
            tenant_id: 租户 ID。
            sandbox_path: 沙箱目录路径。

        Returns:
            True 表示清理成功，False 表示失败。
        """
        sandbox_dir = Path(sandbox_path)

        workspace_dir = self.get_tenant_workspace(tenant_id)
        try:
            sandbox_dir.resolve().relative_to(workspace_dir.resolve())
        except ValueError:
            logger.error(f"沙箱路径不在租户工作目录内: {sandbox_path}")
            return False

        if not sandbox_dir.exists():
            logger.warning(f"沙箱目录不存在: {sandbox_path}")
            return True

        try:
            shutil.rmtree(sandbox_dir)
            logger.info(f"清理沙箱成功: {sandbox_path}")
            return True
        except OSError as e:
            logger.error(f"清理沙箱失败: {sandbox_path}, 错误: {e}")
            return False

    def cleanup_tenant_space(self, tenant_id: str) -> bool:
        """清理租户空间。

        删除租户的所有数据目录和文件。此操作不可逆，请谨慎使用。

        Args:
            tenant_id: 租户 ID。

        Returns:
            True 表示清理成功，False 表示失败。
        """
        tenant_dir = self._get_tenant_dir(tenant_id)

        if not tenant_dir.exists():
            logger.warning(f"租户空间不存在: {tenant_id}")
            return True

        try:
            shutil.rmtree(tenant_dir)
            if tenant_id in self._sandbox_counter:
                del self._sandbox_counter[tenant_id]
            logger.info(f"清理租户空间成功: {tenant_id}")
            return True
        except OSError as e:
            logger.error(f"清理租户空间失败: {tenant_id}, 错误: {e}")
            return False

    def get_storage_usage(self, tenant_id: str) -> float:
        """获取租户存储使用量（MB）。

        递归计算租户目录下所有文件的总大小。

        Args:
            tenant_id: 租户 ID。

        Returns:
            存储使用量（MB）。
        """
        tenant_dir = self._get_tenant_dir(tenant_id)
        if not tenant_dir.exists():
            return 0.0

        total_bytes = 0
        try:
            for dirpath, _, filenames in os.walk(tenant_dir):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    try:
                        total_bytes += os.path.getsize(file_path)
                    except OSError:
                        continue
        except OSError as e:
            logger.error(f"计算存储使用量失败: {tenant_id}, 错误: {e}")
            return 0.0

        return total_bytes / (1024 * 1024)

    def get_tenant_usage_stats(self, tenant_id: str) -> Dict[str, Any]:
        """获取租户使用量统计。

        Args:
            tenant_id: 租户 ID。

        Returns:
            使用量统计字典。
        """
        usage_path = self.get_tenant_usage_path(tenant_id)
        if not usage_path.exists():
            self.ensure_tenant_space(tenant_id)

        try:
            with open(usage_path, "r", encoding="utf-8") as f:
                usage = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取使用量统计失败: {tenant_id}, 错误: {e}")
            usage = {}

        usage["storage_used_mb"] = self.get_storage_usage(tenant_id)
        usage["last_updated"] = time.time()

        return usage

    def record_usage_local(self, tenant_id: str, action: str, cost: float = 0.0) -> None:
        """在本地记录使用量（文件级）。

        Args:
            tenant_id: 租户 ID。
            action: 操作名称。
            cost: 资源消耗量。
        """
        usage = self.get_tenant_usage_stats(tenant_id)
        now = time.time()

        usage["total_api_calls"] = usage.get("total_api_calls", 0) + 1

        month_start = usage.get("current_month_start", now)
        if now - month_start > 30 * 24 * 3600:
            usage["current_month_calls"] = 1
            usage["current_month_start"] = now
        else:
            usage["current_month_calls"] = usage.get("current_month_calls", 0) + 1

        usage["last_action"] = action
        usage["last_action_cost"] = cost
        usage["last_updated"] = now

        usage_path = self.get_tenant_usage_path(tenant_id)
        try:
            with open(usage_path, "w", encoding="utf-8") as f:
                json.dump(usage, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"记录使用量失败: {tenant_id}, 错误: {e}")

    def list_tenant_files(self, tenant_id: str, subdir: str = "") -> list[Dict[str, Any]]:
        """列出租户目录下的文件。

        Args:
            tenant_id: 租户 ID。
            subdir: 子目录（相对于租户根目录）。

        Returns:
            文件列表，每个元素包含 name、path、size、is_dir、modified_at。
        """
        tenant_dir = self._get_tenant_dir(tenant_id)
        target_dir = tenant_dir / subdir if subdir else tenant_dir

        if not target_dir.exists():
            return []

        try:
            target_dir.resolve().relative_to(tenant_dir.resolve())
        except ValueError:
            logger.error(f"路径越界: {subdir}")
            return []

        files = []
        try:
            for entry in os.scandir(target_dir):
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": str(Path(entry.path).relative_to(tenant_dir)),
                    "size": stat.st_size,
                    "is_dir": entry.is_dir(),
                    "modified_at": stat.st_mtime,
                })
        except OSError as e:
            logger.error(f"列出文件失败: {tenant_id}/{subdir}, 错误: {e}")
            return []

        return sorted(files, key=lambda x: (not x["is_dir"], x["name"]))
