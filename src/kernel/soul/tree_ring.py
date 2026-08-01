"""L3 年轮时空记忆 + 时空环境记忆库 —— 完全自研核心（生命体OS 白皮书 L3A/L3B）。

隐喻不是装饰，是压缩策略：树的年轮**越靠外越细节、越靠内越轮廓**，
但每一圈都还在，砍开就能读出这棵树活过的年头。

四圈（band）：
    ring0 FRESH    ≤1 天    原文全量
    ring1 RECENT   ≤7 天    摘要（保留关键实体与结论）
    ring2 SEASON   ≤90 天   要点（只留结论 + 标签）
    ring3 CORE     >90 天   轮廓（一句话 + 计数聚合）

「时空环境记忆库」= 每条记忆带 **when（时间）+ where（locus 场景/环境）**，
支持按时空切片召回：「上个月在做单创OS 定价那阵子我踩过什么坑」。

与既有 AOS 模块的分工（复用不重造）：
- `kernel/memory_lifecycle.MemoryLifecycleManager` 管 TTL/热度/prune —— 可用 `attach_lifecycle()` 挂进来；
- `kernel/memory_distiller.MemoryDistiller` 管从 trace 蒸馏 —— 产物可直接 `remember()` 进本库；
- 本模块只负责别处没有的两件事：**年轮分层压缩** 与 **时空切片索引**。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

DAY = 86400.0

RING_FRESH, RING_RECENT, RING_SEASON, RING_CORE = 0, 1, 2, 3
RING_NAMES = {RING_FRESH: "fresh", RING_RECENT: "recent",
              RING_SEASON: "season", RING_CORE: "core"}
# 年轮边界（秒）：超过该年龄即晋升到下一圈
RING_BOUNDS: Tuple[float, float, float] = (1 * DAY, 7 * DAY, 90 * DAY)

# 各圈保留字符上限（越内圈越短，实现"越久远越轮廓"）
RING_BUDGET = {RING_FRESH: 0, RING_RECENT: 400, RING_SEASON: 160, RING_CORE: 60}


def _summarize(text: str, budget: int) -> str:
    """无依赖的确定性摘要：按句取前部 + 尾部结论，超预算截断并标记。

    刻意不调 LLM：记忆压缩必须离线可跑、可复现、零成本（宪法理念 4）。
    需要更强摘要时由调用方传 summarizer 注入。
    """
    t = " ".join((text or "").split())
    if budget <= 0 or len(t) <= budget:
        return t
    head = t[: max(0, budget - 20)]
    tail = t[-15:]
    return f"{head}…{tail}"


@dataclass
class Memory:
    mid: str
    text: str
    when: float = field(default_factory=time.time)
    locus: str = "unknown"                 # 时空环境标签：项目/场景/地点
    tags: List[str] = field(default_factory=list)
    ring: int = RING_FRESH
    hits: int = 0                          # 召回次数（热度，供 lifecycle 消费）
    original_len: int = 0

    def age(self, now: Optional[float] = None) -> float:
        return max(0.0, ((time.time() if now is None else now)) - self.when)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ring_name"] = RING_NAMES[self.ring]
        return d


class TreeRingMemory:
    """年轮时空记忆库。"""

    def __init__(self, summarizer: Optional[Callable[[str, int], str]] = None):
        self._items: Dict[str, Memory] = {}
        self._by_locus: Dict[str, List[str]] = {}
        self._summarize = summarizer or _summarize
        self._lifecycle = None            # 可选：MemoryLifecycleManager
        self._seq = 0

    # ---------------------------------------------------------------- 写入
    def remember(self, text: str, *, locus: str = "unknown",
                 tags: Optional[Iterable[str]] = None,
                 when: Optional[float] = None, mid: Optional[str] = None) -> Memory:
        self._seq += 1
        mid = mid or f"m{self._seq:06d}"
        m = Memory(mid=mid, text=(text or "").strip(), when=(time.time() if when is None else when),
                   locus=locus, tags=list(tags or []),
                   original_len=len((text or "").strip()))
        self._items[mid] = m
        self._by_locus.setdefault(locus, []).append(mid)
        return m

    # ---------------------------------------------------------------- 年轮
    @staticmethod
    def ring_for_age(age: float) -> int:
        if age <= RING_BOUNDS[0]:
            return RING_FRESH
        if age <= RING_BOUNDS[1]:
            return RING_RECENT
        if age <= RING_BOUNDS[2]:
            return RING_SEASON
        return RING_CORE

    def grow_rings(self, now: Optional[float] = None) -> Dict[str, int]:
        """推进年轮：按年龄晋升并逐层压缩。返回各圈计数。

        高热度记忆（hits ≥ 5）延缓一圈晋升——常被想起的事记得更细，符合真实记忆规律。
        """
        now = (time.time() if now is None else now)
        for m in self._items.values():
            target = self.ring_for_age(m.age(now))
            if m.hits >= 5:
                target = max(RING_FRESH, target - 1)
            while m.ring < target:
                m.ring += 1
                budget = RING_BUDGET[m.ring]
                if budget:
                    m.text = self._summarize(m.text, budget)
        return self.census()

    def census(self) -> Dict[str, int]:
        out = {name: 0 for name in RING_NAMES.values()}
        for m in self._items.values():
            out[RING_NAMES[m.ring]] += 1
        return out

    def compression_ratio(self) -> float:
        """真实压缩率：当前总字符 / 原始总字符（越小压得越狠）。"""
        orig = sum(m.original_len for m in self._items.values())
        now = sum(len(m.text) for m in self._items.values())
        return 1.0 if orig == 0 else round(now / orig, 4)

    # ---------------------------------------------------------------- 召回
    def recall(self, query: str = "", *, locus: Optional[str] = None,
               since: Optional[float] = None, until: Optional[float] = None,
               tags: Optional[Iterable[str]] = None, limit: int = 10) -> List[Memory]:
        """时空切片召回：可按 关键词 / 场景 / 时间窗 / 标签 任意组合。"""
        want_tags = set(tags or [])
        q = (query or "").lower().strip()
        out: List[Memory] = []
        pool = (self._items[i] for i in self._by_locus.get(locus, [])) if locus \
            else self._items.values()
        for m in pool:
            if since is not None and m.when < since:
                continue
            if until is not None and m.when > until:
                continue
            if want_tags and not want_tags.issubset(set(m.tags)):
                continue
            if q and q not in m.text.lower() and not any(q in t.lower() for t in m.tags):
                continue
            out.append(m)
        # 排序：新的优先，同期热度高优先
        out.sort(key=lambda m: (m.when, m.hits), reverse=True)
        for m in out[:limit]:
            m.hits += 1
        return out[:limit]

    def timeline(self, locus: Optional[str] = None) -> List[Tuple[float, str]]:
        """时空环境记忆库的骨架视图：(时间, 一句话) 序列。"""
        pool = (self._items[i] for i in self._by_locus.get(locus, [])) if locus \
            else self._items.values()
        return sorted(((m.when, _summarize(m.text, 60)) for m in pool), key=lambda x: x[0])

    def loci(self) -> List[str]:
        return sorted(self._by_locus)

    # ---------------------------------------------------------------- 集成
    def attach_lifecycle(self, manager: Any) -> None:
        """挂接已有 MemoryLifecycleManager（复用其 TTL/prune，不在此重造）。"""
        self._lifecycle = manager
        if hasattr(manager, "register"):
            manager.register(list(self._items.values()))

    def forget(self, mid: str) -> bool:
        m = self._items.pop(mid, None)
        if not m:
            return False
        lst = self._by_locus.get(m.locus, [])
        if mid in lst:
            lst.remove(mid)
        return True

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([m.to_dict() for m in self._items.values()],
                                ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def load(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        for d in json.loads(p.read_text(encoding="utf-8")):
            d.pop("ring_name", None)
            m = Memory(**d)
            self._items[m.mid] = m
            self._by_locus.setdefault(m.locus, []).append(m.mid)
        return len(self._items)

    def __len__(self) -> int:
        return len(self._items)


__all__ = ["TreeRingMemory", "Memory", "RING_FRESH", "RING_RECENT", "RING_SEASON",
           "RING_CORE", "RING_NAMES", "RING_BOUNDS", "RING_BUDGET"]
