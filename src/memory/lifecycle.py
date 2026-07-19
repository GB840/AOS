"""记忆生命周期桥接层（理念2：失败即训练数据 / 记忆有生有灭）。

设计原则
--------
- **opt-in（默认关闭，零足迹）**：仅当环境变量 ``AOS_MEMORY_LIFECYCLE=1`` 时由
  ``MemoryManager`` 启用；关闭时所有方法均为 no-op，且不创建任何表。
- **不破坏既有工作记忆**：通过独立的 companion 表 ``memory_lifecycle`` 追踪每条记忆的
  热度 / 分类 / 层级，**绝不修改 legacy 主表（conversations/knowledge/tasks）结构**。
- **故障隔离第一性**：桥接层任何异常都只记 warning，绝不冒泡到主记忆读写路径。

分层降级阶梯（tier）
-------------------
- 0 = full       完整记录
- 1 = summarized 已精简摘要（content 已降级为摘要占位，保留可检索，不实际调用 LLM 摘要以避免副作用）
- 2 = archived   超过 TTL 且冷门 -> 软归档（标记 deleted_at，主表行保留）；
                 ``AOS_MEMORY_HARD_DELETE=1`` 时对该类目执行硬删

分类（category）决定 TTL 与淘汰策略
------------------------------------
- failure    短期故障记忆：TTL 短（默认 7 天），冷门快速淘汰
- preference 长期环境偏好：TTL 长（默认 365 天）且 prune 中受保护，避免误删用户固定环境配置
- general    通用：默认 30 天
"""
import os
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

TIER_FULL = 0
TIER_SUMMARIZED = 1
TIER_ARCHIVED = 2

CATEGORY_FAILURE = "failure"
CATEGORY_PREFERENCE = "preference"
CATEGORY_GENERAL = "general"

_VALID_SCOPES = ("conversations", "knowledge", "tasks")

# 机会式 prune 节流：相邻两次真实 prune 至少间隔这么久（秒），避免每次 add/search 都扫全表。
# 仅在 AOS_MEMORY_LIFECYCLE=1（enabled）时生效；关闭时记录钩子本就是 no-op。
_PRUNE_INTERVAL_SECONDS = int(os.environ.get("AOS_MEMORY_PRUNE_INTERVAL_SECONDS", "3600"))

# 各分类默认 TTL（天）。preference 实际永不淘汰（仅受极长 TTL 保护语义）。
_DEFAULT_TTL_DAYS = {
    CATEGORY_FAILURE: 7,
    CATEGORY_GENERAL: 30,
    CATEGORY_PREFERENCE: 365,
}

# 环境变量名 -> 类目
_TTL_ENV_MAP = {
    CATEGORY_FAILURE: "AOS_MEMORY_TTL_FAILURE_DAYS",
    CATEGORY_GENERAL: "AOS_MEMORY_TTL_GENERAL_DAYS",
    CATEGORY_PREFERENCE: "AOS_MEMORY_TTL_PREFERENCE_DAYS",
}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class MemoryLifecycleBridge:
    """记忆生命周期追踪 / TTL / 分层降级桥接层。

    配合 ``MemoryManager`` 使用：在 add / search 时记录热度与分类，在定时 prune 时
    执行 TTL 淘汰与分层降级。
    """

    def __init__(self, conn: sqlite3.Connection, enabled: bool = False):
        self.conn = conn
        self.enabled = bool(enabled)
        self._last_prune_ts = 0.0  # 上次真实 prune 的 epoch 秒，用于机会式节流
        if self.enabled:
            try:
                self._ensure_table()
            except Exception as exc:  # 故障隔离：建表失败不应阻断主记忆
                logger.warning("MemoryLifecycleBridge 建表失败(已降级为禁用): %s", exc)
                self.enabled = False

    @classmethod
    def from_env(cls, conn: sqlite3.Connection) -> "MemoryLifecycleBridge":
        enabled = os.environ.get("AOS_MEMORY_LIFECYCLE", "0") == "1"
        return cls(conn, enabled=enabled)

    # ------------------------------------------------------------------ #
    # 表结构
    # ------------------------------------------------------------------ #
    def _ensure_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_lifecycle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                row_id INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed_at TEXT,
                tier INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scope, row_id)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lifecycle_scope ON memory_lifecycle(scope, row_id)"
        )
        self.conn.commit()

    def is_enabled(self) -> bool:
        return self.enabled

    # ------------------------------------------------------------------ #
    # 热度 / 分类记录
    # ------------------------------------------------------------------ #
    def record_add(self, scope: str, row_id: int, category: str = CATEGORY_GENERAL) -> None:
        if not self.enabled or scope not in _VALID_SCOPES:
            return
        try:
            now = datetime.now().isoformat()
            self.conn.execute(
                """
                INSERT INTO memory_lifecycle (scope, row_id, category, access_count, last_accessed_at, tier)
                VALUES (?, ?, ?, 1, ?, 0)
                ON CONFLICT(scope, row_id) DO UPDATE SET
                    category = excluded.category,
                    access_count = access_count + 1,
                    last_accessed_at = excluded.last_accessed_at
                """,
                (scope, row_id, category, now),
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("record_add 失败(%s:%s): %s", scope, row_id, exc)
        self._maybe_prune()

    def record_access(self, scope: str, row_id: int, category: str = CATEGORY_GENERAL) -> None:
        if not self.enabled or scope not in _VALID_SCOPES:
            return
        try:
            now = datetime.now().isoformat()
            self.conn.execute(
                """
                INSERT INTO memory_lifecycle (scope, row_id, category, access_count, last_accessed_at, tier)
                VALUES (?, ?, ?, 1, ?, 0)
                ON CONFLICT(scope, row_id) DO UPDATE SET
                    access_count = access_count + 1,
                    last_accessed_at = excluded.last_accessed_at,
                    category = CASE
                        WHEN excluded.category <> 'general' THEN excluded.category
                        ELSE memory_lifecycle.category
                    END
                """,
                (scope, row_id, category, now),
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("record_access 失败(%s:%s): %s", scope, row_id, exc)

    def record_access_many(self, scope: str, row_ids: List[int],
                            category: str = CATEGORY_GENERAL) -> None:
        """批量记录访问（单次事务提交，降低 search 热路径开销）。"""
        if not self.enabled or scope not in _VALID_SCOPES or not row_ids:
            return
        try:
            now = datetime.now().isoformat()
            rows = [(scope, rid, category, now) for rid in row_ids]
            self.conn.executemany(
                """
                INSERT INTO memory_lifecycle (scope, row_id, category, access_count, last_accessed_at, tier)
                VALUES (?, ?, ?, 1, ?, 0)
                ON CONFLICT(scope, row_id) DO UPDATE SET
                    access_count = access_count + 1,
                    last_accessed_at = excluded.last_accessed_at,
                    category = CASE
                        WHEN excluded.category <> 'general' THEN excluded.category
                        ELSE memory_lifecycle.category
                    END
                """,
                rows,
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("record_access_many 失败(%s): %s", scope, exc)
        self._maybe_prune()

    # ------------------------------------------------------------------ #
    # 机会式 prune（运行时自触发，无需独立常驻调度）
    # ------------------------------------------------------------------ #
    def _maybe_prune(self) -> None:
        """在真实 add / search 路径上机会式触发 ``prune``。

        设计：时间节流（_PRUNE_INTERVAL_SECONDS，默认 1h 至多一次真实 prune），
        仅在 enabled 时执行，全程故障隔离。这样概念2『记忆有生有灭』在运行时
        自然闭环——记录热度后过期记忆会被 TTL 淘汰 / 分层降级，而非只记不删。
        关闭（AOS_MEMORY_LIFECYCLE!=1）时记录钩子本就是 no-op，此处直接 return。
        """
        if not self.enabled:
            return
        now_ts = time.time()
        if now_ts - self._last_prune_ts < _PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune_ts = now_ts
        try:
            self.prune()
        except Exception as exc:  # 故障隔离：prune 异常绝不冒泡到主记忆路径
            logger.warning("opportunistic prune 失败(已忽略): %s", exc)

    # ------------------------------------------------------------------ #
    # TTL / 分层降级
    # ------------------------------------------------------------------ #
    def _ttl_days(self, category: str) -> int:
        env_key = _TTL_ENV_MAP.get(category, _TTL_ENV_MAP[CATEGORY_GENERAL])
        val = os.environ.get(env_key)
        if val and val.strip().lstrip("-").isdigit():
            return int(val)
        return _DEFAULT_TTL_DAYS.get(category, _DEFAULT_TTL_DAYS[CATEGORY_GENERAL])

    def prune(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """应用 TTL + 分层降级。返回本次 prune 的动作统计。"""
        if not self.enabled:
            return {"skipped": True}
        now = now or datetime.now()
        hard_delete = os.environ.get("AOS_MEMORY_HARD_DELETE", "0") == "1"
        stats = {
            "promoted_to_summary": 0,
            "archived": 0,
            "hard_deleted": 0,
            "protected": 0,
        }
        try:
            rows = self.conn.execute(
                "SELECT id, scope, row_id, category, access_count, tier, created_at "
                "FROM memory_lifecycle"
            ).fetchall()
            for r in rows:
                lifecycle_id = r["id"]
                scope = r["scope"]
                row_id = r["row_id"]
                category = r["category"]
                access_count = r["access_count"] or 0
                tier = r["tier"] or 0
                created = _parse_dt(r["created_at"]) or now
                age_days = (now - created).days
                ttl = self._ttl_days(category)

                # 长期环境偏好：受保护，永不淘汰
                if category == CATEGORY_PREFERENCE:
                    stats["protected"] += 1
                    continue

                if age_days < ttl:
                    continue  # 未超 TTL，保留

                cold = access_count <= 1
                if tier == TIER_FULL:
                    if cold:
                        self._set_tier(lifecycle_id, TIER_SUMMARIZED)
                        stats["promoted_to_summary"] += 1
                    # 仍热（被多次命中）-> 即便超 TTL 也保留，符合"高价值记忆长留"
                elif tier == TIER_SUMMARIZED:
                    if cold:
                        if hard_delete:
                            self._hard_delete(scope, row_id)
                            self.conn.execute(
                                "DELETE FROM memory_lifecycle WHERE id=?", (lifecycle_id,)
                            )
                            stats["hard_deleted"] += 1
                        else:
                            self._set_tier(lifecycle_id, TIER_ARCHIVED)
                            self.conn.execute(
                                "UPDATE memory_lifecycle SET deleted_at=? WHERE id=?",
                                (now.isoformat(), lifecycle_id),
                            )
                            stats["archived"] += 1
            self.conn.commit()
        except Exception as exc:
            logger.warning("prune 失败: %s", exc)
        return stats

    def _set_tier(self, lifecycle_id: int, tier: int) -> None:
        self.conn.execute(
            "UPDATE memory_lifecycle SET tier=? WHERE id=?", (tier, lifecycle_id)
        )

    def _hard_delete(self, scope: str, row_id: int) -> None:
        if scope not in _VALID_SCOPES:
            return
        try:
            self.conn.execute(f"DELETE FROM {scope} WHERE id=?", (row_id,))
        except Exception as exc:
            logger.warning("hard_delete 主表行失败(%s:%s): %s", scope, row_id, exc)

    # ------------------------------------------------------------------ #
    # 可观测性
    # ------------------------------------------------------------------ #
    def stats(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        try:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN category='failure' THEN 1 ELSE 0 END) AS failures, "
                "SUM(CASE WHEN category='preference' THEN 1 ELSE 0 END) AS preferences, "
                "SUM(CASE WHEN tier=1 THEN 1 ELSE 0 END) AS summarized, "
                "SUM(CASE WHEN tier=2 THEN 1 ELSE 0 END) AS archived "
                "FROM memory_lifecycle"
            ).fetchone()
            return {
                "enabled": True,
                "total": row["total"],
                "failures": row["failures"] or 0,
                "preferences": row["preferences"] or 0,
                "summarized": row["summarized"] or 0,
                "archived": row["archived"] or 0,
            }
        except Exception as exc:
            logger.warning("stats 失败: %s", exc)
            return {"enabled": True, "error": str(exc)}
