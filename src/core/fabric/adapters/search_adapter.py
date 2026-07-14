"""多源免费联网搜索适配器 —— AOS fabric 的 WEB_SEARCH 平面。

设计原则（与编排芯粒一致）：**不弄虚**。任一源必须返回「真实搜索结果」
（带 URL 的条目，count>0）才算成功；返回套话/空结果一律不当成功，跳下一源。
全部失败才如实报错，交给下游依赖拦截（不会再冒出基于废话的假图）。

源优先级（**质量最高的实时 API 排最前，国内可达的 HTML 兜底在后**）：
  0. AnySearch 统一实时搜索（api.anysearch.com/mcp，JSON-RPC；免 key 匿名
     100次/日，配 ANYSEARCH_API_KEY 提额至 1000次/日。返回结构化 Markdown + 真实链接，
     是 agent 的「实时外脑」，质量最高，排第一）。
  1. 百度 HTML 搜索（baidu.com/s，免 key，国内通）
  2. Bing HTML 搜索（bing.com/search，免 key，国内通）
  3. DuckDuckGo 直连（html.duckduckgo.com，免 key；国内常被墙，作墙外兜底）
  4. Jina 搜索（api.jina.ai/v1/search，免 key 免费 tier；国内常被墙）
  5. 智谱 GLM web_search 工具（ZHIPU_API_KEY；glm-4-flash 免费版不支持该
     工具、付费模型需余额，故多数情况会如实跳过，不冒成功）
  *. SearXNG（可选）：若配置了 SEARXNG_URL 环境变量，插入到 Bing 之后作为
     自托管元搜索兜底。

注：AnySearch 是云端 API，若用户网络不可达（被墙/超时）会快速失败并降级到
百度/Bing，不阻塞链路；无可用凭证时它也只是其中一个源，不影响其余源。

注：用户仓库里「dgg 库」= DuckDuckGo（ddgs），但 ddgs 9.x 默认后端改 brave
致国内超时，故此处用直连 html 端点。Baidu/XFYun 是纯 LLM 聊天端点，标准
API 不带联网搜索，未用作搜索源（避免再冒假成功）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

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
    """多源免费联网搜索：真实结果优先，全部失败如实报错。"""

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
        # 优先级：AnySearch（实时外脑，质量最高）→ 百度/Bing（国内可达）
        #          → DDG/Jina（墙外兜底）→ 智谱（极少可用）
        sources = [
            ("anysearch", self._search_anysearch),
            ("baidu", self._search_baidu),
            ("bing", self._search_bing),
        ]
        searxng_url = os.getenv("SEARXNG_URL")
        if searxng_url:
            sources.append(("searxng", self._make_searxng(searxng_url)))
        sources += [
            ("duckduckgo", self._search_ddg),
            ("jina", self._search_jina),
            ("zhipu", self._search_zhipu),
        ]
        for name, fn in sources:
            try:
                res = fn(query, max_results)
                # 不弄虚：必须有真实结果（带 URL 的条目）才算成功
                if res and res.get("count", 0) > 0:
                    return InvokeResult(ok=True, data={**res, "engine": name})
                logger.warning("%s 返回但无真实搜索结果，跳过", name)
                errors.append(f"{name}: 返回无真实结果（模型拒绝/未联网/被墙）")
            except Exception as e:  # 单源失败 → 跳下一个，不中断
                logger.warning("%s 搜索失败: %s", name, e)
                errors.append(f"{name}: {e}")
        return InvokeResult(
            ok=False,
            error=("所有搜索源均失败：" + " | ".join(errors))
            if errors else "无可用搜索源（未配置任何凭证且离线）",
        )

    # ---- 源 0：AnySearch 统一实时搜索（api.anysearch.com/mcp，JSON-RPC） ----
    # 设计定位：agent 的「实时外脑」。免 key 匿名 100 次/日，配 ANYSEARCH_API_KEY
    # 提额至 1000 次/日。返回结构化 Markdown（含真实链接），质量远高于 HTML  scraping。
    # 若网络不可达（被墙/超时）快速失败 → 由下方百度/Bing 兜底，不阻塞链路。
    def _search_anysearch(self, query: str, max_results: int) -> dict:
        api_key = os.getenv("ANYSEARCH_API_KEY")
        endpoint = os.getenv("ANYSEARCH_ENDPOINT", "https://api.anysearch.com/mcp")
        headers = {
            "Content-Type": "application/json",
            "X-Anysearch-Client": "aos-fabric/1.0",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"query": query, "max_results": min(max_results, 10)},
            },
        }
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            msg = data["error"]
            raise RuntimeError(f"AnySearch 错误: {msg.get('message', msg)}")
        result = data.get("result", {})
        text = ""
        for item in result.get("content", []):
            if item.get("type") == "text":
                text = item.get("text", "") or ""
                break
        if not text:
            raise RuntimeError("AnySearch 返回空内容")
        # 不弄虚：必须从返回文本中抽到真实链接才算有结果（喂下游 media.image 用）
        links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)
        seen: set[str] = set()
        results: list[dict] = []
        for title, url in links:
            if url in seen:
                continue
            seen.add(url)
            results.append({"title": (title.strip() or url), "url": url, "body": ""})
        # 再补裸 URL（AnySearch 有时直接给出链接而非 markdown 链接）
        for url in re.findall(r"(?<!\()(https?://[^\s)\]]+)", text):
            if url in seen:
                continue
            seen.add(url)
            results.append({"title": url, "url": url, "body": ""})
        if not results:
            raise RuntimeError("AnySearch 返回但无真实链接（可能是模型套话）")
        return {
            "content": text[:2000],
            "query": query,
            "results": results[:max_results],
            "count": len(results),
        }

    # ---- 源 1：百度 HTML 搜索（国内可达，免 key） ----
    def _search_baidu(self, query: str, max_results: int) -> dict:
        resp = requests.get(
            "https://www.baidu.com/s",
            params={"wd": query, "rn": str(max_results)},
            headers=_UA,
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.text
        # 百度结果块 class 名为随机哈希（反爬），不能按 class 抓。
        # 改为按 <h3> 切块：每块取标题链接 + 标题后纯文本作摘要。
        blocks = re.split(r"(?=<h3[^>]*>)", text)
        results: list[dict] = []
        for blk in blocks:
            m = re.search(
                r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S
            )
            if not m:
                continue
            url, title = m.group(1), re.sub("<.*?>", "", m.group(2)).strip()
            if not url.startswith("http"):
                continue
            # 摘要：去掉标题后、到下一块前的纯文本（含天气摘要）
            after = re.sub(r"^.*?</h3>", "", blk, flags=re.S)
            body = re.sub(r"<.*?>", " ", after)
            body = re.sub(r"\s+", " ", body).strip()[:400]
            results.append({"title": title, "url": url, "body": body})
        if not results:
            raise RuntimeError("百度未返回结果（可能被反爬拦截）")
        summary = "\n".join(
            f"- {x['title']}: {x['body']}" for x in results[:3] if x.get("body")
        ) or query
        return {
            "content": summary,
            "query": query,
            "results": results[:max_results],
            "count": len(results),
        }

    # ---- 源 2：Bing HTML 搜索（国内可达，免 key） ----
    def _search_bing(self, query: str, max_results: int) -> dict:
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": str(max_results)},
            headers=_UA,
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.text
        # 按结果块 b_algo 切分，每块取标题链接 + 后随纯文本摘要（抗结构变化）
        blocks = re.split(r'(?=<li class="b_algo")', text)
        results: list[dict] = []
        for blk in blocks:
            m = re.search(
                r'<h2>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S
            )
            if not m:
                continue
            url, title = m.group(1), re.sub("<.*?>", "", m.group(2)).strip()
            if not url.startswith("http"):
                continue
            after = re.sub(r"^.*?</h2>", "", blk, flags=re.S)
            body = re.sub(r"<.*?>", " ", after)
            body = re.sub(r"\s+", " ", body).strip()[:400]
            results.append({"title": title, "url": url, "body": body})
        if not results:
            raise RuntimeError("Bing 未返回结果（可能被反爬拦截）")
        summary = "\n".join(
            f"- {x['title']}: {x['body']}" for x in results[:3] if x.get("body")
        ) or query
        return {
            "content": summary,
            "query": query,
            "results": results[:max_results],
            "count": len(results),
        }

    # ---- 源 3（可选）：SearXNG 自托管元搜索 ----
    def _make_searxng(self, base_url: str):
        base = base_url.rstrip("/")

        def _search(query: str, max_results: int) -> dict:
            resp = requests.get(
                f"{base}/search",
                params={"q": query, "format": "json"},
                headers=_UA,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            results = [
                {
                    "title": i.get("title", ""),
                    "url": i.get("url", ""),
                    "body": (i.get("content") or "")[:400],
                }
                for i in data.get("results", [])
            ]
            if not results:
                raise RuntimeError("SearXNG 未返回结果")
            summary = "\n".join(
                f"- {x['title']}: {x['body']}" for x in results[:3] if x.get("body")
            ) or query
            return {
                "content": summary,
                "query": query,
                "results": results[:max_results],
                "count": len(results),
            }

        return _search

    # ---- 源 4：DuckDuckGo 直连（绕过 ddgs 9.x 的 brave 后端 bug） ----
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

    # ---- 源 5：Jina 搜索（免 key 免费 tier） ----
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

    # ---- 源 6：智谱 GLM web_search（兜底；免费版不支持，付费需余额） ----
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
            tools=[{"type": "web_search", "web_search": {"enable": True, "search_result": True}}],
            timeout=40,
        )
        msg = resp.choices[0].message
        content = (msg.content or "").strip()
        sources: list[dict] = []
        for tc in (msg.tool_calls or []):
            if tc.type == "web_search" and tc.function and tc.function.arguments:
                try:
                    d = json.loads(tc.function.arguments)
                    for s in d.get("search_result", []) or []:
                        sources.append({"title": s.get("title", ""), "url": s.get("url", "")})
                except Exception as e:
                    logger.warning("智谱 web_search 结果解析失败: %s", e)
        # 不弄虚：智谱必须真的返回 web_search 结果才算成功，否则如实失败
        if not sources:
            raise RuntimeError(
                "智谱 web_search 未返回真实结果（glm-4-flash 不支持该工具，或账户无余额）"
            )
        if not content:
            content = " ".join(s.get("title", "") for s in sources[:3])
        return {
            "content": content,
            "query": query,
            "results": sources[:max_results],
            "count": len(sources),
        }
