"""L3 记忆生命周期管理引擎（自研，对应白皮书 11.10 之 IEEE 论文转化项）。

外部声称：IEEE 2026-02「四层记忆 + CIAR」论文。
核验结论：❌ 出处伪造（实为 mas-memory-layer 项目的 ADR-004 设计记录）。
保留能力：认知科学四层记忆（感官/工作/情景/语义）+ 生命周期流动引擎（CIAR：
Collect 收集 / Index 索引 / Activate 激活 / Retrieve 检索 的流动）。
自研落地：本模块实现记忆「重要性评分晋升 → 蒸馏压缩 → 遗忘衰减 → 用户锚定」
四阶段生命周期，独立可测，不依赖任何未证实外部论文。

诚实分级：②（代码 + 单测可跑）；未做 ③（接真 LLM 蒸馏 / 大规模端到端验证）。
本模块与 memory_ladder.py（四层阶梯存储）互补：ladder 管「存在哪一层」，
lifecycle 管「在层间如何流动与消亡」。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def importance_score(record: Dict[str, Any], now: Optional[float] = None) -> float:
    """重要性评分（纯函数，可单测）。

    综合：被访问次数（recall_count）、最近访问时间（新鲜度衰减）、是否用户锚定
    （user_anchored）、显式标注权重（weight）。范围 [0, 1]。
    """
    now = now if now is not None else time.monotonic()
    recalls = float(record.get("recall_count", 0) or 0)
    last = float(record.get("last_access", now) or now)
    weight = float(record.get("weight", 0.5) or 0.5)
    anchored = 1.0 if record.get("user_anchored") else 0.0
    # 新鲜度：越近越高，半衰期 86400s（1 天）
    freshness = 0.5 ** ((now - last) / 86400.0)
    raw = 0.4 * min(1.0, recalls / 10.0) + 0.3 * freshness + 0.2 * weight + 0.1 * anchored
    return round(min(1.0, max(0.0, raw)), 4)


def promote(record: Dict[str, Any], now: Optional[float] = None) -> Optional[str]:
    """晋升判定：重要性超阈值则向上一层（阈值 0.7）。返回新层名或 None。"""
    score = importance_score(record, now)
    ladder = ["L1_sensory", "L2_working", "L3_episodic", "L4_semantic"]
    cur = record.get("layer", "L1_sensory")
    if cur not in ladder:
        return None
    idx = ladder.index(cur)
    if score >= 0.7 and idx < len(ladder) - 1:
        new_layer = ladder[idx + 1]
        record["layer"] = new_layer
        return new_layer
    return None


def distill(record: Dict[str, Any]) -> Dict[str, Any]:
    """蒸馏压缩：把长内容摘要为要点，保留维度标记，缩短 payload。"""
    content = record.get("content", "")
    if not content:
        return record
    # 骨架蒸馏：取前 3 句（按句号切），真实蒸馏由 LLM 接入
    sentences = [s for s in content.replace("\n", "。").split("。") if s.strip()]
    summary = "。".join(sentences[:3])
    if len(sentences) > 3:
        summary += "。（…已蒸馏）"
    record["content"] = summary
    record["distilled"] = True
    return record


def forget(record: Dict[str, Any], now: Optional[float] = None, decay_half_life: float = 30.0) -> bool:
    """遗忘衰减：未被锚定且长期低重要性的记忆按半衰期衰减，低于 0.05 则遗忘。

    返回 True 表示已遗忘（应从存储移除）。user_anchored 的记忆永不忘。
    """
    if record.get("user_anchored"):
        return False
    now = now if now is not None else time.monotonic()
    last = float(record.get("last_access", now) or now)
    age = max(0.0, (now - last) / 86400.0)
    score = importance_score(record, now)
    decayed = score * (0.5 ** (age / decay_half_life))
    record["_decayed_score"] = round(decayed, 4)
    return decayed < 0.05


def anchor(record: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """用户锚定：用户显式钉住，永不被遗忘衰减。"""
    record["user_anchored"] = True
    record["anchored_by"] = user_id
    return record


class MemoryLifecycle:
    """四阶段生命周期编排器（组合上面的纯函数）。"""

    def __init__(self) -> None:
        self.store: Dict[str, Dict[str, Any]] = {}

    def ingest(self, mid: str, record: Dict[str, Any]) -> None:
        record.setdefault("recall_count", 0)
        record.setdefault("layer", "L1_sensory")
        record.setdefault("last_access", time.monotonic())
        self.store[mid] = record

    def access(self, mid: str, now: Optional[float] = None) -> None:
        r = self.store.get(mid)
        if r:
            r["recall_count"] = int(r.get("recall_count", 0)) + 1
            r["last_access"] = now if now is not None else time.monotonic()

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        """对全部记忆跑一遍生命周期：晋升 / 蒸馏 / 遗忘。返回动作统计。"""
        stats = {"promoted": 0, "distilled": 0, "forgotten": 0}
        to_forget: List[str] = []
        for mid, r in self.store.items():
            if promote(r, now):
                stats["promoted"] += 1
            elif r.get("layer") == "L4_semantic" and not r.get("distilled"):
                distill(r)
                stats["distilled"] += 1
            if forget(r, now):
                to_forget.append(mid)
        for mid in to_forget:
            self.store.pop(mid, None)
            stats["forgotten"] += 1
        return stats
