"""记忆阶梯（数据底座层）存储抽象。

把蓝图「四层阶梯式融合架构」落地为可运行的代码骨架：
- L1 瞬时感知层（DuckDB，本机已实测 duckdb 1.5.4 可 import）
- L2 工作记忆层（TriviumDB / Turso，opt-in 惰性适配器）
- L3 长期语义层（复用 AOS 既有 Chroma/cognee；KowitoDB/txtai 仅参考）
- L4 永久传承层（SeekDB 参考；默认文件版本归档）

诚实纪律：所有外部依赖惰性 import，缺失即优雅降级到内存实现，
保证 ② 单元可测；外部库的运行时真连仅留适配器骨架，未做 ③ 端到端验证。
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

# 四层名称常量（与白皮书第十一章对应）
TIER_INSTANT = "instant"      # L1 瞬时感知
TIER_WORKING = "working"      # L2 工作记忆
TIER_LONGTERM = "longterm"    # L3 长期语义
TIER_HERITAGE = "heritage"    # L4 永久传承

TIER_ORDER = [TIER_INSTANT, TIER_WORKING, TIER_LONGTERM, TIER_HERITAGE]


class MemoryTier:
    """记忆阶梯某一层的抽象接口。所有后端都实现 store/recall/stats。"""

    name = "tier"

    def store(self, key: str, value: Any, **meta: Any) -> None:
        raise NotImplementedError

    def recall(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def stats(self) -> Dict[str, Any]:
        raise NotImplementedError


class InMemoryTier(MemoryTier):
    """无外部依赖的内存实现，用于测试与无外部依赖场景（默认降级后端）。"""

    name = "inmemory"

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._written = 0

    def store(self, key: str, value: Any, **meta: Any) -> None:
        self._store[key] = value
        self._meta[key] = dict(meta, ts=time.time())
        self._written += 1

    def recall(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def stats(self) -> Dict[str, Any]:
        return {"name": self.name, "count": len(self._store), "written": self._written}


class DuckDBTier(MemoryTier):
    """L1 瞬时感知层：DuckDB 列式实时统计。

    本机实测 duckdb 1.5.4 在 Python 3.14 下可直接 import，故作为 L1 真后端。
    适合 mirror_branch 的实时统计、生命周期数据复盘。
    """

    name = "duckdb"

    def __init__(self, path: str = ":memory:") -> None:
        import duckdb  # 惰性 import；缺失则构造时抛 ImportError，由 MemoryLadder 降级

        self._con = duckdb.connect(path)
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS ladder_kv (k VARCHAR, v JSON, ts DOUBLE)"
        )

    def store(self, key: str, value: Any, **meta: Any) -> None:
        self._con.execute(
            "INSERT INTO ladder_kv VALUES (?, ?, ?)",
            [key, json.dumps({"value": value, "meta": meta}), time.time()],
        )

    def recall(self, key: str) -> Optional[Any]:
        row = self._con.execute(
            "SELECT v FROM ladder_kv WHERE k=? ORDER BY ts DESC LIMIT 1", [key]
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])["value"]

    def stats(self) -> Dict[str, Any]:
        n = self._con.execute("SELECT COUNT(*) FROM ladder_kv").fetchone()[0]
        return {"name": self.name, "count": n}


class LazyExternalTier(MemoryTier):
    """opt-in 外部库适配器骨架。

    仅在对应库已安装时通过 ``connect`` 工厂建立真实连接；否则调用即抛
    ImportError（清晰告知需 pip install）。不强制任何重型依赖，符合选型铁律。
    """

    name = "external"

    def __init__(self, backend: str, connect: Callable[[], MemoryTier]) -> None:
        self.backend = backend
        self._connect = connect
        self._inner: Optional[MemoryTier] = None

    def _ensure(self) -> MemoryTier:
        if self._inner is None:
            self._inner = self._connect()
        return self._inner

    def store(self, key: str, value: Any, **meta: Any) -> None:
        self._ensure().store(key, value, **meta)

    def recall(self, key: str) -> Optional[Any]:
        return self._ensure().recall(key)

    def stats(self) -> Dict[str, Any]:
        try:
            inner = self._ensure()
            s = inner.stats()
            s["backend"] = self.backend
            return s
        except ImportError as exc:  # 未安装：诚实告知
            return {"name": self.name, "backend": self.backend, "available": False, "reason": str(exc)}


def _trivium_connect() -> MemoryTier:
    """TriviumDB 连接工厂（L2 工作记忆）。需 ``pip install triviumdb``。"""
    import triviumdb  # 缺失即 ImportError

    db = triviumdb.TriviumDB("particle.tdb", dim=384)
    # 包装为 MemoryTier 接口
    class _Wrap(MemoryTier):
        name = "triviumdb"

        def store(self, key, value, **meta):
            db.insert([0.0] * 384, {"key": key, "value": value, **meta})

        def recall(self, key):
            return None  # 向量检索需 query 向量，read 接口按需扩展

        def stats(self):
            return {"name": self.name, "count": 0}

    return _Wrap()


def _turso_connect() -> MemoryTier:
    """Turso/libSQL 连接工厂（L2 工作记忆，每粒子一库）。需 libsql Python 绑定。"""
    import libsql  # 缺失即 ImportError

    # 真实接入在此展开；骨架阶段返回内存实现并标注 backend
    t = InMemoryTier()
    t.name = "turso"
    return t


class MemoryLadder:
    """四层记忆阶梯编排器：按层路由 store/recall，并支持跨层晋升（数据向上沉淀）。"""

    def __init__(
        self,
        instant: Optional[MemoryTier] = None,
        working: Optional[MemoryTier] = None,
        longterm: Optional[MemoryTier] = None,
        heritage: Optional[MemoryTier] = None,
    ) -> None:
        # L1 默认 DuckDB（可用时），否则内存；L2/L3/L4 默认内存，外部库 opt-in
        self.tiers: Dict[str, MemoryTier] = {
            TIER_INSTANT: instant or self._default_instant(),
            TIER_WORKING: working or InMemoryTier(),
            TIER_LONGTERM: longterm or InMemoryTier(),
            TIER_HERITAGE: heritage or InMemoryTier(),
        }
        self.promoted: Dict[str, str] = {}  # key -> 当前所在层

    @staticmethod
    def _default_instant() -> MemoryTier:
        try:
            return DuckDBTier()
        except ImportError:
            return InMemoryTier()

    def store(self, tier: str, key: str, value: Any, **meta: Any) -> None:
        if tier not in self.tiers:
            raise KeyError(f"未知记忆层: {tier}")
        self.tiers[tier].store(key, value, **meta)
        self.promoted[key] = tier

    def recall(self, tier: str, key: str) -> Optional[Any]:
        return self.tiers[tier].recall(key)

    def promote(self, key: str, to_tier: str) -> bool:
        """把一条记忆从当前层晋升到更高层（数据从瞬时→永久自然流动）。

        仅在目标层序号 >= 当前层时允许（不允许降序误用）。返回是否成功。
        """
        if key not in self.promoted:
            return False
        from_idx = TIER_ORDER.index(self.promoted[key])
        to_idx = TIER_ORDER.index(to_tier)
        if to_idx < from_idx:
            return False
        value = self.recall(self.promoted[key], key)
        if value is None:
            return False
        self.tiers[to_tier].store(key, value)
        self.promoted[key] = to_tier
        return True

    def stats(self) -> Dict[str, Any]:
        return {name: tier.stats() for name, tier in self.tiers.items()}


def build_default_ladder() -> MemoryLadder:
    """构造默认阶梯：L1 用 DuckDB（可用时），其余内存兜底；外部库经 opt-in 适配器接入。"""
    ladder = MemoryLadder()
    # L2 可选接 TriviumDB / Turso（未安装则 LazyExternalTier 在调用时诚实报错）
    ladder.tiers[TIER_WORKING] = LazyExternalTier("triviumdb", _trivium_connect)
    return ladder
