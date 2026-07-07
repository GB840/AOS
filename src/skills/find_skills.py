"""
Find Skills — 技能搜索引擎。
搜索本地 SkillRegistry + 可选 GitHub topics 源。
对应 Hermes skills_hub.py 的能力，集成到 AOS。
"""

import logging
from typing import Any, Dict, List, Optional

from .base import Skill, SkillMeta, SkillRegistry

logger = logging.getLogger(__name__)


class FindSkills(Skill):
    """技能搜索引擎: 按名称/标签/类别/能力搜索已注册技能.

    支持:
    - 本地 SkillRegistry 精确搜索
    - 按类别筛选 (autonomous-ai-agents, creative, research 等)
    - 按标签匹配
    - 能力关键词匹配
    - (未来) GitHub topics 远程搜索 — 搜索开源社区技能

    Usage:
        registry.execute("find-skills", {"query": "搜索"})
        registry.execute("find-skills", {"category": "research"})
    """

    def __init__(self):
        meta = SkillMeta(
            name="find-skills",
            description="技能搜索引擎: 发现和安装技能, 支持按名称/标签/类别/能力搜索本地和远程技能库",
            version="1.0.0",
            tags=["meta", "discovery", "search", "skill-hub"],
            capabilities=["skill_search", "skill_discovery", "category_filter"],
            category="autonomous-ai-agents",
        )
        super().__init__(meta)
        self._registry = SkillRegistry()

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("query", context.get("q", ""))
        category = context.get("category", "")
        tag = context.get("tag", "")

        results: List[Dict[str, Any]] = []

        # ---- 按类别筛选 ----
        if category:
            results = self._registry.list_by_category(category)

        # ---- 按标签筛选 ----
        elif tag:
            results = self._registry.list_by_tag(tag)

        # ---- 关键词搜索 ----
        elif query:
            results = self._registry.search(query)

        # ---- 列出全部 ----
        else:
            results = self._registry.list_all()

        # ---- 增强: 添加技能摘要 ----
        enriched = []
        for r in results:
            entry = dict(r)
            entry["_actions"] = [
                f"registry.execute('{entry['name']}', context)",
                f"registry.get('{entry['name']}')  # 获取技能详情",
            ]
            enriched.append(entry)

        # ---- 统计 ----
        stats = self._registry.get_stats()
        by_category = {}
        for r in enriched:
            cat = r.get("category", "general")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(r["name"])

        return {
            "success": True,
            "query": query or f"category={category}" if category else "all",
            "results": enriched,
            "count": len(enriched),
            "total_registered": stats["total"],
            "by_category": by_category,
            "categories_available": list(stats.get("categories", {}).keys()),
            "hint": "使用 skill-creator 创建新技能, 使用 find-skills 搜索现有技能",
        }