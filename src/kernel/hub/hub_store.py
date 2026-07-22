"""智能体商店（Hub）—— AOS 智能体的发现和分发平台。

Hub 里的"智能体" = 公开的工作流模板。
用户可以浏览、搜索、收藏、一键使用、评价。

设计原则：
- 复用工作流系统：Hub 里的智能体就是公开的工作流模板
- 轻量起步：先有基本的列表/详情/搜索/使用
- 数据驱动：使用量、评分、评论都从真实使用中来
- 闭环上报：使用/评价数据同步进 Pulse，供 Evolve 优化用
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from ..studio.workflow_models import Workflow
from ..studio.workflow_store import WorkflowStore, get_workflow_store

logger = logging.getLogger(__name__)

_HUB_DIR = os.environ.get(
    "AOS_HUB_DIR",
    os.path.join("data", "workspaces", "fabric", "hub"),
)


def _hub_dir() -> str:
    os.makedirs(_HUB_DIR, exist_ok=True)
    return _HUB_DIR


def _reviews_path() -> str:
    return os.path.join(_hub_dir(), "reviews.json")


def _stats_path() -> str:
    return os.path.join(_hub_dir(), "stats.json")


def _default_pulse():
    """懒加载 PulseCollector（避免循环 import）。"""
    try:
        from kernel.pulse.pulse_collector import get_pulse_collector
        return get_pulse_collector()
    except Exception:
        return None


class HubStore:
    """智能体商店存储。"""

    def __init__(self, wf_store: WorkflowStore = None, pulse=None):
        self._lock = threading.RLock()
        self._wf_store = wf_store or get_workflow_store()
        self._pulse = pulse or _default_pulse()
        self._reviews = self._load_reviews()
        self._stats = self._load_stats()

    def set_pulse(self, pulse) -> None:
        self._pulse = pulse

    # ── 列表 / 搜索 ──

    def list_agents(self, *, category: str = "", tag: str = "",
                    sort: str = "popular", search: str = "",
                    limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """列出公开的智能体。"""
        agents = self._wf_store.list(is_template=True, category=category,
                                      tag=tag, search=search, limit=100)

        with self._lock:
            enriched = []
            for a in agents:
                wf_id = a["id"]
                stats = self._stats.get(wf_id, {})
                reviews = self._reviews.get(wf_id, [])
                avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews) if reviews else 0

                enriched.append({
                    **a,
                    "use_count": stats.get("use_count", a.get("run_count", 0)),
                    "rating": round(avg_rating, 1),
                    "review_count": len(reviews),
                    "agent_id": wf_id,
                })

        if sort == "popular":
            enriched.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        elif sort == "rating":
            enriched.sort(key=lambda x: x.get("rating", 0), reverse=True)
        elif sort == "newest":
            enriched.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return enriched[offset:offset + limit]

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索智能体。"""
        return self.list_agents(search=query, limit=limit)

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取智能体详情。"""
        wf = self._wf_store.get(agent_id)
        if not wf:
            return None

        with self._lock:
            stats = self._stats.get(agent_id, {})
            reviews = self._reviews.get(agent_id, [])
            avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews) if reviews else 0

            return {
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "category": wf.category,
                "tags": wf.tags,
                "author": wf.author,
                "version": wf.version,
                "step_count": len(wf.steps),
                "steps": [
                    {"name": s.name, "capability": s.capability, "description": s.description}
                    for s in wf.steps
                ],
                "rating": round(avg_rating, 1),
                "review_count": len(reviews),
                "use_count": stats.get("use_count", wf.run_count),
                "avg_duration": wf.avg_duration,
                "success_rate": wf.success_rate,
                "updated_at": wf.updated_at,
                "created_at": wf.created_at,
                "is_public": wf.is_public,
            }

    def use_agent(self, agent_id: str, input_data: Dict = None) -> Optional[Dict[str, Any]]:
        """使用一个智能体（运行它）。"""
        from ..studio.workflow_runner import get_workflow_runner
        runner = get_workflow_runner()

        try:
            run = runner.run(agent_id, input_data=input_data)

            with self._lock:
                stats = self._stats.get(agent_id, {"use_count": 0})
                stats["use_count"] = stats.get("use_count", 0) + 1
                stats["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._stats[agent_id] = stats
                self._save_stats()
                use_count = stats["use_count"]

            self._report_hub_usage(agent_id, run, use_count)

            return {
                "run_id": run.id,
                "status": run.status,
                "duration": run.duration,
                "output": run.output,
                "steps": run.steps,
                "error": run.error,
            }
        except Exception as e:
            logger.error("使用智能体失败: %s", e)
            return None

    # ── 评价 / 评论 ──

    def add_review(self, agent_id: str, *, user: str, rating: int,
                   comment: str = "") -> bool:
        """添加评价。"""
        if not (1 <= rating <= 5):
            return False

        review = {
            "user": user,
            "rating": rating,
            "comment": comment,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        with self._lock:
            if agent_id not in self._reviews:
                self._reviews[agent_id] = []
            self._reviews[agent_id].append(review)
            self._save_reviews()

        self._report_feedback(agent_id, rating, comment)

        return True

    def get_reviews(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取评论列表。"""
        with self._lock:
            reviews = self._reviews.get(agent_id, [])
            return reviews[-limit:][::-1]

    # ── 发布 / 下架 ──

    def publish(self, workflow_id: str) -> bool:
        """把工作流发布到 Hub（设为公开模板）。"""
        wf = self._wf_store.get(workflow_id)
        if not wf:
            return False

        wf.is_template = True
        wf.is_public = True
        wf.published_to_hub = True
        self._wf_store.save(wf)
        return True

    def unpublish(self, workflow_id: str) -> bool:
        """从 Hub 下架。"""
        wf = self._wf_store.get(workflow_id)
        if not wf:
            return False

        wf.is_public = False
        wf.published_to_hub = False
        self._wf_store.save(wf)
        return True

    # ── 分类 ──

    def list_categories(self) -> List[Dict[str, Any]]:
        """列出分类及每个分类的智能体数量。"""
        categories = {}
        agents = self._wf_store.list(is_template=True, limit=1000)
        for a in agents:
            cat = a.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1

        return [
            {"category": cat, "count": count}
            for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)
        ]

    # ── Pulse 上报 ──

    def _report_hub_usage(self, agent_id: str, run, use_count: int) -> None:
        """上报 Hub 使用数据到 Pulse。"""
        if not self._pulse:
            return
        try:
            self._pulse.record_run(agent_id, {
                "source": "hub",
                "use_count_hub": use_count,
            })
        except Exception as e:
            logger.debug("Hub 使用上报 Pulse 失败: %s", e)

    def _report_feedback(self, agent_id: str, rating: int, comment: str) -> None:
        """上报用户评价到 Pulse。"""
        if not self._pulse:
            return
        try:
            # Pulse 如果有 record_feedback 就用，没有就存到事件里
            if hasattr(self._pulse, "record_feedback"):
                self._pulse.record_feedback(agent_id, {
                    "rating": rating,
                    "comment": comment,
                })
            else:
                # 兜底：用 record_run 附带反馈数据
                self._pulse.record_run(agent_id, {
                    "type": "feedback",
                    "rating": rating,
                    "comment": comment,
                })
        except Exception as e:
            logger.debug("反馈上报 Pulse 失败: %s", e)

    # ── 内部方法 ──

    def _load_reviews(self) -> Dict[str, List]:
        if os.path.exists(_reviews_path()):
            try:
                with open(_reviews_path(), "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_reviews(self) -> None:
        try:
            with open(_reviews_path(), "w", encoding="utf-8") as f:
                json.dump(self._reviews, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存评论失败: %s", e)

    def _load_stats(self) -> Dict[str, Any]:
        if os.path.exists(_stats_path()):
            try:
                with open(_stats_path(), "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_stats(self) -> None:
        try:
            with open(_stats_path(), "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存统计失败: %s", e)


# 单例
_hub: Optional[HubStore] = None
_hub_lock = threading.Lock()


def get_hub_store() -> HubStore:
    global _hub
    if _hub is None:
        with _hub_lock:
            if _hub is None:
                _hub = HubStore()
    return _hub
