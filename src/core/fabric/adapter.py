"""Universal agent adapter - the single contract AOS owns.

Every real open-source engine plugs into AOS through this interface.
Adapters are THIN: they translate AOS's open capability calls into the
engine's native API. The engine's native API may itself speak open
protocols (MCP / A2A / ACP); the adapter is the open seam either way.

AOS never re-implements agent brains. It only standardizes HOW it talks to
them. That is the user's hard rule: real OSS engines + AOS improves on top.
"""
from __future__ import annotations

import difflib
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
    # 实际执行该请求的引擎 id（如 "openclaw"/"litellm"）。由路由层在委派成功/
    # 失败后回填，使调用方（编排芯粒 trace、A2UI 报告、路由预测器观测）能诚实
    # 呈现「到底哪个引擎跑的」——对应理念6「诚实+量化置信」「可验证即真理」。
    # 缺省 None 表示路由层未回填（如直接构造的 InvokeResult）。
    engine_id: str | None = None


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


def _text_similarity(a: str, b: str) -> float:
    """0~1 字符级相似度（difflib ratio）；任一为空返回 0。

    提升至合约层（adapter.py）：消除内核层（autopilot）对具体适配器
    （ag2_adapter）私有函数的依赖，落地「内核零依赖具体适配器」原则。
    所有适配器和内核均从本模块导入，避免双轨定义。
    """
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _dedup_text(text: str) -> str:
    """去除 LLM（尤其 glm-4-flash 长 prompt 下）把正文整段重复输出的问题。

    两层防御：
      1) 段落级：相邻近重复段落直接丢弃（防「同一段连发两遍」）；
      2) 整文级：扫描粗粒度候选边界，若某点之后的后缀与正文开头高度相似
         （>=0.9 且重复段占比足够大），则截到该点（防「整篇报告输出两次」）。
    短文本（<120 字）直接跳过，避免误伤短输出（如规划步骤）。

    提升至合约层（adapter.py）：消除内核层（autopilot）对具体适配器
    （ag2_adapter）私有函数的依赖，落地「内核零依赖具体适配器」原则。
    """
    if not text or len(text) < 120:
        return text
    # 1) 段落级去重
    paras = re.split(r"\n\s*\n", text)
    cleaned: list[str] = []
    for p in paras:
        if p.strip() and cleaned:
            if _text_similarity(cleaned[-1], p) >= 0.9:
                continue
        cleaned.append(p)
    text = "\n\n".join(cleaned).strip()
    if not text or len(text) < 120:
        return text

    # 2) 整文级去重：检测「整篇重复两遍」。
    #    用「尾部 L 字 vs 头部 L 字」做对齐比较（对副本间的换行/分隔符偏移鲁棒），
    #    从 L=n/2 向下扫到 n/4，命中高相似即判定为重复，切点 = n-L（保留第一份）。
    n = len(text)
    for L in range(n // 2, n // 4, -1):
        head = text[:L]
        tail = text[-L:]
        if _text_similarity(head, tail) >= 0.9:
            cut = n - L
            # 仅当切点落在中段（约 1/3~2/3）才采纳，避免误伤正常长文
            if n // 3 <= cut <= 2 * n // 3:
                return text[:cut].strip()
    return text


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
    # 去重：同一段文本出现在多个字段时只计一次（如 OrchestrationChiplet 把
    # content 同值投影到 text），否则下游写文件步会拿到「内容\n内容」双份。
    seen: set[str] = set()
    unique_parts: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            unique_parts.append(p)
    text = "\n".join(unique_parts).strip()
    # 5) 终极兜底：上游 out 可能被序列化成字符串（如 images 字段是 str 而非 list），
    #    做一次 URL 扫描，把所有 http(s) 链接捞出来，避免「有真实产出却投影成空」。
    if not text:
        blob = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
        urls = re.findall(r"https?://[^\s\"'\\}\],]+", blob)
        if urls:
            text = "\n".join(f"链接: {u}" for u in dict.fromkeys(urls))
    return text


def extract_media_url(out: Any) -> str:
    """从 media.image / media.video 产出中提取 web 可引用地址。

    统一收敛历史上四态分裂的 media 返回契约：
      - video-maker  → data["output"]      （本地绝对路径）
      - comfyui      → data["output_path"]  （本地绝对路径）
      - media-gen    → data["url"]          （远端 url）
      - agnes        → data["url"]          （远端 url）
    消费方统一调用本函数，不再因契约不同而静默失败。
    优先级：url → image_url → video_url → data[].url → output → output_path。
    返回空串表示确实无媒体地址（调用方应诚实失败，而非编造）。
    """
    if out is None:
        return ""
    data = out.data if hasattr(out, "data") else out
    if not isinstance(data, dict):
        return ""
    for key in ("url", "image_url", "video_url"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    nested = data.get("data")
    if isinstance(nested, list):
        for item in nested[:8]:
            if isinstance(item, dict) and item.get("url"):
                return item["url"]
    for key in ("output", "output_path"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def normalize_media_data(data: dict | None) -> dict:
    """把任一 media 适配器的原生 data 投影成统一契约（加键不删键）。

    保证返回 dict 同时含 `url` / `output` / `output_path` 三键：
      - url：web 可引用地址优先，无则用本地路径降级（消费方若为本地脚本可直用）
      - output / output_path：本地路径优先，无则用 url 兜底
    原始字段全部保留，下游按自身需要读任意键。供 FabricHub.route 出口对
    MEDIA_* 结果统一投影，使所有消费方只需读 `url` 一个键即可。
    """
    data = dict(data or {})
    url = (
        data.get("url")
        or data.get("image_url")
        or data.get("video_url")
        or next(
            (it.get("url") for it in data.get("data", []) if isinstance(it, dict) and it.get("url")),
            None,
        )
    )
    local = data.get("output") or data.get("output_path")
    if not data.get("url"):
        data["url"] = url or local or ""
    if not data.get("output"):
        data["output"] = local or url or ""
    if not data.get("output_path"):
        data["output_path"] = local or url or ""
    return data
