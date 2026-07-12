"""多源免费搜索适配器 —— AOS fabric 的 WEB_SEARCH 平面。

自动按优先级尝试多个免费/已有凭证的搜索源，任一成功即用：
  1. 智谱 GLM web_search 工具（ZHIPU_API_KEY，国内网络通，最稳）
  2. DuckDuckGo 直连（requests 打 html.duckduckgo.com，绕过 ddgs 9.x 偷偷改用
     brave 后端导致国内超时的 bug）
  3. Jina 搜索（api.jina.ai/v1/search，免 key 免费 tier 兜底）

全部失败才报失败并列出各源错误，交给编排芯粒容错。

用户仓库里「dgg 库」= DuckDuckGo（ddgs），只是其中一个源；还有智谱/讯飞等
免费联网能力此前完全没接进 fabric 新栈，现一并纳入 fallback。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class SearchAdapter(BaseAgentAdapter):
    """多源免费联网搜索：智谱联网优先，DuckDuckGo/Jina 兜底。"""

    engine_id = "web-search"

    def advertise_capabilities(self):
        return [Capability.WEB_SEARCH]

    def health(self) -> bool:
        # 适配器本身无硬依赖，运行时按各源可用性 fallback
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        query = (req.payload.get("query")
                 or req.payload.get("task")
                 or req.payload.get("q") or "").strip()
        if not query:
            return InvokeResult(ok=False, error="缺少 query/task")
        try:
            max_results = int(req.payload.get("max_results", 5))
        except (TypeError, ValueError):
            max_results = 5

        errors: list[str] = []
        # 优先级：智谱联网（国内通）→ DuckDuckGo 直连 → Jina
        for name, fn in (
            ("zhipu", self._search_zhipu),
            ("duckduckgo", self._search_ddg),
            ("jina", self._search_jina),
        ):
            try:
                res = fn(query, max_results)
                if res and res.get("results"):
                    return InvokeResult(ok=True, data={**res, "engine": name})
            except Exception as e:  # 单源失败 → 跳下一个，不中断
                logger.warning("%s 搜索失败: %s", name, e)
                errors.append(f"{name}: {e}")
        return InvokeResult(
            ok=False,
            error=("所有搜索源均失败：" + " | ".join(errors))
            if errors else "无可用搜索源（未配置任何凭证且离线）",
        )

    # ---- 源 1：智谱 GLM web_search（国内网络通，最稳） ----
    def _search_zhipu(self, query: str, max_results: int) -> dict:
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise RuntimeError("ZHIPU_API_KEY 未配置")
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        )
        model = os.getenv("ZHIPU_MODEL", "glm-4-flash")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"请联网搜索并简要回答：{query}"}],
            tools=[{"type": "web_search", "web_search": {"search_result": True}}],
            timeout=30,
        )
        msg = resp.choices[0].message
        content = (msg.content or "").strip()
        sources: list[dict] = []
        for tc in (msg.tool_calls or []):
            if tc.type == "web_search" and tc.function and tc.function.arguments:
                try:
                    data = json.loads(tc.function.arguments)
                    for s in data.get("search_result", []) or []:
                        sources.append({"title": s.get("title", ""), "url": s.get("url", "")})
                except Exception:
                    pass
        if not content:
            raise RuntimeError("智谱联网未返回内容（可能未开通 web_search 权限）")
        return {
            "content": content,
            "query": query,
            "results": sources or [{"title": "(智谱联网回答)", "url": "", "body": content[:400]}],
            "count": len(sources),
        }

    # ---- 源 2：DuckDuckGo 直连（绕过 ddgs 9.x 的 brave 后端 bug） ----
    def _search_ddg(self, query: str, max_results: int) -> dict:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=_UA,
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.text
        results: list[dict] = []
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.S
        ):
            url, title = m.group(1), re.sub("<.*?>", "", m.group(2))
            results.append({"title": title.strip(), "url": url, "body": ""})
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.S)
        for i, s in enumerate(snippets[: len(results)]):
            results[i]["body"] = re.sub("<.*?>", "", s).strip()[:400]
        if not results:
            raise RuntimeError("DuckDuckGo 未返回结果（可能被墙）")
        summary = "\n".join(
            f"- {x['title']}: {x['body']}" for x in results[:3] if x.get("body")
        ) or query
        return {
            "content": summary,
            "query": query,
            "results": results[:max_results],
            "count": len(results),
        }

    # ---- 源 3：Jina 搜索（免 key 免费 tier） ----
    def _search_jina(self, query: str, max_results: int) -> dict:
        resp = requests.get(
            f"https://api.jina.ai/v1/search?q={requests.utils.quote(query)}&limit={max_results}",
            headers={"Authorization": "Bearer free-tier"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            {
                "title": i.get("title", ""),
                "url": i.get("url", ""),
                "body": (i.get("summary") or i.get("content") or "")[:400],
            }
            for i in data.get("results", [])
        ]
        if not results:
            raise RuntimeError("Jina 未返回结果")
        summary = "\n".join(
            f"- {x['title']}: {x['body']}" for x in results[:3] if x.get("body")
        ) or query
        return {
            "content": summary,
            "query": query,
            "results": results,
            "count": len(results),
        }
