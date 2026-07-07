"""Capability-based registry & router.

AOS discovers engines by the CAPABILITIES they advertise, not by name.
When a task needs a capability, the registry picks the best live provider.

This is what makes AOS open and future-proof: swap or add any engine
(one of the four, or a future one) without touching core logic. The fabric
is a thin seam, not a heavy OS substrate.
"""
from __future__ import annotations

from typing import Dict, List

from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import Capability


class FabricRegistry:
    def __init__(self) -> None:
        self._adapters: Dict[str, BaseAgentAdapter] = {}

    def register(self, adapter: BaseAgentAdapter) -> None:
        self._adapters[adapter.engine_id] = adapter

    def providers_for(self, cap: Capability) -> List[BaseAgentAdapter]:
        return [
            a
            for a in self._adapters.values()
            if cap in a.advertise_capabilities() and a.health()
        ]

    def route(self, req: InvokeRequest) -> InvokeResult:
        providers = self.providers_for(req.capability)
        if not providers:
            return InvokeResult(
                ok=False, error=f"no live provider for {req.capability.value}"
            )
        # Naive-best: first healthy provider. Future: cost / latency / quality
        # scoring, or A2A negotiation between candidate engines.
        return providers[0].invoke(req)

    def snapshot(self) -> Dict[str, List[str]]:
        return {
            eid: [c.value for c in a.advertise_capabilities()]
            for eid, a in self._adapters.items()
        }
