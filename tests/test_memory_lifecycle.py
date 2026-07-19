"""记忆生命周期桥接层测试（理念2：TTL + 分层降级，opt-in）。

覆盖：
- 禁用态零足迹（no-op，不建表）
- 热度 / 分类记录
- 分层降级阶梯（full -> summarized -> archived，软归档 / 硬删）
- 长期环境偏好受保护
- TTL 环境变量覆盖与未超 TTL 不淘汰
- 批量访问记录
- 与 MemoryManager 的 opt-in 集成
- **机会式 prune 经真实 add / search 路径触发**（概念2『记忆有生有灭』闭环，非只记录不淘汰）
- MemoryManager.prune_lifecycle() 委派
"""
import os
import time
import sqlite3
from datetime import datetime, timedelta

import pytest

from memory.lifecycle import (
    MemoryLifecycleBridge,
    CATEGORY_FAILURE,
    CATEGORY_PREFERENCE,
    CATEGORY_GENERAL,
    TIER_FULL,
    TIER_SUMMARIZED,
    TIER_ARCHIVED,
)


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_disabled_is_noop_and_no_table():
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=False)
    assert bridge.is_enabled() is False
    bridge.record_add("conversations", 1, CATEGORY_FAILURE)
    bridge.record_access("conversations", 1)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "memory_lifecycle" not in tables
    assert bridge.prune() == {"skipped": True}
    assert bridge.stats() == {"enabled": False}


def test_enabled_creates_table_and_records_heat():
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "memory_lifecycle" in tables

    bridge.record_add("conversations", 1, CATEGORY_FAILURE)
    bridge.record_access("conversations", 1)
    bridge.record_access("conversations", 1)

    st = bridge.stats()
    assert st["total"] == 1
    assert st["failures"] == 1
    cnt = conn.execute(
        "SELECT access_count FROM memory_lifecycle WHERE scope='conversations' AND row_id=1"
    ).fetchone()["access_count"]
    # 1(add 内部 +1) + 2(access) = 3
    assert cnt == 3


def test_prune_failure_ladder_soft_archive():
    os.environ.pop("AOS_MEMORY_HARD_DELETE", None)
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    old = (datetime.now() - timedelta(days=40)).isoformat()
    conn.execute(
        "INSERT INTO memory_lifecycle (scope, row_id, category, access_count, last_accessed_at, tier, created_at) "
        "VALUES ('conversations', 99, 'failure', 1, ?, 0, ?)",
        (old, old),
    )
    conn.commit()
    now = datetime.now()

    stats = bridge.prune(now=now)
    assert stats["promoted_to_summary"] == 1
    assert conn.execute("SELECT tier FROM memory_lifecycle WHERE row_id=99").fetchone()["tier"] == TIER_SUMMARIZED

    stats2 = bridge.prune(now=now)
    assert stats2["archived"] == 1
    assert conn.execute("SELECT tier FROM memory_lifecycle WHERE row_id=99").fetchone()["tier"] == TIER_ARCHIVED
    # 软归档：companion 行仍在（仅标记 deleted_at）
    assert conn.execute("SELECT deleted_at FROM memory_lifecycle WHERE row_id=99").fetchone()["deleted_at"] is not None


def test_preference_protected_from_prune():
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    old = (datetime.now() - timedelta(days=400)).isoformat()
    conn.execute(
        "INSERT INTO memory_lifecycle (scope, row_id, category, access_count, last_accessed_at, tier, created_at) "
        "VALUES ('knowledge', 5, 'preference', 0, ?, 0, ?)",
        (old, old),
    )
    conn.commit()
    stats = bridge.prune(now=datetime.now())
    assert stats["protected"] == 1
    assert conn.execute("SELECT tier FROM memory_lifecycle WHERE row_id=5").fetchone()["tier"] == TIER_FULL


def test_ttl_env_override_and_within_ttl_not_pruned(monkeypatch):
    monkeypatch.setenv("AOS_MEMORY_TTL_FAILURE_DAYS", "3")
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    recent = (datetime.now() - timedelta(days=2)).isoformat()
    conn.execute(
        "INSERT INTO memory_lifecycle (scope, row_id, category, access_count, tier, created_at) "
        "VALUES ('conversations', 7, 'failure', 1, 0, ?)",
        (recent,),
    )
    conn.commit()
    stats = bridge.prune(now=datetime.now())
    assert stats["promoted_to_summary"] == 0


def test_record_access_many_batches_without_duplicating():
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    bridge.record_access_many("knowledge", [1, 2, 3])
    assert conn.execute("SELECT COUNT(*) FROM memory_lifecycle").fetchone()[0] == 3
    bridge.record_access_many("knowledge", [1, 2, 3])
    # 行数不变，命中计数 +1
    assert conn.execute("SELECT COUNT(*) FROM memory_lifecycle").fetchone()[0] == 3
    assert conn.execute("SELECT access_count FROM memory_lifecycle WHERE row_id=1").fetchone()[0] == 2


def test_hard_delete_removes_main_row_when_flagged():
    os.environ["AOS_MEMORY_HARD_DELETE"] = "1"
    try:
        conn = _conn()
        conn.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY, content TEXT)")
        conn.execute("INSERT INTO conversations VALUES (42, 'x')")
        bridge = MemoryLifecycleBridge(conn, enabled=True)
        old = (datetime.now() - timedelta(days=40)).isoformat()
        conn.execute(
            "INSERT INTO memory_lifecycle (scope, row_id, category, access_count, tier, created_at) "
            "VALUES ('conversations', 42, 'failure', 1, 1, ?)",
            (old,),
        )
        conn.commit()
        stats = bridge.prune(now=datetime.now())
        assert stats["hard_deleted"] == 1
        assert conn.execute("SELECT id FROM conversations WHERE id=42").fetchone() is None
        assert conn.execute("SELECT id FROM memory_lifecycle WHERE row_id=42").fetchone() is None
    finally:
        os.environ.pop("AOS_MEMORY_HARD_DELETE", None)


def test_memory_manager_lifecycle_integration(monkeypatch, tmp_path):
    from memory import memory as memory_module
    from memory.memory import MemoryManager
    from utils.config import config

    monkeypatch.setattr(memory_module, "CHROMADB_AVAILABLE", False)
    monkeypatch.setattr(memory_module, "ZVEC_AVAILABLE", False)
    monkeypatch.setattr(config, "SQLITE_DB_PATH", str(tmp_path / "mem.db"))
    monkeypatch.setattr(config, "CHROMADB_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(config, "VECTOR_COLLECTION_NAME", "test_mem")
    monkeypatch.setenv("AOS_MEMORY_LIFECYCLE", "1")

    mm = MemoryManager()
    try:
        assert mm.lifecycle is not None
        assert mm.lifecycle.is_enabled() is True

        cid = mm.add_conversation("sess1", "user", "hello failure", category=CATEGORY_FAILURE)
        st = mm.lifecycle.stats()
        assert st["total"] == 1
        assert st["failures"] == 1

        # 搜索记录命中热度
        mm.search_conversations("hello")
        cnt = mm.lifecycle.conn.execute(
            "SELECT access_count FROM memory_lifecycle WHERE scope='conversations' AND row_id=?",
            (cid,),
        ).fetchone()["access_count"]
        assert cnt >= 2  # 1(add) + >=1(search)

        # 分类标记持久化
        assert mm.lifecycle.conn.execute(
            "SELECT category FROM memory_lifecycle WHERE scope='conversations' AND row_id=?",
            (cid,),
        ).fetchone()["category"] == CATEGORY_FAILURE
    finally:
        mm.close()


def _insert_expired(bridge, conn, row_id, category=CATEGORY_FAILURE, age_days=40, tier=TIER_FULL):
    old = (datetime.now() - timedelta(days=age_days)).isoformat()
    conn.execute(
        "INSERT INTO memory_lifecycle (scope, row_id, category, access_count, tier, created_at) "
        "VALUES ('conversations', ?, ?, 1, ?, ?)",
        (row_id, category, tier, old),
    )
    conn.commit()


def test_opportunistic_prune_fires_via_record_add():
    """概念2 真闭环：add 路径上过期记忆被自动 prune（分层降级），而非只记不删。"""
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    _insert_expired(bridge, conn, 9001)  # 40 天前的 failure（TTL 7天），冷门
    bridge._last_prune_ts = 0.0  # 强制节流放行

    bridge.record_add("conversations", 99999, CATEGORY_GENERAL)  # 触发 _maybe_prune

    assert conn.execute("SELECT tier FROM memory_lifecycle WHERE row_id=9001").fetchone()["tier"] == TIER_SUMMARIZED


def test_opportunistic_prune_throttled_within_interval():
    """节流：距上次 prune 不足间隔时不扫表，过期记忆保持原 tier。"""
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    _insert_expired(bridge, conn, 9002)
    bridge._last_prune_ts = time.time()  # 刚 prune 过，节流未过

    bridge.record_add("conversations", 99998, CATEGORY_GENERAL)

    assert conn.execute("SELECT tier FROM memory_lifecycle WHERE row_id=9002").fetchone()["tier"] == TIER_FULL


def test_opportunistic_prune_fires_via_record_access_many():
    """search 热路径（record_access_many）同样触发机会式 prune。"""
    conn = _conn()
    bridge = MemoryLifecycleBridge(conn, enabled=True)
    _insert_expired(bridge, conn, 9003)
    bridge._last_prune_ts = 0.0

    bridge.record_access_many("conversations", [123, 124, 125])

    assert conn.execute("SELECT tier FROM memory_lifecycle WHERE row_id=9003").fetchone()["tier"] == TIER_SUMMARIZED


def test_memory_manager_prune_lifecycle_delegates(monkeypatch, tmp_path):
    """MemoryManager.prune_lifecycle() 委派到桥接层；禁用态返回 {"enabled": False}。"""
    from memory import memory as memory_module
    from memory.memory import MemoryManager
    from utils.config import config

    monkeypatch.setattr(memory_module, "CHROMADB_AVAILABLE", False)
    monkeypatch.setattr(memory_module, "ZVEC_AVAILABLE", False)
    monkeypatch.setattr(config, "SQLITE_DB_PATH", str(tmp_path / "mem2.db"))
    monkeypatch.setattr(config, "CHROMADB_PERSIST_DIR", str(tmp_path / "chroma2"))
    monkeypatch.setattr(config, "VECTOR_COLLECTION_NAME", "test_mem2")
    monkeypatch.setenv("AOS_MEMORY_LIFECYCLE", "1")

    mm = MemoryManager()
    try:
        # 写入一条过期失败记忆，显式 prune 应分层降级
        mm.lifecycle.conn.execute(
            "INSERT INTO memory_lifecycle (scope, row_id, category, access_count, tier, created_at) "
            "VALUES ('conversations', 7001, 'failure', 1, 0, ?)",
            ((datetime.now() - timedelta(days=40)).isoformat(),),
        )
        mm.lifecycle.conn.commit()
        stats = mm.prune_lifecycle()
        assert stats.get("promoted_to_summary", 0) >= 1
        assert mm.lifecycle.conn.execute(
            "SELECT tier FROM memory_lifecycle WHERE row_id=7001"
        ).fetchone()["tier"] == TIER_SUMMARIZED
    finally:
        mm.close()

    # 禁用态（AOS_MEMORY_LIFECYCLE=0）：bridge 仍存在但 enabled=False，
    # prune_lifecycle 返回 {"enabled": False} 且不触碰任何表
    monkeypatch.setenv("AOS_MEMORY_LIFECYCLE", "0")
    mm2 = MemoryManager()
    try:
        assert mm2.lifecycle is not None
        assert mm2.lifecycle.is_enabled() is False
        assert mm2.prune_lifecycle() == {"enabled": False}
    finally:
        mm2.close()
