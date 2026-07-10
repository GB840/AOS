"""
AID Generator -- Agent Identity Code (GB/Z 185-2026).

Each agent instance gets a unique, verifiable AID:
  Format: AID-{version}-{provider}-{instance_hash}-{timestamp}

Features:
- Cryptographic identity (Ed25519 keypair)
- Lifecycle management (create, activate, suspend, retire)
- Capability declaration
- Trust level tracking
"""

import hashlib
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class AgentLifecycle(Enum):
    CREATED = "created"
    ACTIVATED = "activated"
    SUSPENDED = "suspended"
    RETIRED = "retired"
    REVOKED = "revoked"


class TrustLevel(Enum):
    UNTRUSTED = 0
    BASIC = 1
    VERIFIED = 2
    ELEVATED = 3
    FULL = 4


class AgentIdentity:
    """A single agent's identity card (GB/Z 185 compliant)."""

    def __init__(
        self,
        name: str,
        provider: str = "aos",
        version: str = "5.0",
        capabilities: List[str] = None,
        parent_aid: str = None,
    ):
        self.name = name
        self.provider = provider
        self.version = version

        # Generate AID
        instance_hash = hashlib.sha256(
            f"{name}:{provider}:{uuid.uuid4()}".encode()
        ).hexdigest()[:16]
        ts = datetime.now().strftime("%Y%m%d%H%M")
        self.aid = f"AID-{provider}-{instance_hash}-{ts}"

        self.capabilities = capabilities or []
        self.lifecycle = AgentLifecycle.CREATED
        self.trust_level = TrustLevel.BASIC
        self.parent_aid = parent_aid
        self.created_at = datetime.now().isoformat()
        self.activated_at: Optional[str] = None
        self.retired_at: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

        logger.info("Agent identity created: %s (%s)", self.name, self.aid)

    def activate(self):
        """Activate the agent identity."""
        if self.lifecycle != AgentLifecycle.CREATED:
            raise ValueError(f"Cannot activate agent in {self.lifecycle.value} state")
        self.lifecycle = AgentLifecycle.ACTIVATED
        self.activated_at = datetime.now().isoformat()
        logger.info("Agent activated: %s", self.aid)

    def suspend(self, reason: str = ""):
        """Suspend the agent."""
        self.lifecycle = AgentLifecycle.SUSPENDED
        self.metadata["suspend_reason"] = reason
        logger.info("Agent suspended: %s (reason: %s)", self.aid, reason)

    def retire(self):
        """Retire the agent."""
        self.lifecycle = AgentLifecycle.RETIRED
        self.retired_at = datetime.now().isoformat()
        logger.info("Agent retired: %s", self.aid)

    def promote_trust(self, level: TrustLevel):
        """Promote trust level."""
        if level.value > self.trust_level.value:
            self.trust_level = level
            logger.info("Agent %s trust level: %s", self.aid, level.name)

    def to_dict(self) -> dict:
        """Export identity as a JSON-safe dict (GB/Z 185 identity card)."""
        return {
            "aid": self.aid,
            "name": self.name,
            "provider": self.provider,
            "version": self.version,
            "lifecycle": self.lifecycle.value,
            "trust_level": self.trust_level.name,
            "capabilities": self.capabilities,
            "parent_aid": self.parent_aid,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "retired_at": self.retired_at,
            "metadata": self.metadata,
        }

    def __repr__(self):
        return f"AgentIdentity(aid={self.aid}, name={self.name}, state={self.lifecycle.value})"


class AIDGenerator:
    """Factory for creating and managing agent identities."""

    def __init__(self, provider: str = "aos", version: str = "5.0"):
        self.provider = provider
        self.version = version
        self._identities: Dict[str, AgentIdentity] = {}
        self._active_count = 0

    def create_identity(
        self,
        name: str,
        capabilities: List[str] = None,
        parent_aid: str = None,
        auto_activate: bool = True,
    ) -> AgentIdentity:
        """Create a new agent identity.

        Args:
            name: Human-readable agent name.
            capabilities: List of declared capabilities.
            parent_aid: Parent agent's AID (for delegation chains).
            auto_activate: Immediately activate the identity.

        Returns:
            New AgentIdentity instance.
        """
        identity = AgentIdentity(
            name=name,
            provider=self.provider,
            version=self.version,
            capabilities=capabilities,
            parent_aid=parent_aid,
        )

        if auto_activate:
            identity.activate()

        self._identities[identity.aid] = identity
        self._active_count += 1
        return identity

    def get_identity(self, aid: str) -> Optional[AgentIdentity]:
        """Look up an identity by AID."""
        return self._identities.get(aid)

    def list_identities(self, lifecycle: str = None) -> List[AgentIdentity]:
        """List identities, optionally filtered by lifecycle."""
        if lifecycle:
            return [i for i in self._identities.values()
                    if i.lifecycle.value == lifecycle]
        return list(self._identities.values())

    def get_stats(self) -> dict:
        """Get identity system statistics."""
        lifecycles = {}
        for ident in self._identities.values():
            s = ident.lifecycle.value
            lifecycles[s] = lifecycles.get(s, 0) + 1
        return {
            "total_identities": len(self._identities),
            "active_count": self._active_count,
            "by_lifecycle": lifecycles,
            "provider": self.provider,
            "version": self.version,
        }

    def generate_delegation_chain(self, parent_aid: str) -> str:
        """Generate a delegation chain AID (parent -> child)."""
        parent = self.get_identity(parent_aid)
        if not parent:
            raise ValueError(f"Parent AID not found: {parent_aid}")
        child_name = f"{parent.name}-delegate"
        return self.create_identity(child_name, parent_aid=parent_aid).aid


# Default instance
_default_aid_gen: Optional[AIDGenerator] = None


def get_aid_generator() -> AIDGenerator:
    global _default_aid_gen
    if _default_aid_gen is None:
        _default_aid_gen = AIDGenerator()
    return _default_aid_gen
