"""Universal agent adapter - the single contract AOS owns.

Every real open-source engine plugs into AOS through this interface.
Adapters are THIN: they translate AOS's open capability calls into the
engine's native API. The engine's native API may itself speak open
protocols (MCP / A2A / ACP); the adapter is the open seam either way.

AOS never re-implements agent brains. It only standardizes HOW it talks to
them. That is the user's hard rule: real OSS engines + AOS improves on top.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .capability import Capability, ENGINE_TIER, TIER_MEDIUM


@dataclass
class InvokeRequest:
    capability: Capability
    payload: dict[str, Any]
    trace_id: str | None = None
    tier: str | None = None  # 可选：指定起始(最高)档 high/medium/low；缺省由注册表默认(级联)


@dataclass
class InvokeResult:
    ok: bool
    data: dict[str, Any] = None
    error: str | None = None


class BaseAgentAdapter(ABC):
    """The one contract AOS owns. Engine-agnostic, protocol-open."""

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Stable id, e.g. 'openclaw', 'hermes', 'deerflow', 'ag2'."""

    @abstractmethod
    def advertise_capabilities(self) -> list[Capability]:
        """Declare which capabilities this engine provides."""

    @abstractmethod
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        """Execute a capability. The adapter owns the translation to the
        engine's native (possibly open-protocol) call."""

    @abstractmethod
    def health(self) -> bool:
        """Liveness check so the fabric can route around dead engines."""

    def tier(self) -> str:
        """本引擎在全局高中低三级中的档位（动态路由第一维度）。

        默认读 ENGINE_TIER 映射（数据，可编辑）；子类可覆盖以返回自身
        运行时档位（如按配置/可用性解析）。档位参与 registry 的 tier-first
        排序与向下级联，是「端云合作 / 云端用不了就本地」的落点。
        """
        return ENGINE_TIER.get(self.engine_id, TIER_MEDIUM)

    def supported_protocols(self) -> list[str]:
        """Optional: declare open protocols spoken (MCP / A2A / ACP).

        When both ends share a protocol, plumbing becomes standard rather
        than bespoke - the openness enabler.
        """
        return []


def extract_text(out: Any) -> str:
    """把任意上游产出投影成「下游文本消费型能力（openclaw / mem0 / tool_use）
    能直接用的一句可读文本」。

    这是流水线 input 适配的核心：OrchestrationChiplet 把上一步整个 out 字典
    透传给下一步，而文本消费型下游只认 `text` / `query` 字段。本函数从常见
    out 形状（搜索 content、图 images[].url、reply、纯文本）里提取，避免
    「上游有真实产出却被当成空消息 → 假失败/空转」。

    返回空串表示确实没有任何可读内容（调用方应据此诚实失败，而非编造）。
    """
    if out is None:
        return ""
    if isinstance(out, str):
        return out.strip()
    if not isinstance(out, dict):
        return str(out).strip()

    parts: list[str] = []
    # 1) 显式文本字段（优先级最高）
    for key in ("content", "reply", "text", "summary", "answer"):
        v = out.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    # 2) 图片：把 URL 列出来（openclaw 可转发链接、记忆可索引）
    imgs = out.get("images")
    if isinstance(imgs, list):
        for im in imgs:
            if isinstance(im, dict) and im.get("url"):
                parts.append(f"图片: {im['url']}")
            elif isinstance(im, str):
                parts.append(f"图片: {im}")
    # 3) 搜索结果摘要（results 列表）
    res = out.get("results")
    if isinstance(res, list) and res:
        lines = []
        for item in res[:8]:
            if isinstance(item, dict):
                title = item.get("title") or item.get("url") or ""
                url = item.get("url") or ""
                body = item.get("body") or item.get("snippet") or ""
                line = title + (f" ({url})" if url and url not in title else "")
                if body:
                    line += f" — {body}"[:300]
                if line.strip():
                    lines.append(line.strip())
        if lines:
            parts.append("搜索结果:\n" + "\n".join(lines))
    # 4) 兜底：raw 里有 url 文本也抓
    raw = out.get("raw")
    if isinstance(raw, dict):
        data = raw.get("data")
        if isinstance(data, list):
            for d in data:
                if isinstance(d, dict) and d.get("url"):
                    parts.append(f"图片: {d['url']}")
    text = "\n".join(p for p in parts if p).strip()
    # 5) 终极兜底：上游 out 可能被序列化成字符串（如 images 字段是 str 而非 list），
    #    做一次 URL 扫描，把所有 http(s) 链接捞出来，避免「有真实产出却投影成空」。
    if not text:
        blob = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
        urls = re.findall(r"https?://[^\s\"'\\}\],]+", blob)
        if urls:
            text = "\n".join(f"链接: {u}" for u in dict.fromkeys(urls))
    return text
