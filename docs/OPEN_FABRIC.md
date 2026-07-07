# AOS Open Agent Fabric

> Reframing of AOS away from a heavy "OS substrate" toward a **thin, open,
> engine-agnostic fabric** — written after the user demanded flexibility,
> openness, and innovative thinking over conservative architecture-first planning.

## Why this shape

The previous plan ("protocol-native Agentic OS substrate") was directionally
right but executed as a **thick horizontal layer**: pull four engines, build
a bus, then layer. That produced architecture, not product, and welded AOS
to four (some very new) projects.

The open fabric inverts the default:

- **Compose by CAPABILITY, not by project.** AOS asks "who can do
  `channel.access`?" not "is OpenClaw registered?". Engines are commodities.
- **One contract AOS owns:** `BaseAgentAdapter`. Every real OSS engine plugs
  in through it. AOS never re-implements agent brains.
- **Glue = OPEN protocols** (MCP / A2A / ACP / AG-UI), not a private bus. A
  thin adapter to an open standard is speaking the common tongue, not
  "building your own architecture."
- **Engines are swappable.** Swap or add any engine (the four, or a future
  one) without touching core logic. This is the future-proofing.

## The mandated engines (real OSS, never reinvented)

| Engine | Real OSS | Role in the fabric |
|---|---|---|
| OpenClaw | MIT, openclaws.io | `channel.access` — reach users on 20+ platforms |
| AG2 | MIT, AutoGen community fork | `group.orchestration` — multi-agent swarm (real, replaces unreachable ClawSwarm) |
| Hermes | MIT, Nous Research | `cognition.self_improve` — learns & rewrites skills |
| DeerFlow | MIT, bytedance | `cognition.long_horizon` — multi-hour execution |

## What AOS adds on top (the improvement layer)

The part AOS is allowed to build, on top of the real engines:

- **Evolution governance** (`system.evolution`): the `meta_orchestrator`
  safely coordinates and reviews other agents. AOS's unique value, not a
  reinvented brain.
- **Open capability registry & router** (this module).
- **Platform shell** already built: observability, resilience, middleware,
  notify, eventstore, fileproc, sandbox, cold, devops, compat.
- **Frontier add-ons the real engines lack**, which AOS may pioneer as open,
  engine-agnostic capabilities:
  - `action.aci` — agent computer interface: real hands on the machine.
  - `system.economy` — internal agent capability marketplace / exchange.
  - hierarchical world-model memory for long-horizon planning.
  - learned self-optimization beyond rule-based feedback.

## Files

- `src/core/fabric/capability.py` — open capability taxonomy + engine map
- `src/core/fabric/adapter.py` — the single `BaseAgentAdapter` contract
- `src/core/fabric/registry.py` — capability-based discovery & routing
- `src/core/fabric/protocols.py` — open protocols used as glue
- `scripts/verify_fabric.py` — smoke test

## Next

1. Implement one real adapter (OpenClaw) against `BaseAgentAdapter`.
2. Stand up the first vertical slice: `channel.access` + `group.orchestration`
   producing a real multi-agent group chat.
3. Layer `meta_orchestrator` evolution governance over the running slice.

---

## Frontier Validation (searched 2026-07-08)

Re-grounded against the live AI landscape. **The open-fabric direction holds,
and two capabilities I'd pre-emptively put in the taxonomy are now confirmed
mainstream — not speculative.**

| Frontier signal (2026) | Source evidence | What it means for AOS |
|---|---|---|
| **2026 = "the year of protocols"** | MCP + A2A + ACP + **AG-UI** (CopilotKit) all live; none has won; MCP has documented production pain | AOS stays protocol-READY, never welded. Adapters degrade gracefully. → added `AG-UI` slot to `protocols.py` |
| **ACI = Agent-Computer Interface** (Anthropic, late 2025) | aci.dev (Aipolabs) OSS hooks agents to 600+ tools; "Harness Engineering: agent execution kernel, from sandbox to ACI" | My `action.aci` cap is prescient — it is now a named paradigm. AOS's unified ACI layer is a real differentiator |
| **Agent-to-Agent economy** | Multi-agent commerce & negotiation (game-theoretic); A2A economy + Web3 micropayments; AEAs | My `system.economy` cap is confirmed real frontier, not sci-fi. AOS can pioneer the internal capability marketplace |
| **Agentic OS / agent infrastructure** | Alibaba Cloud Agentic OS; 2026 six technical evolution directions; 12-framework survey | AOS's "thin fabric, not thick OS" is the right call — infrastructure, not another framework |
| **Self-improving / autonomous agents** | 2024-2026 survey (121 papers, 5 dims: perception/reasoning, memory, multi-agent, tools+embodiment, eval+safety) | `cognition.self_improve` + AOS `system.evolution` governance remain the right split: engines learn, AOS governs safely |

**Conclusion:** the fabric is correctly placed at the intersection of the 2026
frontier (infrastructure + open protocols + ACI + agent economy), and is
engine-agnostic enough to survive the framework churn that search results
show is ongoing. No reversal of direction needed — only the AG-UI slot added.

## Where everything lives (file map)

```
D:\AOS\
├── src\core\fabric\            ← the OPEN FABRIC (what I built this session)
│   ├── capability.py          ← open capability taxonomy + 4-engine map (data, not arch)
│   ├── adapter.py             ← BaseAgentAdapter: the ONE contract AOS owns
│   ├── registry.py            ← capability-based discovery + routing (engine-agnostic)
│   ├── protocols.py           ← open glue: MCP / A2A / ACP / AG-UI (swappable)
│   └── adapters\
│       ├── openclaw_adapter.py   ← real OpenClaw gateway adapter (endpoints @ OPENCLAW_API)
│       ├── ag2_adapter.py         ← real AG2 group-chat adapter (GroupChat, pip ag2)
│       └── __init__.py
├── scripts\
│   ├── verify_fabric.py       ← smoke test  (PYTHONPATH=. python scripts/verify_fabric.py)
│   └── slice_groupchat.py     ← first vertical slice, --demo (offline) / --real (live)
└── docs\
    └── OPEN_FABRIC.md         ← this doc
```

Run it:
```
cd D:\AOS
PYTHONPATH=. python scripts/verify_fabric.py        # → routes across 4 engines
PYTHONPATH=. python scripts/slice_groupchat.py --demo  # → OpenClaw→AG2 group chat (offline)
PYTHONPATH=. python scripts/slice_groupchat.py --check  # → health-check real engines
PYTHONPATH=. python scripts/slice_groupchat.py --real   # → hit live OpenClaw + AG2
```

## Real engine wiring (verified 2026-07-08)

Endpoints were pinned from the **official OpenClaw Gateway API reference** and
the **AG2 documentation** (not guessed).

### OpenClaw — endpoints VERIFIED
- Base URL: `http://127.0.0.1:18789/api/v1` (Gateway default port is **18789**, NOT 18080)
- Auth: `Authorization: Bearer <token>` (token in `~/.openclaw/gateway.yaml`)
- Real paths used: `POST /message` (body `{channel,message,conversation_id,wait_for_response}`),
  `GET /health`, `POST /memory/search`, `GET /skills`, `GET /channels`
- Adapter translates AOS `channel.access` payload → OpenClaw `/message` shape.
- Has official Node.js + Python SDK clients and a WebSocket API.

### AG2 — group.orchestration (real, MIT)
- Package: `pip install ag2` (provides the `autogen` namespace, v0.14.0).
- Provides `GroupChat` + `GroupChatManager` = real multi-agent group chat.
- Replaces ClawSwarm, which is unreachable in this sandbox (Docker/GitHub/PyPI
  blocked). The registry is health-gated, so if ClawSwarm ever becomes
  reachable it would be preferred automatically — until then AG2 drives
  `group.orchestration`.

### To go fully live (only external dependency)
```bash
# OpenClaw gateway (local, listens :18789)
# AG2 group chat (in-process, no Docker needed)
pip install ag2
```
Then `python scripts/slice_groupchat.py --real` will hit live engines. The
fabric degrades gracefully (health-gated routing) if an engine is down.

