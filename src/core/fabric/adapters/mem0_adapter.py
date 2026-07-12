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

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability


def _import_mem0():
    """Lazy import so the adapter is valid code even before `pip install`."""
    from mem0 import Memory  # type: ignore
    return Memory


def build_mem0_config() -> dict | None:
    """Best-effort 构造 mem0 配置：优先复用仓库里已有的 OpenAI 兼容 LLM key
    （SiliconFlow / Zhipu / Unified），配一个内存向量库，让 mem0 在「有 key 即
    真持久化、无 key 即优雅降级」两种环境下都不崩。

    返回 None 表示没有可用 key —— 调用方据此走降级（memory facade 返回空/False）。
    注意：本函数只决定「是否有可能初始化」，真正能否连通由 mem0 在 invoke 时决定；
    任何异常都在上层被隔离，不会拖垮枢纽。
    """
    import os

    candidates = [
        # (env 名, OpenAI 兼容 base_url, 默认模型)
        ("SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-7B-Instruct"),
        ("ZHIPU_API_KEY", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
        ("UNIFIED_API_KEY", None, "gpt-4o-mini"),
    ]
    for envk, base, model in candidates:
        key = os.environ.get(envk)
        if not key:
            continue
        llm_cfg: dict[str, Any] = {
            "provider": "openai",
            "config": {"model": model, "openai_api_key": key},
        }
        emb_cfg: dict[str, Any] = {
            "provider": "openai",
            "config": {"model": "text-embedding-3-small", "openai_api_key": key},
        }
        if base:
            llm_cfg["config"]["openai_base_url"] = base
            emb_cfg["config"]["openai_base_url"] = base
        return {
            "llm": llm_cfg,
            "embedder": emb_cfg,
            "vector_store": {"provider": "memory"},
            "history_db_path": ":memory:",
        }
    return None


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
            mem = Memory(**self._config)
            action = req.payload.get("action", "search")
            opts = req.payload.get("opts", {})
            if action == "add":
                r = mem.add(req.payload.get("text", ""), **opts)
            elif action == "search":
                r = mem.search(req.payload.get("query", ""), **opts)
            elif action == "get":
                r = mem.get(req.payload.get("memory_id", ""), **opts)
            elif action == "get_all":
                r = mem.get_all(**opts)
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
