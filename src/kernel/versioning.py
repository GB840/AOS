"""v1.0 版本化系统：语义版本 + 多版本插件共存 + 升级迁移。

这是 v1.0 文档"版本化与向后兼容"节的代码落地。

设计原则（v1.0 物种思维）：
- 每个插件模块都有语义版本号（major.minor.patch）
- 系统支持多版本共存（旧版 agent 可在新版系统上运行）
- 升级通过迁移脚本按序执行（数据永远向前兼容，内核永远向后兼容）
- 零依赖（仅 stdlib + kernel types）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ─── 语义版本 ────────────────────────────────────────────────────

@dataclass(order=True, frozen=True)
class ModuleVersion:
    """语义版本号。支持比较和排序。

    示例：ModuleVersion(1,0,0) > ModuleVersion(0,9,9) → True
    """
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version_str: str) -> ModuleVersion:
        """从字符串解析。'2.0.0' / '0.1.0-alpha' → ModuleVersion(2,0,0)。"""
        numeric = version_str.split("-")[0]
        parts = numeric.split(".")
        return cls(
            major=int(parts[0]) if len(parts) > 0 else 0,
            minor=int(parts[1]) if len(parts) > 1 else 0,
            patch=int(parts[2]) if len(parts) > 2 else 0,
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def is_compatible_with(self, other: ModuleVersion) -> bool:
        """同 major 且 less-or-equal minor → 向前兼容。"""
        return self.major == other.major and self.minor <= other.minor


# ─── 版本化插件注册表 ────────────────────────────────────────────

@dataclass
class VersionedPlugin:
    """一个带版本号的插件注册条目。"""
    plugin_id: str                     # 唯一标识符
    kind: str                          # "model_gateway" / "agent_runtime" / "skill_bus" / "ui" / etc
    version: ModuleVersion
    factory: Callable[[], Any]         # 无参工厂函数（延迟实例化）
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class VersionRegistry:
    """支持多版本共存的插件注册表。

    允许多个版本的同名插件同时存在，系统根据版本号自动选择最新兼容版本。
    旧版 agent 通过创建时的版本号锁定其使用的插件版本。
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, List[VersionedPlugin]] = {}

    def register(self, plugin: VersionedPlugin) -> None:
        """注册一个插件版本。同 plugin_id 多版本按 version 排序。"""
        entry = self._plugins.setdefault(plugin.plugin_id, [])
        entry.append(plugin)
        entry.sort(key=lambda p: p.version, reverse=True)  # 降序：最新在前

    def get_latest(self, plugin_id: str) -> Optional[VersionedPlugin]:
        """获取最新版本。"""
        entries = self._plugins.get(plugin_id)
        return entries[0] if entries else None

    def get_compatible(self, plugin_id: str, required: ModuleVersion) -> Optional[VersionedPlugin]:
        """获取与 required 兼容的最新版本（同 major, >= required）。"""
        entries = self._plugins.get(plugin_id)
        if not entries:
            return None
        for p in entries:
            if p.version.major == required.major and p.version >= required:
                return p
        return None

    def get_exact(self, plugin_id: str, version: ModuleVersion) -> Optional[VersionedPlugin]:
        """精确版本查找。"""
        entries = self._plugins.get(plugin_id)
        if not entries:
            return None
        for p in entries:
            if p.version == version:
                return p
        return None

    def list_versions(self, plugin_id: str) -> List[ModuleVersion]:
        """列出某插件的所有已注册版本。"""
        entries = self._plugins.get(plugin_id, [])
        return [p.version for p in entries]

    def list_all(self, kind: str | None = None) -> List[VersionedPlugin]:
        """列出所有插件，可按 kind 过滤。"""
        result: List[VersionedPlugin] = []
        for entries in self._plugins.values():
            for p in entries:
                if kind is None or p.kind == kind:
                    result.append(p)
        return sorted(result, key=lambda p: (p.plugin_id, p.version), reverse=True)

    def remove(self, plugin_id: str, version: ModuleVersion | None = None) -> int:
        """移除插件。version=None 时移除所有版本，返回移除数量。"""
        entries = self._plugins.get(plugin_id)
        if not entries:
            return 0
        if version is None:
            count = len(entries)
            del self._plugins[plugin_id]
            return count
        before = len(entries)
        self._plugins[plugin_id] = [p for p in entries if p.version != version]
        after = len(self._plugins[plugin_id])
        if after == 0:
            del self._plugins[plugin_id]
        return before - after


# ─── 升级迁移管理器 ──────────────────────────────────────────────

class Migration:
    """单次迁移脚本：从 from_version 迁移到 to_version。"""

    def __init__(self, from_version: str, to_version: str,
                 script: Callable[[Dict[str, Any]], Dict[str, Any]],
                 description: str = "") -> None:
        self.from_version = ModuleVersion.parse(from_version)
        self.to_version = ModuleVersion.parse(to_version)
        self.script = script
        self.description = description

    def apply(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return self.script(config)


class UpgradeManager:
    """版本升级编排器。

    读取当前配置版本，按迁移脚本链按序执行，确保数据和设置完好。
    内核不改，数据向前兼容。

    用法：
        mgr = UpgradeManager()
        mgr.register_migration(Migration("1.0.0", "1.1.0", lambda c: {**c, "new": True}))
        mgr.register_migration(Migration("1.1.0", "2.0.0", ...))
        upgraded = mgr.upgrade(current_config, target="2.0.0")
    """

    def __init__(self) -> None:
        self._migrations: List[Migration] = []

    def register_migration(self, migration: Migration) -> None:
        self._migrations.append(migration)
        # 按 from_version 排序，确保迁移链顺序
        self._migrations.sort(key=lambda m: m.from_version)

    def get_chain(self, from_version: str,
                  to_version: str) -> Optional[List[Migration]]:
        """获取从 from_version 到 to_version 的迁移链。

        使用拓扑序：从 from_version 出发，贪心选择第一条迁移，
        持续执行直到抵达 to_version 或无法继续。
        """
        fv = ModuleVersion.parse(from_version)
        tv = ModuleVersion.parse(to_version)
        if fv >= tv:
            return None  # 不需要迁移或无法倒退

        chain: List[Migration] = []
        current = fv
        visited: set[str] = set()
        while current < tv:
            found = False
            for m in self._migrations:
                if m.from_version == current and str(m.to_version) not in visited:
                    chain.append(m)
                    visited.add(str(m.to_version))
                    current = m.to_version
                    found = True
                    break
            if not found:
                # 无迁移可达 to_version
                return None
        return chain

    def upgrade(self, config: Dict[str, Any],
                target: str) -> Dict[str, Any]:
        """执行完整升级链，返回迁移后的配置。"""
        current_version = config.get("version", "0.0.0")
        chain = self.get_chain(current_version, target)
        if chain is None:
            raise ValueError(
                f"无法从 {current_version} 升级到 {target}：迁移链不完整")
        result = dict(config)
        for migration in chain:
            result = migration.apply(result)
            result["version"] = str(migration.to_version)
        return result

    @property
    def migration_count(self) -> int:
        return len(self._migrations)


# ─── 便捷工厂 ────────────────────────────────────────────────────

def version_plugin(plugin_id: str, kind: str, version: str,
                   factory: Callable[[], Any],
                   description: str = "",
                   **metadata: Any) -> VersionedPlugin:
    """一句话版本化注册一个插件。"""
    return VersionedPlugin(
        plugin_id=plugin_id,
        kind=kind,
        version=ModuleVersion.parse(version),
        factory=factory,
        description=description,
        metadata=metadata,
    )


__all__ = [
    "Migration",
    "ModuleVersion",
    "UpgradeManager",
    "VersionedPlugin",
    "VersionRegistry",
    "version_plugin",
]
