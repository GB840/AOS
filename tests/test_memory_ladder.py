"""记忆阶梯（数据底座层）单元测试 —— 诚实级 ②（代码就绪 + 单元验证）。

覆盖：
- InMemoryTier 基础读写/统计
- DuckDBTier L1 真后端（本机 duckdb 1.5.4 可用时真连，否则跳）
- LazyExternalTier 未安装时诚实降级（available=False）
- MemoryLadder 分层路由 + 跨层晋升（瞬时→传承 数据向上沉淀）
- build_default_ladder 默认 L1 用 DuckDB、L2 接 TriviumDB 适配器骨架
"""

import importlib.util
import sys

import pytest

from kernel.store import (
    DuckDBTier,
    InMemoryTier,
    LazyExternalTier,
    MemoryLadder,
    TIER_HERITAGE,
    TIER_INSTANT,
    TIER_LONGTERM,
    TIER_WORKING,
    build_default_ladder,
)

DUCKDB_AVAILABLE = importlib.util.find_spec("duckdb") is not None


def test_inmemory_tier_store_recall_stats():
    t = InMemoryTier()
    t.store("a", {"x": 1}, source="test")
    assert t.recall("a") == {"x": 1}
    assert t.recall("missing") is None
    s = t.stats()
    assert s["count"] == 1 and s["written"] == 1


def test_duckdb_tier_real_backend():
    if not DUCKDB_AVAILABLE:
        pytest.skip("duckdb 未安装，跳过真后端")
    t = DuckDBTier()  # 内存库
    t.store("k1", "v1", ts=1)
    t.store("k1", "v2", ts=2)  # 同 key 二次写，取最新
    assert t.recall("k1") == "v2"
    assert t.stats()["count"] == 2
    # 新实例持久路径也能落盘
    import tempfile, os

    p = os.path.join(tempfile.mkdtemp(), "l.db")
    t2 = DuckDBTier(p)
    t2.store("p", 99)
    assert t2.recall("p") == 99


def test_lazy_external_tier_graceful_when_missing():
    # 用一个必定不存在的包模拟“未安装”，验证诚实降级
    def fake_connect():
        raise ImportError("no-such-pkg is not installed")

    lt = LazyExternalTier("no-such-pkg", fake_connect)
    s = lt.stats()
    assert s["available"] is False and "not installed" in s["reason"]


def test_ladder_routes_by_tier():
    ladder = MemoryLadder()
    ladder.store(TIER_INSTANT, "evt", {"v": 1})
    ladder.store(TIER_LONGTERM, "fact", {"v": 2})
    assert ladder.recall(TIER_INSTANT, "evt") == {"v": 1}
    assert ladder.recall(TIER_LONGTERM, "fact") == {"v": 2}
    # 不同层同 key 互不干扰
    ladder.store(TIER_WORKING, "evt", {"v": 9})
    assert ladder.recall(TIER_INSTANT, "evt") == {"v": 1}
    assert ladder.recall(TIER_WORKING, "evt") == {"v": 9}


def test_ladder_promote_upward():
    ladder = MemoryLadder()
    ladder.store(TIER_INSTANT, "memory-1", "raw-sense")
    # 瞬时 → 传承：晋升成功，数据向上沉淀
    assert ladder.promote("memory-1", TIER_HERITAGE) is True
    assert ladder.recall(TIER_HERITAGE, "memory-1") == "raw-sense"
    assert ladder.promoted["memory-1"] == TIER_HERITAGE


def test_ladder_promote_rejects_downward():
    ladder = MemoryLadder()
    ladder.store(TIER_HERITAGE, "root", "permanent")
    # 传承 → 瞬时：不允许降序
    assert ladder.promote("root", TIER_INSTANT) is False


def test_ladder_promote_unknown_key():
    ladder = MemoryLadder()
    assert ladder.promote("nope", TIER_HERITAGE) is False


def test_build_default_ladder_uses_duckdb_for_l1():
    ladder = build_default_ladder()
    # L1 默认 DuckDB（可用时），否则 InMemory；两种都应是真后端名
    inst_name = ladder.tiers[TIER_INSTANT].name
    assert inst_name in ("duckdb", "inmemory")
    # L2 接了 TriviumDB 惰性适配器骨架
    assert ladder.tiers[TIER_WORKING].backend == "triviumdb"
    # 默认阶梯可正常写 L1
    ladder.store(TIER_INSTANT, "x", 1)
    assert ladder.recall(TIER_INSTANT, "x") == 1


def test_ladder_stats_aggregates_all_tiers():
    ladder = MemoryLadder(
        instant=InMemoryTier(),
        working=InMemoryTier(),
        longterm=InMemoryTier(),
        heritage=InMemoryTier(),
    )
    ladder.store(TIER_INSTANT, "a", 1)
    ladder.store(TIER_HERITAGE, "b", 2)
    s = ladder.stats()
    assert s[TIER_INSTANT]["count"] == 1
    assert s[TIER_HERITAGE]["count"] == 1
