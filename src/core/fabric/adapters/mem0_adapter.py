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

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability


def _import_mem0():
    """Lazy import so the adapter is valid code even before `pip install`."""
    from mem0 import Memory  # type: ignore
    return Memory


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
            return InvokeResult(ok=False, error=str(e))

    def health(self) -> bool:
        try:
            _import_mem0()
            return True
        except Exception:
            return False

    def supported_protocols(self) -> list[str]:
        # Mem0 runs an LLM under the hood (via LiteLLM) and exposes an
        # OpenAI-compatible client in recent versions.
        return ["OpenAI"]
