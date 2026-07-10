# AOS Kernel — Agentic OS v1.0

**Zero-dependency minimal kernel for AI agent operating systems.**

Not a plugin framework. A living substrate — agents with DNA, immunity, evolution, ecology, and trusted multimodal memory.

```bash
pip install aos-kernel
```

```python
from kernel import AOSKernel, AgentSpec
from kernel.system import build_default_system

# One-liner: full system with graceful degradation
system = build_default_system()

# Register an agent, route a message, check permission
system.kernel.register_agent(AgentSpec("bot1", "Assistant", "litellm"))
response = system.kernel.send_message(Message(sender="user", recipient="bot1", payload={"prompt": "hello"}))
```

---

## Architecture

```
24 modules, 0 heavy dependencies, stdlib-only
┌─────────────────────────────────────────────────────────┐
│  Species Dynamics                                       │
│  immunity (anomaly/circuit/heal) + evolution (DNA/fit)  │
│  + ecology (economy/selection/symbiosis)                │
├─────────────────────────────────────────────────────────┤
│  Trusted Memory (Hippo-Scroll)                          │
│  Dual-track (evidence + cognition) + pyramid retrieval  │
│  + arbitration output + metacognitive patrol            │
├─────────────────────────────────────────────────────────┤
│  Cross-Cutting (versioning/events/auth/hotswap)         │
├─────────────────────────────────────────────────────────┤
│  Plugable Skeleton (4-layer ABCs + wiring + system)     │
├─────────────────────────────────────────────────────────┤
│  AOSKernel (register/send_message/check_permission)     │
└─────────────────────────────────────────────────────────┘
```

### Core Concepts

| Layer | What it does | Key classes |
|---|---|---|
| **Kernel** | Agent lifecycle / message routing / permission | `AOSKernel` |
| **4-Layer Skeleton** | Swappable UI / AgentRuntime / MCPBus / ModelGateway | `WebUILayer` `AgentRuntimeLayer` `MCPBusLayer` `ModelGatewayLayer` |
| **Species Dynamics** | Self-healing, DNA mutation, fitness selection, resource economy | `AnomalyDetector` `Breeder` `NaturalSelection` |
| **Hippo-Scroll** | Dual-track trusted memory with arbitration | `HippoScrollEngine` `EvidenceTrack` `CognitionTrack` |
| **Cross-Cutting** | Versioning, events, auth, hot-swap | `EventBus` `VersionRegistry` `AuthBridge` `HotSwapManager` |

### Quick Start: Species Evolution Demo

```python
from kernel import AgentDNA, Gene, FitnessTracker, Breeder
from kernel import AOSKernel, AgentSpec

# Create parent DNA
parent = AgentDNA(genes=[
    Gene("engine", "litellm", "discrete", options=["litellm", "openclaw", "hermes"]),
    Gene("temperature", 0.7, "continuous", continuous_range=0.3),
    Gene("capabilities", ["chat"], "discrete", options=["chat", "code", "browser"]),
])

# Mutate → child
child = parent.mutate()
print(f"Generation: {parent.generation} → {child.generation}")
print(f"Engine mutated: {child.to_spec().engine}")

# Fitness tracking
ft = FitnessTracker()
ft.record_success("agent-a", latency=0.3, tokens=80)
ft.record_success("agent-b", latency=1.5, tokens=300)
top = ft.top_agents(2)  # a wins (faster + cheaper)

# Breed next generation
breeder = Breeder(ft)
offspring = breeder.breed([parent, child], offspring_count=3)
print(f"Offspring: {len(offspring)}, gens: {[d.generation for d in offspring]}")
```

### Hippo-Scroll: Trusted Memory

```python
from kernel import HippoScrollEngine, EvidenceAnchor, Modality

hs = HippoScrollEngine()

# Deposit immutable evidence
aid = hs.deposit_evidence(EvidenceAnchor.create("photo.jpg", Modality.IMAGE,
    spatial={"x": 100, "y": 200}, light={"caption": "A cat outdoors"}))

# Multiple interpretations coexist — no forced consensus
hs.cognition.add_consensus(aid, "Cat is outdoors", source="observer_A")
hs.cognition.add_interpretation(aid, "Might be a wild cat", source="user_X")
hs.cognition.add_interpretation(aid, "Could be a lost pet", source="user_Y")

# Arbitration: structured output with trace/consensus/disputes/conclusion
result = hs.arbitrate("Is the cat wild?", aid)
# result.trace — source evidence
# result.consensus — agreed facts
# result.disputes — divergent views listed separately
# result.conclusion — AI synthesis with basis noted
# result.confidence — DISPUTED (system preserves disagreement)
```

### Circuit Breaker + Self-Healing

```python
from kernel import CircuitBreaker, SelfHealer, CircuitBreakerOpenError

cb = CircuitBreaker("litellm-gateway", failure_threshold=3)
try:
    with cb:
        some_fragile_call()  # 3 consecutive failures → circuit opens
except CircuitBreakerOpenError:
    fallback()  # automatically routed to fallback
```

### Event Bus

```python
from kernel import EventBus, SystemEvent

bus = EventBus()
bus.subscribe("agent.*", lambda e: print(f"Agent event: {e.event_type}"))
bus.subscribe("model.failed", lambda e: alert(e.payload))
bus.emit(Event(SystemEvent.AGENT_REGISTERED, "system", {"agent_id": "bot1"}))
```

---

## Installation

```bash
# Requires Python 3.10+
pip install aos-kernel

# Or from source
git clone https://github.com/aos-dev/aos-kernel
cd aos-kernel
pip install -e .
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AOS_TOKEN_SECRET` | Development | HMAC signing key for self-contained tokens. Generate: `python -c 'import secrets; print(secrets.token_hex(32))'` |
| `OPENAI_API_KEY` / `ZHIPU_API_KEY` | Optional | API keys for model gateway (LiteLLM). Without them, calls gracefully return empty. |

## License

MIT

## Philosophy

> "Species thinking, not product thinking."
> The kernel is minimal and constant. Everything else is a plugin behind abstract interfaces.
> The system grows — it is not written once and frozen.
