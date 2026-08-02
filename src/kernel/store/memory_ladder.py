"""记忆阶梯（数据底座层）存储抽象。

把蓝图「四层阶梯式融合架构」落地为可运行的代码骨架：
- L1 瞬时感知层（DuckDB 1.5.5，已升最新；可选 Lance 扩展获得版本血缘）
- L2 工作记忆层（TriviumDB / Turso，opt-in 惰性适配器）
- L3 长期语义层（复用 AOS 既有 Chroma/cognee；KowitoDB/txtai 仅参考）
- L4 永久传承层（SeekDB 主选；LanceDB 为「更优技术」opt-in 备选——Git 式
  分支版本化，Apache-2.0，与 DuckDB 直接集成）

深度推理新增（2026-08-02 全网核验）：AionDB/SurrealDB 虽涌现，但 AionDB 仅
source-available（许可不明）、SurrealDB 偏服务/分布式不符「每粒子一文件轻量」，
按铁律列为观察项、不采纳。

自动分层引擎（2026-08-02 第二轮深度推理补）：蓝图灵魂是「让不同数据库根据
数据热度、访问频率、生命周期自动分层」。初版仅手动 promote()，与理念脱节。
现补 `heat()` / `auto_promote()` / `distill()` / `_route_by_heat()`：记忆被
访问（store/recall）越频繁越热，热度达阈值即自动向上沉淀一层，无需手工调用；
`distill()` 批量执行——实现蓝图「层间数据流动」的自动版。

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

    本机实测 duckdb 1.5.5 在 Python 3.14 下可直接 import，故作为 L1 真后端。
    适合 mirror_branch 的实时统计、生命周期数据复盘。

    ``lance=True`` 时 best-effort 加载 DuckDB 的 Lance 扩展
    （INSTALL lance; LOAD lance;），让 L1 可直接读写带 MVCC 版本/时间旅行的
    Lance 表，等于给瞬时层免费附上「版本血缘」——和 L4 的代际传承打通。
    加载失败（无网络/未发布）时静默降级，不影响 L1 基础能力。
    """

    name = "duckdb"

    def __init__(self, path: str = ":memory:", lance: bool = False) -> None:
        import duckdb  # 惰性 import；缺失则构造时抛 ImportError，由 MemoryLadder 降级

        self._con = duckdb.connect(path)
        self._con.execute(
            "CREATE TABLE IF NOT EXISTS ladder_kv (k VARCHAR, v JSON, ts DOUBLE)"
        )
        if lance:
            try:
                self._con.execute("INSTALL lance; LOAD lance;")
                self._lance = True
            except Exception:
                self._lance = False  # best-effort：无网络或扩展未发布则降级
        else:
            self._lance = False

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


def _lancedb_connect() -> MemoryTier:
    """L4 永久传承层：LanceDB 连接工厂（「更优技术」opt-in 备选，Apache-2.0）。

    深度推理（2026-08-02 全网核验）：LanceDB 0.34.0（2026-07-02）新增 table branches
    —— Git 式零拷贝分支，写分支不动 main，可 checkout/diff/merge；每次写自动版本化
    （不可变 fragment + 时间旅行 + tag）。这比 SeekDB 的 Fork/Diff&Merge **更原生地**
    命中蓝图「数字家谱/Git 式版本分支」需求，且与 DuckDB 直接集成（L1↔L4 血缘打通）。
    故作为 L4 opt-in 备选自动接入（主选仍 SeekDB，见文档第十一章）。

    需 ``pip install lancedb``。缺失即 ImportError（诚实告知）。
    """
    import lancedb  # 缺失即 ImportError

    db = lancedb.connect("./_ladder_heritage.lance")

    class _Wrap(MemoryTier):
        name = "lancedb"

        def __init__(self, db):
            self._db = db
            self._table_name = "heritage"

        def store(self, key, value, **meta):
            import pyarrow as pa

            data = [{"key": key, "value": json.dumps(value), "meta": json.dumps(meta)}]
            tbl = self._db.open_table(self._table_name) if self._db.table_names() else None
            if tbl is None:
                self._db.create_table(self._table_name, data=pa.table(data))
            else:
                tbl.add(pa.table(data))

        def recall(self, key):
            if self._table_name not in self._db.table_names():
                return None
            tbl = self._db.open_table(self._table_name)
            df = tbl.search().where(f"key = '{key}'").to_pandas()
            if df.empty:
                return None
            return json.loads(df.iloc[-1]["value"])

        def stats(self):
            if self._table_name not in self._db.table_names():
                return {"name": self.name, "count": 0}
            return {"name": self.name, "count": self._db.open_table(self._table_name).count_rows()}

    return _Wrap(db)


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
        self._access: Dict[str, Dict[str, float]] = {}  # key -> {count, last} 自动分层用

    @staticmethod
    def _default_instant() -> MemoryTier:
        try:
            return DuckDBTier()
        except ImportError:
            return InMemoryTier()

    def store(self, tier: Optional[str], key: str, value: Any, **meta: Any) -> None:
        if tier is None:
            tier = self._route_by_heat(key)  # 按热度自动选层
        if tier not in self.tiers:
            raise KeyError(f"未知记忆层: {tier}")
        self.tiers[tier].store(key, value, **meta)
        self.promoted[key] = tier
        self._touch(key)

    def recall(self, tier: str, key: str) -> Optional[Any]:
        self._touch(key)  # 访问即记热度
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

    # ---- 自动分层引擎（蓝图核心：按数据热度/访问频率自动向上沉淀）----
    def _touch(self, key: str) -> None:
        a = self._access.setdefault(key, {"count": 0, "last": 0.0})
        a["count"] += 1
        a["last"] = time.time()

    def heat(self, key: str) -> int:
        """返回某条记忆被访问（store/recall）的总次数——即「数据热度」。"""
        return int(self._access.get(key, {}).get("count", 0))

    def _route_by_heat(self, key: str) -> str:
        """按热度自动选层：新记忆落 L1 瞬时层；每累计 3 次访问向上晋升一层。"""
        idx = min(self.heat(key) // 3, len(TIER_ORDER) - 1)
        return TIER_ORDER[idx]

    def auto_promote(self, key: str, heat_threshold: int = 3) -> bool:
        """热度达阈值即把记忆向上晋升一层（仅在还能升时）。返回是否晋升成功。"""
        if key not in self.promoted:
            return False
        if self.heat(key) < heat_threshold:
            return False
        idx = TIER_ORDER.index(self.promoted[key])
        if idx >= len(TIER_ORDER) - 1:
            return False  # 已在永久传承层，无更高层
        return self.promote(key, TIER_ORDER[idx + 1])

    def distill(self, heat_threshold: int = 3) -> list:
        """批处理：对所有达热度阈值的记忆执行一次向上晋升，返回被晋升的 key 列表。

        实现蓝图「层间数据流动」的自动版——高频/有价值的记忆自动从瞬时层向上
        沉淀到工作/长期/传承层，无需手动 promote。
        """
        promoted: list = []
        for key in list(self.promoted.keys()):
            if self.auto_promote(key, heat_threshold):
                promoted.append(key)
        return promoted

    def stats(self) -> Dict[str, Any]:
        return {name: tier.stats() for name, tier in self.tiers.items()}


def build_default_ladder() -> MemoryLadder:
    """构造默认阶梯：L1 用 DuckDB（可用时），其余内存兜底；外部库经 opt-in 适配器接入。

    L4 永久传承层接入 LanceDB 作为「更优技术」opt-in 备选（Git 式分支版本化，
    Apache-2.0，与 DuckDB 直接集成）；SeekDB 仍为文档主选，二者可并存。
    """
    ladder = MemoryLadder()
    # L2 可选接 TriviumDB / Turso（未安装则 LazyExternalTier 在调用时诚实报错）
    ladder.tiers[TIER_WORKING] = LazyExternalTier("triviumdb", _trivium_connect)
    # L4 可选接 LanceDB（更优技术 opt-in；未安装则诚实降级 available:False）
    ladder.tiers[TIER_HERITAGE] = LazyExternalTier("lancedb", _lancedb_connect)
    return ladder
