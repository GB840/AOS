"""Universal agent adapter - the single contract AOS owns.

Every real open-source engine plugs into AOS through this interface.
Adapters are THIN: they translate AOS's open capability calls into the
engine's native API. The engine's native API may itself speak open
protocols (MCP / A2A / ACP); the adapter is the open seam either way.

AOS never re-implements agent brains. It only standardizes HOW it talks to
them. That is the user's hard rule: real OSS engines + AOS improves on top.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .capability import Capability


@dataclass
class InvokeRequest:
    capability: Capability
    payload: Dict[str, Any]
    trace_id: Optional[str] = None


@dataclass
class InvokeResult:
    ok: bool
    data: Dict[str, Any] = None
    error: Optional[str] = None


class BaseAgentAdapter(ABC):
    """The one contract AOS owns. Engine-agnostic, protocol-open."""

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Stable id, e.g. 'openclaw', 'hermes', 'deerflow', 'ag2'."""

    @abstractmethod
    def advertise_capabilities(self) -> List[Capability]:
        """Declare which capabilities this engine provides."""

    @abstractmethod
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        """Execute a capability. The adapter owns the translation to the
        engine's native (possibly open-protocol) call."""

    @abstractmethod
    def health(self) -> bool:
        """Liveness check so the fabric can route around dead engines."""

    def supported_protocols(self) -> List[str]:
        """Optional: declare open protocols spoken (MCP / A2A / ACP).

        When both ends share a protocol, plumbing becomes standard rather
        than bespoke - the openness enabler.
        """
        return []
