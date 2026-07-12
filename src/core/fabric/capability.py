"""Open capability taxonomy for the AOS agent fabric.

AOS composes agents by CAPABILITY, not by project name. Any real
open-source engine (OpenClaw, Hermes, DeerFlow, AG2, or anything
that appears in the future) advertises the capabilities it provides; AOS
routes a task to the best live provider. This is what makes AOS
engine-agnostic and future-proof instead of welded to four projects.
"""
from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """Canonical capabilities an agent engine may provide.

    Open by design: engines are never hard-coded; capabilities are the
    contract. Add new members as the field evolves (ACI, economy, world
    models, etc.) without touching core logic.
    """

    # Reach / access
    CHANNEL_ACCESS = "channel.access"            # reach users on 20+ chat platforms
    GROUP_ORCHESTRATION = "group.orchestration"  # multi-agent swarm / group chat

    # Cognition
    SELF_IMPROVEMENT = "cognition.self_improve"  # learns & rewrites its own skills
    LONG_HORIZON = "cognition.long_horizon"      # multi-hour autonomous execution
    PLANNING = "cognition.planning"
    REASONING = "cognition.reasoning"

    # Inference plane (the "fuel" the behaviour engines run on)
    LLM_GATEWAY = "inference.llm"              # unified LLM access via LiteLLM

    # Memory
    MEMORY_PERSISTENT = "memory.persistent"
    MEMORY_EPISODIC = "memory.episodic"
    MEMORY_SEMANTIC = "memory.semantic"
    MEMORY_KNOWLEDGE = "memory.knowledge"   # RAG / Graph-RAG knowledge hub

    # Action
    CODE_EXECUTION = "action.code_exec"
    ACI = "action.aci"                           # agent computer interface: hands on the machine
    TOOL_USE = "action.tool_use"

    # System / meta
    SAFETY = "system.safety"
    OBSERVABILITY = "system.observability"
    EVOLUTION_GOVERNANCE = "system.evolution"    # coordinates & safely governs other agents
    ECONOMY = "system.economy"                   # agent capability marketplace / exchange

    # Probe-only: synthetic task used by scripts/ipc_probe.py to measure the
    # kernel<->die IPC hop overhead (Day 8-10 gate). Not advertised by any
    # real engine, so route() isolates it to the benchmark adapter.
    BENCH_PING = "bench.ping"


# Declarative, swappable map: the four mandated real-OSS engines -> capabilities
# they are known to provide. EDIT / EXTEND FREELY. This is data, not architecture.
# "ag2" (MIT, pip `ag2`) is the real-OSS group.orchestration engine AOS
# actually runs (in-process group chat, no Docker needed). The registry is
# health-gated, so only live engines are routed.
ENGINE_CAPABILITY_MAP: dict[str, list[Capability]] = {
    "openclaw": [Capability.CHANNEL_ACCESS, Capability.TOOL_USE, Capability.MEMORY_PERSISTENT],
    "ag2": [Capability.GROUP_ORCHESTRATION, Capability.PLANNING],
    "hermes": [
        Capability.SELF_IMPROVEMENT,
        Capability.CODE_EXECUTION,
        Capability.MEMORY_PERSISTENT,
        Capability.REASONING,
    ],
    "deerflow": [
        Capability.LONG_HORIZON,
        Capability.PLANNING,
        Capability.CODE_EXECUTION,
        Capability.MEMORY_SEMANTIC,
    ],
}
