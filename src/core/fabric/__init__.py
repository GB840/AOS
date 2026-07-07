"""AOS open agent fabric - the thin, open, engine-agnostic seam.

AOS = an open fabric that weaves real open-source agent engines together
by CAPABILITY, glues them with OPEN protocols, and improves on top
(governance, memory, safety, observability, evolution). It never
re-implements agent brains.
"""
from .capability import Capability, ENGINE_CAPABILITY_MAP
from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .registry import FabricRegistry
from .protocols import OPEN_PROTOCOLS, describe

__all__ = [
    "Capability",
    "ENGINE_CAPABILITY_MAP",
    "BaseAgentAdapter",
    "InvokeRequest",
    "InvokeResult",
    "FabricRegistry",
    "OPEN_PROTOCOLS",
    "describe",
]
