"""记忆阶梯（数据底座层）存储抽象。

把蓝图「四层阶梯式融合架构」落地为可运行的代码骨架：
- L1 瞬时感知层（DuckDB 1.5.5，已升最新；可选 Lance 扩展获得版本血缘）
- L2 工作记忆层（TriviumDB / Turso，opt-in 惰性适配器，**诚实降级**）
- L3 长期语义层（复用 AOS 既有 Chroma/cognee/mem0 —— 这些本就是开源，非自研）
- L4 永久传承层（**LanceDB 已真接入并可跑 Git 式表分支**；SeekDB 为服务端参考项）

诚实纪律（2026-08-02 收口）：
- 凡能装的 MIT/Apache 开源 **真接入、真跑通**（DuckDB 已装；LanceDB 0.36.0 已装、store/recall/branch 实测通过）。
- 接不上的（TriviumDB=Rust crate 无 PyPI 轮子；Turso=libsql 仅支持 Py<3.13）：
  **import 即 ImportError，由 LazyExternalTier 诚实降级为 available:False，绝不退回内存实现冒充**。
- SeekDB 是 OceanBase 服务端产品，本地优先 OS 偏重，列为参考项不强制接入。
- 所有外部依赖惰性 import，缺失即优雅降级到内存实现，保证 ② 单元可测；
  外部库的运行时真连仅留适配器骨架，未做 ③ 端到端验证（真灌多模态数据全链路）。
"""

from __future__ import annotations

import json
import os
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

    本机实测 duckdb 1.5.5 在 Python 3.13/3.14 下可直接 import，故作为 L1 真后端。
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
    ImportError（清晰告知需 pip install / 构建绑定），**绝不退回内存实现冒充**。
    不强制任何重型依赖，符合选型铁律。
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
        except ImportError as exc:  # 未安装：诚实告知（含真实约束原因）
            return {
                "name": self.name,
                "backend": self.backend,
                "available": False,
                "reason": str(exc),
            }


def _trivium_connect() -> MemoryTier:
    """TriviumDB 连接工厂（L2 工作记忆）。

    诚实说明：TriviumDB 是 **Rust crate**（github.com/YoKONCy/TriviumDB），
    PyPI 上**没有** ``triviumdb`` 轮子，需从源码/Cargo 构建 pyo3 绑定，或降到
    Python <3.13。本托管环境是 Python 3.13.12，故 ``import triviumdb`` 会
    ImportError——这是真实约束，不是代码 bug。由 LazyExternalTier 诚实降级为
    available:False。一旦环境具备该绑定，请在此实现真实 _Wrap（按 key 存/取）。
    """
    import triviumdb  # 缺失（Py3.13 / 未构建）即 ImportError → 上层诚实降级

    # 环境具备绑定时才执行到此处；其真实 API 未在本环境验证，故显式要求实现。
    raise RuntimeError(
        "TriviumDB Python 绑定已 import 成功，但其真实 API 未经本环境验证；"
        "请在具备该绑定的环境中实现按 key 存/取的 _Wrap 后再启用。"
    )


def _turso_connect() -> MemoryTier:
    """Turso/libSQL 连接工厂（L2 工作记忆，每粒子一库）。

    诚实说明：Turso 的 Python 绑定 ``libsql`` 在 PyPI 仅支持 Python <3.13；
    本托管环境是 3.13.12，``import libsql`` 会 ImportError。这是真实环境约束，
    不是 bug。若环境降到 <3.13 或构建了绑定，则真正连接 libSQL 文件库。
    **绝不退回内存实现冒充 Turso**（旧代码曾这样骗，已修）。
    """
    import libsql  # <3.13 才可用；此处 ImportError → 上层诚实降级

    con = libsql.connect("file:particle.tdb")  # 真实 libSQL 文件库连接

    class _Wrap(MemoryTier):
        name = "turso"

        def store(self, key: str, value: Any, **meta: Any) -> None:
            con.execute(
                "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, ts DOUBLE)"
            )
            con.execute(
                "INSERT OR REPLACE INTO kv VALUES (?, ?, ?)",
                [key, json.dumps({"value": value, "meta": meta}), time.time()],
            )

        def recall(self, key: str) -> Optional[Any]:
            row = con.execute("SELECT v FROM kv WHERE k=?", [key]).fetchone()
            return json.loads(row[0])["value"] if row else None

        def stats(self) -> Dict[str, Any]:
            n = con.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
            return {"name": self.name, "count": n}

    return _Wrap()


def _seekdb_connect() -> MemoryTier:
    """SeekDB 连接工厂（L4 永久传承层，OceanBase 开源产品）。

    诚实说明：SeekDB 是 **服务端产品**（OceanBase 源分发，非纯 pip 库），对
    本地优先 OS 偏重。本环境未安装即 ImportError → 诚实降级。其 Fork Database
    + Diff&Merge 能力是「数字家谱」的强参考；本地优先场景由 LanceDB 表分支承担。
    """
    import seekdb  # 未安装（服务端产品）即 ImportError → 上层诚实降级

    raise RuntimeError(
        "SeekDB 为 OceanBase 服务端产品，本环境未安装；请部署服务端后在具备依赖的"
        "环境中实现真实 _Wrap（Fork Database / Diff&Merge）再启用。"
    )


def _lancedb_connect() -> MemoryTier:
    """L4 永久传承层：LanceDB 连接工厂（**已真接入、可跑 Git 式表分支**）。

    深度推理（2026-08-02 全网核验）：LanceDB 0.34.0+ 的 **table branches**
    —— Git 式零拷贝分支（写分支不动 main，可 checkout/merge）、每次写自动版本化
    （不可变 fragment + 时间旅行 + tag）。比 SeekDB 的 Fork/Diff&Merge **更原生地**
    命中蓝图「数字家谱 / Git 式版本分支」需求，且与 DuckDB 直接集成（L1↔L4 血缘打通）。
    Apache-2.0，~11k★，且本环境 Python 3.13 可装（实测 0.36.0）。

    路径可通过环境变量 ``AOS_LANCE_HERITAGE_PATH`` 覆盖（测试指向临时目录），
    默认 ``./_ladder_heritage.lance``。

    分支 API 在 **表对象** 上（``tbl.branches()`` / ``tbl.checkout()`` /
    ``tbl.current_branch()`` / ``tbl.merge()`` / ``tbl.version``），非 DB 对象。
    """
    import lancedb  # 缺失即 ImportError（诚实降级）

    path = os.environ.get("AOS_LANCE_HERITAGE_PATH", "./_ladder_heritage.lance")
    db = lancedb.connect(path)
    TABLE = "heritage"

    class _Wrap(MemoryTier):
        name = "lancedb"

        def _tbl(self):
            res = db.list_tables() if hasattr(db, "list_tables") else db.table_names()
            # lancedb 0.36: list_tables() 返回分页结果对象（含 .tables 列表），
            # 旧 table_names() 直接返回 list；两者都兼容。
            if not isinstance(res, (list, tuple, set)):
                res = getattr(res, "tables", []) or []
            if TABLE in res:
                return db.open_table(TABLE)
            return None

        def store(self, key: str, value: Any, **meta: Any) -> None:
            data = [{"key": key, "value": json.dumps(value), "meta": json.dumps(meta)}]
            tbl = self._tbl()
            if tbl is None:
                db.create_table(TABLE, data=data)
            else:
                tbl.add(data)

        def recall(self, key: str) -> Optional[Any]:
            tbl = self._tbl()
            if tbl is None:
                return None
            rows = tbl.search().where(f"key = '{key}'").to_list()
            if not rows:
                return None
            return json.loads(rows[-1]["value"])

        def stats(self) -> Dict[str, Any]:
            tbl = self._tbl()
            if tbl is None:
                return {"name": self.name, "count": 0, "branch": "main", "version": 0}
            return {
                "name": self.name,
                "count": tbl.count_rows(),
                "branch": tbl.current_branch(),
                "version": tbl.version,
            }

        # ---- 数字家谱：Git 式表分支（更优技术落地，LanceDB 0.36 实测）----
        # 分支 API 在 **表对象的 branches 管理器** 上：create/checkout/diff/list/version。
        # 诚实边界：本地模式 **merge 仅支持 remote 表**（NotImplementedError），故本地
        # 「数字家谱」= 分支隔离 + 不可变版本历史 + 时间旅行；跨分支合并需 LanceDB Cloud。
        def branches(self) -> list:
            tbl = self._tbl()
            if tbl is None:
                return ["main"]
            try:
                return list(tbl.branches.list().keys())
            except Exception:
                return ["main"]

        def create_branch(self, name: str) -> None:
            tbl = self._tbl()
            if tbl:
                tbl.branches.create(name)

        def current_branch(self) -> str:
            tbl = self._tbl()
            return tbl.current_branch() if tbl else "main"

        def checkout(self, branch: str) -> None:
            tbl = self._tbl()
            if tbl:
                tbl.branches.checkout(branch)

        def merge(self, branch: str) -> None:
            # 仅 LanceDB Cloud remote 表支持；本地模式会抛 NotImplementedError。
            tbl = self._tbl()
            if tbl:
                tbl.branches.merge(branch)

    return _Wrap()


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

    - L2 工作记忆：接 TriviumDB opt-in（未构建/Py3.13 则诚实降级 available:False，
      绝不退回内存冒充）。
    - L4 永久传承：接 **LanceDB opt-in（已装即真用，Git 式表分支可跑）**；SeekDB 为
      服务端参考项，不强制接入。
    """
    ladder = MemoryLadder()
    # L2 可选接 TriviumDB（Rust crate / Py<3.13；本环境诚实降级）
    ladder.tiers[TIER_WORKING] = LazyExternalTier("triviumdb", _trivium_connect)
    # L4 接 LanceDB（已装 0.36.0，store/recall/branch 实测通过）
    ladder.tiers[TIER_HERITAGE] = LazyExternalTier("lancedb", _lancedb_connect)
    return ladder
