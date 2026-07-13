"""URL 内容读取适配器 —— AOS fabric 的 WEB_FETCH 平面。

从 URL 抓取网页内容并提取纯文本。搜索结果的下一步往往是「读取这个链接」，
这个适配器让 think→do 闭环能深入读取网页内容。

设计原则：零依赖、不弄虚。
- 用标准库 urllib抓取，不依赖 requests/httpx
- 用简单的 HTML 标签剥离提取文本，不依赖 BeautifulSoup
- 抓取失败如实返回错误，不编造内容
- 超时 15s，避免慢网页拖垮流水线
"""
from __future__ import annotations

import logging
import re
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

# 简单的 HTML 标签剥离
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.S | re.I)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.S | re.I)
_WS_RE = re.compile(r"\s+")


class WebFetchAdapter(BaseAgentAdapter):
    """从 URL 抓取内容并提取纯文本。"""

    def __init__(self) -> None:
        logger.info("WebFetchAdapter: ready (stdlib urllib, zero deps)")

    @property
    def engine_id(self) -> str:
        return "web-fetch"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.WEB_FETCH]

    def health(self) -> bool:
        return True  # stdlib always available

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        url = payload.get("url") or payload.get("link") or ""

        # 从上游搜索结果中提取 URL
        if not url:
            text = payload.get("content") or payload.get("text") or ""
            url = self._extract_url(text)

        if not url:
            return InvokeResult(ok=False, error="未提供 URL 且无法从输入中提取")

        try:
            req_obj = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (AOS Fabric/1.0)",
            })
            with urlopen(req_obj, timeout=15) as resp:
                raw = resp.read(200_000)  # 最多 200KB
                charset = resp.headers.get_content_charset() or "utf-8"
                html = raw.decode(charset, errors="replace")

            text = self._extract_text(html)
            if not text.strip():
                return InvokeResult(ok=False, error="页面内容为空")

            return InvokeResult(ok=True, data={
                "content": text[:10_000],  # 最多 10K 字符
                "url": url,
                "length": len(text),
            })
        except (URLError, HTTPError) as e:
            return InvokeResult(ok=False, error=f"抓取失败: {e}")
        except Exception as e:
            return InvokeResult(ok=False, error=f"解析失败: {e}")

    @staticmethod
    def _extract_url(text: str) -> str:
        """从文本中提取第一个 http(s) URL。"""
        m = re.search(r"https?://[^\s<>\]\)]+", text)
        return m.group(0) if m else ""

    @staticmethod
    def _extract_text(html: str) -> str:
        """从 HTML 中提取纯文本（简单标签剥离，零依赖）。"""
        # 去 script/style
        html = _SCRIPT_RE.sub("", html)
        html = _STYLE_RE.sub("", html)
        # 去标签
        text = _TAG_RE.sub(" ", html)
        # 压缩空白
        text = _WS_RE.sub(" ", text).strip()
        return text
