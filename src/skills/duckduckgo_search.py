# -*- coding: utf-8 -*-
"""DuckDuckGo 搜索技能 —— 现统一委托 FabricHub 的 SearchAdapter（单一搜索实现）。

历史：本技能曾直接用 ddgs 库（9.x 默认后端改 brave 致国内超时）。现委托
core.fabric 的 SearchAdapter，它多源 fallback（百度/Bing/DDG/Jina/智谱），
**单一实现**，避免与 fabric 新栈双轨重复。保留原 Skill 接口（execute 签名、
返回形状），hermes/agent.py 无感切换。
"""
from .base import Skill, SkillMeta
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _legacy_shape(payload: dict) -> dict:
    """把 unified SearchAdapter 的 InvokeResult.data 映射回 legacy 技能返回形状。"""
    results = payload.get("results", []) or []
    normalized = []
    for r in results:
        normalized.append({
            "source": "duckduckgo",
            "query": payload.get("query", ""),
            "date_found": datetime.now().strftime("%Y-%m-%d"),
            "name": r.get("title", ""),
            "url": r.get("url", ""),
            "description": (r.get("body", "") or "")[:300],
        })
    return {
        "success": True,
        "query": payload.get("query", ""),
        "type": "text",
        "results": normalized,
        "count": len(normalized),
    }


class DuckDuckGoSearchSkill(Skill):
    def __init__(self):
        meta = SkillMeta(
            name="duckduckgo-search",
            description="Unified web search via FabricHub SearchAdapter "
                        "(Baidu/Bing/DDG/Jina fallback), no API key",
            version="2.0.0",
            tags=["search", "web", "duckduckgo", "ddgs", "research",
                  "privacy", "free"],
            capabilities=["web_search", "news_search", "image_search",
                          "video_search", "instant_answer"],
            category="research",
        )
        super().__init__(meta)

    def execute(self, context):
        query = context.get("query", context.get("q", ""))
        if not query:
            return {"success": False, "error": "Missing query field"}
        max_results = min(context.get("max_results", 10), 50)
        try:
            from core.fabric.adapter import InvokeRequest
            from core.fabric.adapters.search_adapter import SearchAdapter

            res = SearchAdapter().invoke(InvokeRequest(
                capability="web.search",
                payload={"query": query, "max_results": max_results},
            ))
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        if not res.ok:
            return {"success": False, "error": res.error}
        return _legacy_shape(res.data)
