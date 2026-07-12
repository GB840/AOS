"""DuckDuckGo (ddgs) web search adapter —— AOS fabric 的 SEARCH 平面。

关键-free、真实联网搜索。复用 legacy `DuckDuckGoSearchSkill` 同款 `ddgs`
库，但作为 fabric 一等公民适配器注册，让编排芯粒能把「搜索/查/找」路由到它——
**不需要 BROWSER_USE_API_KEY**（那是 browser-use 真·浏览器自动化的付费 key）。

这正是用户「dgg 库」所指：DuckDuckGo（dgg）。之前 fabric 完全没有 search
能力，才把搜索硬塞给缺 key 的 browser-use——这是方向错误，现已修正。
"""
from __future__ import annotations

import logging
from typing import Any

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)

try:
    from ddgs import DDGS
    HAS_DDGS = True
except Exception:  # pragma: no cover - 依赖缺失时优雅降级
    HAS_DDGS = False


class SearchAdapter(BaseAgentAdapter):
    """免 key 真实联网搜索（DuckDuckGo / ddgs）。"""

    engine_id = "duckduckgo"

    def advertise_capabilities(self):
        return [Capability.WEB_SEARCH]

    def health(self) -> bool:
        return HAS_DDGS

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not HAS_DDGS:
            return InvokeResult(ok=False, error="ddgs 未安装：pip install ddgs")
        query = (req.payload.get("query")
                 or req.payload.get("task")
                 or req.payload.get("q") or "").strip()
        if not query:
            return InvokeResult(ok=False, error="缺少 query/task")
        stype = req.payload.get("type", "text")
        try:
            max_results = int(req.payload.get("max_results", 5))
        except (TypeError, ValueError):
            max_results = 5
        region = req.payload.get("region", "wt-wt")
        try:
            with DDGS() as ddgs:
                method = getattr(ddgs, stype, ddgs.text)
                raw = list(method(query, max_results=max_results, region=region))
        except Exception as e:  # 网络不可达等 → 干净失败，交给编排芯粒容错
            logger.warning("duckduckgo 搜索失败: %s", e)
            return InvokeResult(ok=False, error=f"duckduckgo 搜索失败: {e}")
        results: list[dict[str, Any]] = []
        for r in raw:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href") or r.get("url", ""),
                "body": (r.get("body") or "")[:400],
            })
        # 产出 content 摘要，供下游 media.image / inference.llm 经 in_from:previous 直接消费
        summary = "\n".join(
            f"- {x['title']}: {x['body']}" for x in results[:3] if x.get("body")
        ) or query
        return InvokeResult(
            ok=True,
            data={"content": summary, "query": query, "type": stype,
                  "results": results, "count": len(results)},
        )
