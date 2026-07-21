"""Crawl4AI 适配器 —— AOS fabric 的 WEB_CRAWL 平面。

Crawl4AI (unclecode/crawl4ai, Apache-2.0, 5万+ Star) 把网页转成 LLM 友好的
Markdown / 结构化数据，专为 RAG、智能体、数据管线设计。这是 AOS「万物为我所用」
的又一个真实 OSS 供给方：AOS 不自研爬虫，只把 web.crawl 能力路由到它。

设计原则（对齐项目铁律 + 现有适配器范式）：
- **可选依赖懒加载**：`crawl4ai` 未安装时模块仍可 import（不触发包级 except），
  `health()` 返回 False，路由层自动忽略，绝不谎报 live。
- **缺依赖自动跳过**：与基线「缺依赖自动跳过」一致；安装后零回归注册。
- **诚实可观测**：invoke 失败如实返回 error，不编造 Markdown；engine_id 由路由层回填。
- **复用 `_safe_async_run`**：与 aci_browser_adapter 同款，避免已有事件循环中
  asyncio.run() 报 RuntimeError。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability
# 复用 aci_browser_adapter 的同款安全异步运行器（避免重复实现）
from .aci_browser_adapter import _safe_async_run


def _import_crawl4ai():
    """Lazy import so the adapter is valid code even before `pip install crawl4ai`."""
    from crawl4ai import AsyncWebCrawler  # type: ignore
    return AsyncWebCrawler


class Crawl4AIAdapter(BaseAgentAdapter):
    """Thin wrapper over the real Crawl4AI crawler (the "web.crawl" plane)."""

    def __init__(self) -> None:
        # 缓存可用性：构造时不启动浏览器（重），仅标记 crawl4ai 是否可导入。
        try:
            _import_crawl4ai()
            self._available = True
            logger.info("Crawl4AIAdapter: ready (crawl4ai available)")
        except Exception as e:  # noqa: BLE001 - 缺依赖：标记不可用，不抛
            self._available = False
            logger.info("Crawl4AIAdapter: crawl4ai 未安装，将优雅降级 (%s)", e)

    @property
    def engine_id(self) -> str:
        return "web-crawl"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.WEB_CRAWL]

    def health(self) -> bool:
        # 基于真实可导入性探测，不硬编码 True/False
        return self._available

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        url = payload.get("url") or payload.get("link") or ""
        if not url:
            return InvokeResult(ok=False, error="未提供 URL（payload 需含 url 或 link）")

        if not self._available:
            return InvokeResult(ok=False, error="crawl4ai 未安装：pip install crawl4ai")

        try:
            AsyncWebCrawler = _import_crawl4ai()

            async def _run() -> Any:
                async with AsyncWebCrawler() as crawler:
                    return await crawler.arun(url)

            result = _safe_async_run(_run())

            # 个别版本 arun 可能返回列表；取首项
            if isinstance(result, list):
                result = result[0] if result else None

            if result is None:
                return InvokeResult(ok=False, error="爬取无返回")

            # 成功标志（不同版本字段名略有差异，兼容处理）
            success = getattr(result, "success", True)
            if not success:
                err = getattr(result, "error_message", "未知爬取错误")
                return InvokeResult(ok=False, error=f"爬取失败: {err}")

            # Markdown 提取：新版本 result.markdown 是带 fit_markdown/raw_markdown
            # 的对象；旧版本可能是纯字符串。兼容两种形态。
            md = getattr(result, "markdown", None)
            text = self._extract_markdown(md)
            if not text.strip():
                return InvokeResult(ok=False, error="页面未提取到 Markdown 内容")

            return InvokeResult(ok=True, data={
                "markdown": text,
                "url": url,
                "length": len(text),
            })
        except Exception as e:  # 浏览器起不来 / 网络超时 / 依赖缺失
            logger.warning("crawl4ai invoke failed: %s", e)
            return InvokeResult(ok=False, error=str(e))

    @staticmethod
    def _extract_markdown(md: Any) -> str:
        """从 crawl4ai 的 markdown 产出中稳健提取文本。"""
        if md is None:
            return ""
        # 新版本：MarkdownGenerationResult 带 fit_markdown（去噪）/ raw_markdown
        if hasattr(md, "fit_markdown"):
            fit = getattr(md, "fit_markdown") or ""
            raw = getattr(md, "raw_markdown") or ""
            return (fit or raw).strip()
        if isinstance(md, str):
            return md.strip()
        return str(md).strip()
