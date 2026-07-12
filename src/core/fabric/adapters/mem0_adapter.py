"""Real Mem0 adapter for the AOS open fabric - the MEMORY / KNOWLEDGE PLANE.

Mem0 (mem0ai, MIT - github.com/mem0ai/mem0) is the dedicated agent memory
layer: it extracts durable facts about the user / project and serves
semantic recall. This is the "RAG / Graph-RAG / long-term memory" plane the
four behaviour engines (OpenClaw, Hermes, DeerFlow, AG2) all lack -
DeerFlow only ships light TF-IDF. Mem0 plugs in as the shared memory hub.

Thin adapter: translates AOS `memory.semantic` / `memory.knowledge` calls
into real `mem0.Memory` operations (add / search / get). AOS does NOT
re-implement memory - it delegates to the real OSS.
"""
from __future__ import annotations

from typing import Any

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult, extract_text
from ..capability import Capability


def _import_mem0():
    """Lazy import so the adapter is valid code even before `pip install`."""
    from mem0 import Memory  # type: ignore
    return Memory


def build_mem0_config() -> dict | None:
    """Best-effort 构造 mem0 配置：优先复用仓库里已有的 OpenAI 兼容 LLM key
    （SiliconFlow / Zhipu / Unified），配一个本地 chroma 向量库，让 mem0 在
    「有 key 即真持久化、无 key 即优雅降级」两种环境下都不崩。

    适配 mem0 2.0 的 config schema（与旧版差异巨大）：
    - llm/embedder 的 key 字段名是 `api_key`（非旧版的 `openai_api_key`）；
    - LlmConfig 不接受 `openai_base_url` 参数，OpenAI LLM 只读环境变量
      `OPENAI_BASE_URL`，故 base 经 env 注入（setdefault，不覆盖官方 base）；
    - EmbedderConfig 接受 `openai_base_url`，可直接传；
    - vector_store 用 chroma + 真实路径（Windows 不支持 `:memory:`）。

    返回 None 表示没有可用 key —— 调用方据此走降级。任何异常在上层隔离。
    """
    import os
    import tempfile

    # (env 名, OpenAI 兼容 base_url, llm 模型, embedding 模型)
    candidates = [
        ("SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1",
         "Qwen/Qwen2.5-7B-Instruct", "BAAI/bge-large-zh-v1.5"),
        ("ZHIPU_API_KEY", "https://open.bigmodel.cn/api/paas/v4",
         "glm-4-flash", "embedding-3"),
        ("UNIFIED_API_KEY", None, "gpt-4o-mini", "text-embedding-3-small"),
    ]
    for envk, base, model, emb in candidates:
        key = os.environ.get(envk)
        if not key:
            continue
        # mem0 2.0 的 OpenAI LLM 只认环境变量 OPENAI_BASE_URL（LlmConfig 不接受
        # openai_base_url 参数），故 base 经 env 注入；setdefault 避免覆盖用户
        # 可能已有的官方 OPENAI base。
        if base:
            os.environ.setdefault("OPENAI_BASE_URL", base)
            os.environ.setdefault("OPENAI_API_KEY", key)
        chroma_path = os.path.join(tempfile.gettempdir(), "mem0_chroma")
        llm_cfg: dict[str, Any] = {
            "provider": "openai",
            "config": {"model": model, "api_key": key},
        }
        emb_cfg: dict[str, Any] = {
            "provider": "openai",
            "config": {"model": emb, "api_key": key,
                       **({"openai_base_url": base} if base else {})},
        }
        return {
            "llm": llm_cfg,
            "embedder": emb_cfg,
            "vector_store": {
                "provider": "chroma",
                "config": {"collection_name": "mem0", "path": chroma_path},
            },
        }
    return None


def _build_memory(Memory, config):
    """版本兼容地构造 mem0.Memory 实例。

    - mem0 >= 2.0：接受单一 `config` 参数，优先用 `Memory.from_config(dict)`；
    - 旧版：可能接受 `Memory(**config)` 或 `Memory(config=...)`。
    config 为 None（无 key）时退回默认 Memory()（invoke 时若无 key 会优雅失败）。
    """
    if not config:
        return Memory()
    if hasattr(Memory, "from_config"):
        try:
            return Memory.from_config(config)
        except Exception:  # noqa: BLE001 - 退回旧版初始化
            pass
    try:
        return Memory(**config)
    except TypeError:
        return Memory(config=config)


class Mem0Adapter(BaseAgentAdapter):
    """Thin wrapper over the real Mem0 agent-memory (the "memory" plane)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        # Mem0 needs an LLM + vector store; defaults pick sane env-based ones.
        self._config: dict[str, Any] = config or {}

    @property
    def engine_id(self) -> str:
        return "mem0"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.MEMORY_SEMANTIC, Capability.MEMORY_KNOWLEDGE]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        try:
            Memory = _import_mem0()
            mem = _build_memory(Memory, self._config)
            action = req.payload.get("action", "search")
            opts = dict(req.payload.get("opts", {}))

            # 输入适配：上游产出经 OrchestrationChiplet 投影得到 `text` 字段；
            # 若调用方只给了结构化 out（图URL/搜索结果）没给显式文本，则从
            # payload 整体投影。query 缺失时以 text 兜底，避免 mem0 报
            # "Invalid query empty"（假失败）。
            text = req.payload.get("text") or extract_text(req.payload)
            query = req.payload.get("query") or text

            # mem0 2.0.11 的 search()/get_all() 不接受顶层 user_id（必须放 filters），
            # 而 add() 接受顶层 user_id（合法）。在此统一平移，保持 hub 合同
            # （memory_recall/memory_store 传 user_id 顶层）不变——mem0 API 再变只动这里。
            user_id = opts.pop("user_id", None)

            if action == "add":
                kwargs = dict(opts)
                if user_id is not None:
                    kwargs["user_id"] = user_id
                r = mem.add(text, **kwargs)
            elif action == "search":
                kwargs = dict(opts)
                if user_id is not None:
                    f = dict(kwargs.get("filters") or {})
                    f["user_id"] = user_id
                    kwargs["filters"] = f
                r = mem.search(query, **kwargs)
            elif action == "get":
                r = mem.get(req.payload.get("memory_id", ""), **opts)
            elif action == "get_all":
                kwargs = dict(opts)
                if user_id is not None:
                    f = dict(kwargs.get("filters") or {})
                    f["user_id"] = user_id
                    kwargs["filters"] = f
                r = mem.get_all(**kwargs)
            else:
                return InvokeResult(ok=False, error=f"unknown action {action}")
            return InvokeResult(ok=True, data={"result": r})
        except Exception as e:  # no LLM key / no vector store configured
            logger.warning("mem0 invoke failed: %s", e)
            return InvokeResult(ok=False, error=str(e))

    def health(self) -> bool:
        try:
            _import_mem0()
            return True
        except Exception as e:
            logger.debug("mem0 health check failed: %s", e)
            return False

    def supported_protocols(self) -> list[str]:
        # Mem0 runs an LLM under the hood (via LiteLLM) and exposes an
        # OpenAI-compatible client in recent versions.
        return ["OpenAI"]
