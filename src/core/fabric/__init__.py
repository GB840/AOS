"""AOS open agent fabric - the thin, open, engine-agnostic seam.

AOS = an open fabric that weaves real open-source agent engines together
by CAPABILITY, glues them with OPEN protocols, and improves on top
(governance, memory, safety, observability, evolution). It never
re-implements agent brains.
"""
from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import ENGINE_CAPABILITY_MAP, Capability
from .protocols import OPEN_PROTOCOLS, describe
from .registry import FabricRegistry

__all__ = [
    "ENGINE_CAPABILITY_MAP",
    "OPEN_PROTOCOLS",
    "BaseAgentAdapter",
    "Capability",
    "FabricRegistry",
    "InvokeRequest",
    "InvokeResult",
    "describe",
]
