"""Capability-based registry & router.

AOS discovers engines by the CAPABILITIES they advertise, not by name.
When a task needs a capability, the registry picks the best live provider.

This is what makes AOS open and future-proof: swap or add any engine
(one of the four, or a future one) without touching core logic. The fabric
is a thin seam, not a heavy OS substrate.
"""
from __future__ import annotations

from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import Capability


class FabricRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAgentAdapter] = {}

    def register(self, adapter: BaseAgentAdapter) -> None:
        self._adapters[adapter.engine_id] = adapter

    @staticmethod
    def _cap_to_str(cap) -> str:
        """能力统一成字符串：兼容 Capability 枚举(API 内部)与字符串(API 入参)。"""
        return cap.value if hasattr(cap, "value") else str(cap)

    def providers_for(self, cap: Capability) -> list[BaseAgentAdapter]:
        cap_str = self._cap_to_str(cap)
        return [
            a
            for a in self._adapters.values()
            if cap_str in {self._cap_to_str(c) for c in a.advertise_capabilities()}
            and a.health()
        ]

    def route(self, req: InvokeRequest) -> InvokeResult:
        providers = self.providers_for(req.capability)
        if not providers:
            cap_str = self._cap_to_str(req.capability)
            return InvokeResult(ok=False, error=f"no live provider for {cap_str}")
        # Naive-best: first healthy provider. Future: cost / latency / quality
        # scoring, or A2A negotiation between candidate engines.
        return providers[0].invoke(req)

    def snapshot(self) -> dict[str, list[str]]:
        return {
            eid: [c.value for c in a.advertise_capabilities()]
            for eid, a in self._adapters.items()
        }
