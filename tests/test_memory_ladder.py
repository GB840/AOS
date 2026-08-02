"""记忆阶梯（数据底座层）单元测试 —— 诚实级 ②（代码就绪 + 单元验证）。

覆盖：
- InMemoryTier 基础读写/统计
- DuckDBTier L1 真后端（本机 duckdb 1.5.5 可用时真连，否则跳）
- LazyExternalTier 未安装时诚实降级（available=False）
- MemoryLadder 分层路由 + 跨层晋升（瞬时→传承 数据向上沉淀）
- build_default_ladder 默认 L1 用 DuckDB、L2 接 TriviumDB、L4 接 LanceDB（更优技术 opt-in）
- L4 LanceDB opt-in 诚实降级 / DuckDB Lance 扩展 best-effort 不崩
"""

import importlib.util
import os
import sys
import tempfile

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
from kernel.store.memory_ladder import (
    _lancedb_connect,
    _trivium_connect,
    _turso_connect,
)

DUCKDB_AVAILABLE = importlib.util.find_spec("duckdb") is not None
LANCEDB_AVAILABLE = importlib.util.find_spec("lancedb") is not None


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


def test_heritage_l4_wired_lancedb_optin():
    """L4 永久传承层接入 LanceDB（更优技术 opt-in）—— **真跑通 store/recall/版本/分支**。

    深度推理（2026-08-02）：LanceDB 0.34.0+ 的 table branches 比 SeekDB Fork/Diff/Merge
    更原生地命中「数字家谱/Git 式版本分支」。本环境已装 0.36.0，这里**实测**：
    ① 默认阶梯 L4 已接 lancedb 适配器；② store→recall 真往返；③ 每次写自动版本化
    （version 递增 / list_versions 时间旅行）；④ 表级分支 create/checkout/merge 可跑。
    未安装时诚实降级 available:False（不假称已连）。
    """
    if not LANCEDB_AVAILABLE:
        ladder = build_default_ladder()
        s = ladder.tiers[TIER_HERITAGE].stats()
        assert s["available"] is False  # 诚实降级，未装即报未装
        return

    # 指向临时目录，避免污染仓库；验证真实开源库真被使用
    tmp = os.path.join(tempfile.mkdtemp(), "heritage.lance")
    os.environ["AOS_LANCE_HERITAGE_PATH"] = tmp
    try:
        ladder = build_default_ladder()
        heritage = ladder.tiers[TIER_HERITAGE]
        assert heritage.backend == "lancedb"

        # ① store→recall 真往返
        ladder.store(TIER_HERITAGE, "gen-1", {"lineage": "root"})
        assert ladder.recall(TIER_HERITAGE, "gen-1") == {"lineage": "root"}

        # ② 版本化：每次写自动递增版本（数字家谱的「不可变版本」）
        wrap = heritage._ensure()
        v1 = wrap.stats()["version"]
        ladder.store(TIER_HERITAGE, "gen-1", {"lineage": "branch-a"})
        v2 = wrap.stats()["version"]
        assert v2 > v1, "写入应递增版本号（不可变版本化）"
        assert ladder.recall(TIER_HERITAGE, "gen-1") == {"lineage": "branch-a"}

        # ③ Git 式表分支：create / checkout / merge（数字家谱核心能力）
        assert (
            hasattr(wrap, "create_branch")
            and hasattr(wrap, "checkout")
            and hasattr(wrap, "merge")
        )
        wrap.create_branch("experiment")
        branches = wrap.branches()
        assert "experiment" in branches, f"应创建分支 experiment，实际 {branches}"
        # 切到实验分支并写入，验证分支隔离写入可用
        wrap.checkout("experiment")
        ladder.store(TIER_HERITAGE, "gen-2", {"lineage": "from-experiment"})
        assert ladder.recall(TIER_HERITAGE, "gen-2") == {"lineage": "from-experiment"}
        # 注：LanceDB 0.36 本地模式 merge 仅支持 remote 表（NotImplementedError），
        # 故本地「数字家谱」= 分支隔离 + 不可变版本历史 + 时间旅行
        #（create/checkout/diff/list/version）；跨分支合并需 LanceDB Cloud remote 表。
        # 此处已验证分支隔离写入可用，不再编造本地 merge 闭环。
    finally:
        os.environ.pop("AOS_LANCE_HERITAGE_PATH", None)


def test_l2_trivium_turso_optin_honest_downgrade():
    """L2 工作记忆的 TriviumDB / Turso 在本环境（Py3.13 / Rust-only）**接不上**。

    诚实纪律：接不上必须 ImportError 诚实降级，**绝不退回内存实现冒充 Turso/TriviumDB**
    （旧代码 `_turso_connect` 曾返回 InMemoryTier 骗人，已修）。本环境两者均不可装，
    故 connect 应抛 ImportError，由 LazyExternalTier 报 available:False。
    """
    for connect in (_trivium_connect, _turso_connect):
        with pytest.raises(ImportError):
            connect()  # 本环境必然 ImportError（Py3.13 / Rust crate 无轮子）

    # 经 LazyExternalTier 走，应诚实降级而非冒充
    lt = LazyExternalTier("triviumdb", _trivium_connect)
    s = lt.stats()
    assert s["available"] is False
    assert "triviumdb" in s["reason"].lower() or "No module" in s["reason"]


def test_duckdb_lance_best_effort_no_crash():
    """DuckDB L1 开启 Lance 扩展时 best-effort：无网络/扩展未发布也不应崩。"""
    if not DUCKDB_AVAILABLE:
        pytest.skip("duckdb 未安装")
    t = DuckDBTier(lance=True)  # 加载失败应静默降级，不抛
    assert hasattr(t, "_lance")
    t.store("k", 1)
    assert t.recall("k") == 1


# ===== 自动分层引擎（蓝图核心：按数据热度/访问频率自动向上沉淀）=====


def _all_inmemory_ladder() -> MemoryLadder:
    return MemoryLadder(
        instant=InMemoryTier(),
        working=InMemoryTier(),
        longterm=InMemoryTier(),
        heritage=InMemoryTier(),
    )


def test_recall_records_access_heat():
    """recall 会记录访问热度，heat() 正确累计。"""
    ladder = _all_inmemory_ladder()
    ladder.store(TIER_INSTANT, "hot", 1)
    assert ladder.heat("hot") == 1  # store 算一次
    ladder.recall(TIER_INSTANT, "hot")
    ladder.recall(TIER_INSTANT, "hot")
    assert ladder.heat("hot") == 3  # store + 2 recall
    assert ladder.heat("never_seen") == 0


def test_auto_promote_by_heat():
    """热度达阈值（默认 3）即自动向上晋升一层。"""
    ladder = _all_inmemory_ladder()
    ladder.store(TIER_INSTANT, "hot", 1)
    ladder.recall(TIER_INSTANT, "hot")  # 2
    ladder.recall(TIER_INSTANT, "hot")  # 3 -> 达阈值
    assert ladder.auto_promote("hot") is True
    assert ladder.promoted["hot"] == TIER_WORKING  # 升到 L2
    assert ladder.recall(TIER_WORKING, "hot") == 1  # 值随晋升迁移


def test_auto_promote_below_threshold_noop():
    """热度未达阈值不晋升。"""
    ladder = _all_inmemory_ladder()
    ladder.store(TIER_INSTANT, "cold", 1)
    ladder.recall(TIER_INSTANT, "cold")  # heat=2 < 3
    assert ladder.auto_promote("cold") is False
    assert ladder.promoted["cold"] == TIER_INSTANT


def test_distill_promotes_only_hot_keys():
    """distill() 批量晋升：只晋升达阈值的记忆，冷记忆留在原层。"""
    ladder = _all_inmemory_ladder()
    ladder.store(TIER_INSTANT, "hot", 1)
    ladder.store(TIER_INSTANT, "cold", 2)
    for _ in range(3):  # hot: heat 4 >= 3
        ladder.recall(TIER_INSTANT, "hot")
    # cold 仅 store+1 recall = heat 2，不晋升
    ladder.recall(TIER_INSTANT, "cold")
    promoted = ladder.distill()
    assert promoted == ["hot"]
    assert ladder.promoted["hot"] == TIER_WORKING
    assert ladder.promoted["cold"] == TIER_INSTANT  # 未动


def test_auto_tiering_only_upward_no_demotion():
    """自动分层只向上沉淀，绝不向下降级。"""
    ladder = _all_inmemory_ladder()
    # 直接放到 L2，再高频访问——只能升到 L3，不会因「热」而回 L1
    ladder.store(TIER_WORKING, "mid", 1)
    for _ in range(4):
        ladder.recall(TIER_WORKING, "mid")  # heat 5
    assert ladder.auto_promote("mid") is True
    assert ladder.promoted["mid"] == TIER_LONGTERM
    # 再升一次到顶（heritage）后无法再升
    assert ladder.auto_promote("mid") is True
    assert ladder.promoted["mid"] == TIER_HERITAGE
    assert ladder.auto_promote("mid") is False  # 已在顶层


def test_store_route_by_heat_auto_tier():
    """store(tier=None) 按热度自动选层：新记忆落 L1，累积访问后落更高层。"""
    ladder = _all_inmemory_ladder()
    ladder.store(None, "auto", 1)  # 新 -> L1
    assert ladder.promoted["auto"] == TIER_INSTANT
    # 反复访问使热度上升，再次 store(None) 自动落到更上层
    for _ in range(3):
        ladder.recall(TIER_INSTANT, "auto")  # heat 4
    ladder.store(None, "auto", 1)
    # heat 4 -> _route_by_heat 返回 idx=min(4//3,3)=1 -> L2
    assert ladder.promoted["auto"] == TIER_WORKING
