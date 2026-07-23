"""炼化进化蒸馏闭环（Refinery Evolution Loop）。

从每次炼化结果中学习，沉淀最佳实践模式，持续提升炼化效率和质量：
- 记录每次炼化的输入/输出/结果
- 蒸馏出成功的优化模式（哪些优化最有效）
- 学习失败模式（哪些优化导致测试失败）
- 反哺优化引擎：自动调整优先级、参数、策略

设计原则：
- 白盒进化：所有知识可复核、可解释
- 有界内存：最多保留 N 条历史，不无限增长
- 渐进式提升：从数据中学习，不盲目修改代码
- 可回滚：所有知识变更可追溯
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 蒸馏阈值
_MIN_PATTERN_SAMPLES = 3  # 至少出现多少次才沉淀为模式
_SUCCESS_RATE_THRESHOLD = 0.7  # 成功率阈值
_MAX_HISTORY = 200  # 最多历史记录数
_MAX_PATTERNS = 100  # 最多模式数

_DEFAULT_STORE_DIR = os.path.join(
    "data", "workspaces", "refinery", "evolution"
)


@dataclass
class DistilledPattern:
    """蒸馏出的优化模式（最佳实践）。"""
    pattern_id: str
    category: str  # security / quality / performance / architecture
    name: str
    description: str
    success_count: int = 0
    total_count: int = 0
    avg_score_improvement: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0
    confidence: float = 0.0  # 0-1
    applicable_files: List[str] = field(default_factory=list)
    auto_apply_recommended: bool = False

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "success_count": self.success_count,
            "total_count": self.total_count,
            "success_rate": round(self.success_rate, 3),
            "avg_score_improvement": round(self.avg_score_improvement, 2),
            "confidence": round(self.confidence, 3),
            "auto_apply_recommended": self.auto_apply_recommended,
            "applicable_files_count": len(self.applicable_files),
        }


@dataclass
class RefineryHistoryEntry:
    """一条炼化历史记录。"""
    task_id: str
    project_name: str
    initial_score: float
    final_score: float
    score_improvement: float
    proposals_applied: List[str]
    tests_passed: bool
    duration_ms: float
    timestamp: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RefineryEvolutionLoop:
    """炼化进化蒸馏闭环。

    功能：
    1. 记录每次炼化结果
    2. 蒸馏成功模式与失败模式
    3. 为优化引擎提供建议（哪些优化优先做）
    4. 学习调整参数（如复杂度阈值、风险等级划分）
    """

    def __init__(self, store_dir: str = None):
        self._store_dir = Path(store_dir or _DEFAULT_STORE_DIR)
        self._store_dir.mkdir(parents=True, exist_ok=True)

        self._history: List[RefineryHistoryEntry] = []
        self._patterns: Dict[str, DistilledPattern] = {}
        self._load()

    # ── 持久化 ──────────────────────────────────────────────────────

    def _load(self) -> None:
        """从磁盘加载历史和模式。"""
        hist_file = self._store_dir / "history.jsonl"
        if hist_file.is_file():
            try:
                with open(hist_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        self._history.append(RefineryHistoryEntry(**data))
            except Exception as e:
                logger.warning("加载炼化历史失败: %s", e)

        pat_file = self._store_dir / "patterns.json"
        if pat_file.is_file():
            try:
                with open(pat_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for pid, pdata in data.items():
                        self._patterns[pid] = DistilledPattern(**pdata)
            except Exception as e:
                logger.warning("加载蒸馏模式失败: %s", e)

        logger.info("进化蒸馏就绪: history=%d, patterns=%d",
                    len(self._history), len(self._patterns))

    def _save_history(self) -> None:
        """保存历史到 JSONL。"""
        try:
            hist_file = self._store_dir / "history.jsonl"
            with open(hist_file, "w", encoding="utf-8") as f:
                for entry in self._history[-_MAX_HISTORY:]:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("保存炼化历史失败: %s", e)

    def _save_patterns(self) -> None:
        """保存模式到 JSON。"""
        try:
            pat_file = self._store_dir / "patterns.json"
            data = {pid: p.to_dict() for pid, p in list(self._patterns.items())[:_MAX_PATTERNS]}
            with open(pat_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存蒸馏模式失败: %s", e)

    # ── 记录 ────────────────────────────────────────────────────────

    def record_refinery_result(self, task_id: str, project_root: str,
                               initial_score: float, final_score: float,
                               applied_proposals: List[Dict[str, Any]],
                               tests_passed: bool,
                               duration_ms: float,
                               notes: str = "") -> Dict[str, Any]:
        """记录一次炼化结果。"""
        project_name = Path(project_root).name
        entry = RefineryHistoryEntry(
            task_id=task_id,
            project_name=project_name,
            initial_score=initial_score,
            final_score=final_score,
            score_improvement=final_score - initial_score,
            proposals_applied=[p.get("id", "") for p in applied_proposals],
            tests_passed=tests_passed,
            duration_ms=duration_ms,
            timestamp=time.time(),
            notes=notes,
        )

        self._history.append(entry)
        # 保持在限额内
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]

        # 从这次结果中蒸馏模式
        self._distill_from_entry(entry, applied_proposals)

        self._save_history()
        self._save_patterns()

        logger.info("记录炼化结果: task=%s, score %.1f→%.1f (%.+1f)",
                    task_id, initial_score, final_score,
                    final_score - initial_score)
        return {"success": True, "entry": entry.to_dict()}

    def _distill_from_entry(self, entry: RefineryHistoryEntry,
                            applied_proposals: List[Dict[str, Any]]) -> None:
        """从单条炼化记录中蒸馏模式。"""
        score_improvement = entry.score_improvement
        success = score_improvement > 0 and entry.tests_passed

        for prop in applied_proposals:
            category = prop.get("category", "unknown")
            title = prop.get("title", "unknown")
            risk = prop.get("risk_level", "low")

            # 生成模式 ID（基于 category + 类型特征）
            pattern_key = self._pattern_key(category, title, risk)
            pattern_id = hashlib.md5(pattern_key.encode()).hexdigest()[:12]

            if pattern_id not in self._patterns:
                self._patterns[pattern_id] = DistilledPattern(
                    pattern_id=pattern_id,
                    category=category,
                    name=title[:60],
                    description=prop.get("description", "")[:200],
                    first_seen=time.time(),
                    last_seen=time.time(),
                )

            pat = self._patterns[pattern_id]
            pat.total_count += 1
            pat.last_seen = time.time()

            if success:
                pat.success_count += 1
                # 累加分数改进（后面算平均）
                pat.avg_score_improvement = (
                    (pat.avg_score_improvement * (pat.success_count - 1) + score_improvement)
                    / pat.success_count
                )

            # 计算置信度
            if pat.total_count >= _MIN_PATTERN_SAMPLES:
                # 置信度 = 成功率 * 样本权重（样本越多越可信）
                sample_weight = min(1.0, pat.total_count / _MIN_PATTERN_SAMPLES)
                pat.confidence = pat.success_rate * sample_weight

            # 自动应用推荐：高成功率 + 低风险 + 足够样本
            pat.auto_apply_recommended = (
                pat.total_count >= _MIN_PATTERN_SAMPLES
                and pat.success_rate >= _SUCCESS_RATE_THRESHOLD
                and risk == "low"
            )

    @staticmethod
    def _pattern_key(category: str, title: str, risk: str) -> str:
        """生成模式的特征键（用于归并相同类型的优化）。"""
        # 简化标题，提取关键词
        keywords = []
        for word in title.lower().split():
            if len(word) > 2:
                keywords.append(word[:10])
        return f"{category}:{risk}:{'-'.join(keywords[:5])}"

    # ── 查询 ────────────────────────────────────────────────────────

    def get_patterns(self, category: str = None,
                     min_confidence: float = 0.0,
                     auto_apply_only: bool = False) -> List[DistilledPattern]:
        """获取蒸馏出的模式。"""
        patterns = list(self._patterns.values())

        if category:
            patterns = [p for p in patterns if p.category == category]
        if min_confidence > 0:
            patterns = [p for p in patterns if p.confidence >= min_confidence]
        if auto_apply_only:
            patterns = [p for p in patterns if p.auto_apply_recommended]

        return sorted(patterns, key=lambda p: p.confidence, reverse=True)

    def get_history(self, project_name: str = None,
                    limit: int = 50) -> List[RefineryHistoryEntry]:
        """获取炼化历史。"""
        hist = self._history
        if project_name:
            hist = [h for h in hist if h.project_name == project_name]
        return sorted(hist, key=lambda h: h.timestamp, reverse=True)[:limit]

    # ── 建议 ────────────────────────────────────────────────────────

    def get_refinery_recommendations(self,
                                     quality_report=None) -> Dict[str, Any]:
        """基于历史模式，为当前项目生成炼化建议。"""
        recommendations: List[str] = []
        priority_proposals: List[Dict[str, Any]] = []

        # 高置信度的成功模式优先推荐
        high_conf = self.get_patterns(min_confidence=0.6)
        if high_conf:
            recommendations.append(
                f"发现 {len(high_conf)} 个高置信度优化模式，建议优先应用"
            )
            for pat in high_conf[:5]:
                priority_proposals.append({
                    "pattern_id": pat.pattern_id,
                    "name": pat.name,
                    "category": pat.category,
                    "confidence": pat.confidence,
                    "success_rate": pat.success_rate,
                    "avg_improvement": pat.avg_score_improvement,
                })

        # 从历史中学习平均提升
        if self._history:
            avg_improvement = sum(h.score_improvement for h in self._history) / len(self._history)
            recommendations.append(
                f"历史平均提升 {avg_improvement:+.1f} 分（基于 {len(self._history)} 次炼化）"
            )

        # 测试通过率统计
            test_pass_rate = sum(1 for h in self._history if h.tests_passed) / len(self._history)
            if test_pass_rate < 0.8:
                recommendations.append(
                    f"历史测试通过率 {test_pass_rate*100:.0f}%，建议优化后仔细验证"
                )

        return {
            "success": True,
            "recommendations": recommendations,
            "priority_proposals": priority_proposals,
            "total_patterns": len(self._patterns),
            "total_history": len(self._history),
        }

    # ── 统计 ────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """进化系统统计。"""
        if not self._history:
            return {
                "total_runs": 0,
                "total_patterns": 0,
                "avg_improvement": 0,
                "test_pass_rate": 0,
            }

        avg_imp = sum(h.score_improvement for h in self._history) / len(self._history)
        pass_rate = sum(1 for h in self._history if h.tests_passed) / len(self._history)
        high_conf = sum(1 for p in self._patterns.values() if p.confidence >= 0.7)

        return {
            "total_runs": len(self._history),
            "total_patterns": len(self._patterns),
            "high_confidence_patterns": high_conf,
            "avg_score_improvement": round(avg_imp, 2),
            "test_pass_rate": round(pass_rate, 3),
            "best_improvement": round(max(h.score_improvement for h in self._history), 1),
            "auto_apply_patterns": sum(
                1 for p in self._patterns.values() if p.auto_apply_recommended
            ),
        }
