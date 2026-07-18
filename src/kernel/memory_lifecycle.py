"""记忆生命周期管理器（理念2「失败即训练数据」的"遗忘/再生"半边）。

农耕层循环智慧：记忆不是只进不出，而是有生有灭、腐烂成肥、循环再生。
此前 AOS 的提炼记忆只 append 进 distilled_memory.jsonl（见 memory_distiller.py），
缺一个"有 TTL、有热度、有分层降级"的遗忘机制——这就是概念2 确认缺失的那一半。

本模块为白盒记忆根基叠加一层**生命周期侧车**（distilled_lifecycle.json），
实现（对齐理念2/6/9）：
- TTL 过期：普通/重要记忆超过存活期未访问即触发降级
- 访问热度：被 recall 命中的记忆累积 access_count + 刷新 last_accessed，
  高热度可延缓降级（活土肥力）
- 分层降级：eternal(永生) / important(重要) / normal(普通) / archived(归档软删)
- 偏好记忆区分：memory_type=preference 走永生层，长期资产不退化
- 量化报告：各 tier 计数、过期数、归档数（对齐理念6 诚实+量化 / 理念9 可验证）

设计约束（与 MemoryDistiller 同风格）：
- 纯标准库、不引重型依赖（避免冷启动负担）
- best-effort、加锁、零阻塞：任何异常被吞并记日志，绝不拖垮主进程
- 单一数据源：记忆正文仍在 distilled_memory.jsonl，本类只持侧车元数据
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---- tier 常量 ----
TIER_ETERNAL = "eternal"      # 永生：偏好/核心事实，永不删不降
TIER_IMPORTANT = "important"  # 重要：能力可靠性等长期资产，长 TTL
TIER_NORMAL = "normal"        # 普通：默认，中 TTL，超期降级归档
TIER_ARCHIVED = "archived"    # 归档：软删冷存，不物理删除（数据保全）
TIERS = (TIER_ETERNAL, TIER_IMPORTANT, TIER_NORMAL, TIER_ARCHIVED)

# 默认 TTL（秒）——概念2 的"记忆有生有灭"的时间尺度
DEFAULT_TTL: Dict[str, Optional[float]] = {
    TIER_ETERNAL: None,            # 永生
    TIER_IMPORTANT: 30 * 86400,    # 30 天
    TIER_NORMAL: 7 * 86400,        # 7 天
    TIER_ARCHIVED: 90 * 86400,     # 归档后冷存 90 天（仍不物理删）
}

# category -> (memory_type, 初始 tier)
_CATEGORY_MAP = {
    "failure_pattern": ("failure", TIER_NORMAL),
    "capability_reliability": ("fact", TIER_IMPORTANT),
    "latency_fact": ("fact", TIER_NORMAL),
}


@dataclass
class LifecycleMeta:
    id: str
    tier: str = TIER_NORMAL
    memory_type: str = "fact"
    created_ts: float = 0.0
    last_accessed_ts: float = 0.0
    access_count: int = 0
    ttl_seconds: Optional[float] = None
    archived: bool = False
    promoted: bool = False  # 是否因热度升过级（用于 report 量化）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LifecycleMeta":
        return cls(**{k: v for k, v in d.items() if k in _META_FIELDS})


_META_FIELDS = set(LifecycleMeta.__dataclass_fields__.keys())


@dataclass
class PruneReport:
    scanned: int = 0
    expired: int = 0
    demoted: int = 0     # important -> normal
    archived: int = 0    # normal -> archived
    promoted: int = 0    # 因热度升级（预留）
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now() -> float:
    return time.time()


def _id_of(it: Any) -> Optional[str]:
    if isinstance(it, dict):
        return it.get("id")
    return getattr(it, "id", None)


def _cat_of(it: Any) -> Optional[str]:
    if isinstance(it, dict):
        return it.get("category")
    return getattr(it, "category", None)


def _conf_of(it: Any) -> float:
    if isinstance(it, dict):
        v = it.get("confidence", 0) or 0
    else:
        v = getattr(it, "confidence", 0) or 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class MemoryLifecycleManager:
    """农耕层循环记忆：为白盒记忆根基（distilled_memory.jsonl）管理生命周期侧车。"""

    def __init__(self, lifecycle_path: str,
                 now_provider: Callable[[], float] = _now):
        self.path = lifecycle_path
        self._now = now_provider
        self._meta: Dict[str, LifecycleMeta] = self._load()
        self._lock = threading.Lock()
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        except OSError as e:  # noqa: BLE001
            logger.warning("lifecycle dir create failed: %s", e)

    # ---- 持久化 ----
    def _load(self) -> Dict[str, LifecycleMeta]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {k: LifecycleMeta.from_dict(v) for k, v in raw.items()}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._meta.items()},
                          f, ensure_ascii=False)
        except OSError as e:  # noqa: BLE001
            logger.warning("lifecycle save failed: %s", e)

    # ---- 注册（写入时打标签）----
    def register(self, items: List[Any]) -> int:
        """为新提炼的记忆登记生命周期元数据。items 为带 .id/.category 的对象
        （DistilledMemory 或 dict）。返回新登记数。已登记的跳过（幂等）。"""
        now = self._now()
        new = 0
        with self._lock:
            for it in items:
                mid = _id_of(it)
                if not mid or mid in self._meta:
                    continue
                cat = _cat_of(it) or "fact"
                mtype, tier = _CATEGORY_MAP.get(cat, ("fact", TIER_NORMAL))
                self._meta[mid] = LifecycleMeta(
                    id=mid, tier=tier, memory_type=mtype,
                    created_ts=now, last_accessed_ts=now,
                    ttl_seconds=DEFAULT_TTL.get(tier))
                new += 1
            if new:
                self._save()
        return new

    # ---- 召回（取用即升温）----
    def recall(self, items: List[Any],
               filter_fn: Optional[Callable[[Any], bool]] = None,
               limit: int = 20) -> List[Any]:
        """从存活（未归档）记忆中按 热度*置信 排序召回。命中即升温。
        items 是完整记忆列表（由调用方从 jsonl 载入；本类不持有记忆正文，
        只持侧车元数据，保持单一数据源）。"""
        now = self._now()
        alive: List[Any] = []
        with self._lock:
            for it in items:
                mid = _id_of(it)
                meta = self._meta.get(mid) if mid else None
                if meta is None or meta.archived:
                    continue
                if filter_fn and not filter_fn(it):
                    continue
                meta.access_count += 1
                meta.last_accessed_ts = now
                alive.append((it, meta))
            if alive:
                self._save()
        # 排序：热度分 = access_count * (0.5 + confidence)
        alive.sort(key=lambda p: p[1].access_count * (0.5 + _conf_of(p[0])),
                   reverse=True)
        return [p[0] for p in alive[:limit]]

    # ---- 周期 prune（TTL 过期 + 分层降级）----
    def prune(self, now: Optional[float] = None) -> PruneReport:
        now = now if now is not None else self._now()
        rep = PruneReport()
        with self._lock:
            for mid, meta in self._meta.items():
                rep.scanned += 1
                try:
                    if meta.tier == TIER_ETERNAL:
                        continue  # 永生不删不降
                    if meta.tier == TIER_ARCHIVED:
                        continue  # 归档冷存，不物理删（数据保全铁律）
                    ttl = meta.ttl_seconds
                    if ttl is None:
                        continue
                    age = now - meta.last_accessed_ts
                    # 高热度延缓降级：访问越多，等效寿命越长（活土肥力）
                    effective_ttl = ttl * (1 + min(meta.access_count, 10) * 0.2)
                    if age <= effective_ttl:
                        continue
                    rep.expired += 1
                    if meta.tier == TIER_IMPORTANT:
                        meta.tier = TIER_NORMAL
                        meta.ttl_seconds = DEFAULT_TTL[TIER_NORMAL]
                        rep.demoted += 1
                    elif meta.tier == TIER_NORMAL:
                        meta.tier = TIER_ARCHIVED
                        meta.archived = True
                        meta.ttl_seconds = DEFAULT_TTL[TIER_ARCHIVED]
                        rep.archived += 1
                except Exception as e:  # noqa: BLE001
                    rep.errors.append(f"{mid}: {e}")
            if rep.expired:
                self._save()
        return rep

    # ---- 显式标注偏好（API/用户干预用）----
    def mark_preference(self, mid: str) -> bool:
        with self._lock:
            meta = self._meta.get(mid)
            if not meta:
                return False
            meta.memory_type = "preference"
            meta.tier = TIER_ETERNAL
            meta.ttl_seconds = None
            meta.archived = False
            self._save()
        return True

    # ---- 量化报告（理念6 诚实+量化 / 理念9 可验证）----
    def report(self) -> Dict[str, Any]:
        counts = {t: 0 for t in TIERS}
        archived = promoted = 0
        for meta in self._meta.values():
            counts[meta.tier] = counts.get(meta.tier, 0) + 1
            if meta.archived:
                archived += 1
            if meta.promoted:
                promoted += 1
        return {
            "total": len(self._meta),
            "by_tier": counts,
            "archived": archived,
            "ever_promoted": promoted,
        }
