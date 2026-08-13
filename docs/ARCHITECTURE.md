# AOS v5.0 Architecture Overview

> One-page reference for new developers. Last updated: 2026-07.

> **视角说明**：本图是 **部署拓扑视角**（alpha 控制台 / beta 前端 / gamma 内核 三层进程拓扑），用于快速理解"进程怎么跑、端口怎么分"。另两份是不同镜头，非矛盾：
> - `docs/LIFEFORM_OS_WHITEPAPER_V6.md`：**生命体分层视角**（L0–L9 六维 + 宪法，对齐白皮书叙事）。
> - `docs/ARCHITECTURE_MAP.md`：**模块分层视角**（产品 / 内核 / 能力路由 / 基础设施 四层 + 适配器清单）。

## The Three Realities

AOS runs three conceptual layers that coexist in one codebase:

| Layer | Name | Role | Entry point |
|-------|------|------|-------------|
| **alpha** | Supervisor | Streamlit web console, user-facing | `src/web/app.py` (:8501) |
| **beta** | v5 App | FastAPI + brain.py, Hermes/DeerFlow orchestration | `src/api/main.py` (:8000) |
| **gamma** | v1 Kernel | Zero-dep capability router, skill bus, compliance | `src/kernel/` (mounted via `v5_bridge.py`) |

## Process Topology

```
                  +---------------------------+
                  |  Streamlit Console  :8501 |  <-- /web/* via gateway
                  +---------------------------+
                                |
+------------------+   +---------------------------+   +------------------+
| OpenClaw Gateway |<--|  AOS FastAPI (main) :8000 |-->| DeerFlow Gateway |
|     :18789       |   |  + MCP server      :8001 |   |     :2026        |
+------------------+   +---------------------------+   +------------------+
                                |
                       +-------------------+
                       | v1 Kernel (gamma) |  <-- mounted via v5_bridge
                       | (in-process)      |
                       +-------------------+
```

All three external services are reverse-proxied through AOS :8000 via `src/api/gateway.py`.

## Code Terrain by Size

| Module | Lines | % | Purpose |
|--------|------:|--:|---------|
| `src/skills/` | 36,935 | 53% | 25+ skill implementations (search, code, voice, image, RAG...) |
| `src/core/` | 7,933 | 11% | brain.py, Hermes/DeerFlow wrappers, DB, platform layer |
| `src/kernel/` | 6,095 | 9% | v1 kernel: capability router, compliance, evolution, hotswap |
| `src/web/` | 4,296 | 6% | Streamlit pages and components |
| `src/api/` | 2,683 | 4% | FastAPI endpoints, security, gateway proxy |
| `src/deerflow/` | 2,732 | 4% | DeerFlow scheduler, sandbox, guardrails bridge |
| `src/subagents/` | 1,299 | 2% | Sub-agent definitions and execution |
| `src/utils/` | 1,745 | 3% | Config, exceptions, sanitization, keystore |
| Others | 4,554 | 7% | router, mcp, memory, compliance, voice, execution, persistence |
| **Total** | **69,472** | | |

## Traffic Flow

```
Browser POST /api/chat
  |
  +-- AOS_KERNEL_TRAFFIC_PCT > 0? --yes--> kernel.v5_bridge.chat()
  |                                            |
  |                                            +--> kernel.send_message()
  |                                            +--> CapabilityRouter dispatch
  |
  +-- (default) ---------------------------> brain.chat()
                                               |
                          +--------------------+--------------------+
                          |                    |                    |
                     hermes.agent        deerflow.scheduler    litellm
                     (chat/reason)       (workflow/tasks)      (LLM calls)
```

- `/api/chat` -> `brain.py` (v5 path, default) or `v5_bridge.chat()` (kernel path, gated)
- `/api/v1/chat` -> kernel directly (when mounted)
- `/api/sandbox/exec` -> DeerFlow sandbox (gated by `AOS_SANDBOX_API_ENABLED=false`)
- `/web/*`, `/openclaw/*`, `/deerflow/*` -> reverse proxy to upstream services

## Traffic Switching Strategy

`AOS_KERNEL_TRAFFIC_PCT` (env var, default `0`) controls what percentage of `/api/chat` requests route through the v1 kernel instead of brain.py.

- `0` = all traffic goes to brain.py (default, safe)
- `1-99` = random percentage routed to kernel for validation
- `100` = all traffic goes to kernel

This enables gradual migration: run both paths in parallel, compare results, then switch.

## Key Files

| File | Role |
|------|------|
| `src/api/main.py` | FastAPI app, all endpoints, startup/shutdown |
| `src/core/brain.py` | Central orchestrator: wires Hermes + DeerFlow + skills |
| `src/kernel/v5_bridge.py` | Mounts v1 kernel into v5 FastAPI app (7 integration points) |
| `src/kernel/system.py` | `build_default_system()` -- assembles kernel + layers |
| `src/router/llm_router.py` | LLM provider priority router (MistralRS > Ollama > cloud) |
| `src/api/gateway.py` | Reverse proxy: /web, /openclaw, /deerflow |
| `src/api/security.py` | Auth (API key + JWT RS256), rate limiting, CORS, headers |
| `src/utils/config.py` | Pydantic BaseSettings, all env vars, secret policy |
| `src/skills/base.py` | Skill ABC: name, description, category, _execute_impl |
| `src/hermes/agent.py` | Hermes agent wrapper (chat/reasoning engine) |
| `src/deerflow/scheduler.py` | DeerFlow workflow scheduler |
| `start_all.sh` | One-command startup: AOS + OpenClaw + DeerFlow |

## Red Lines -- Do Not Touch

1. **`SANDBOX_API_ENABLED` defaults to `false`** -- the sandbox exec endpoint is an RCE surface. Never change the default to `true`.
2. **Secret policy in `_enforce_secret_policy`** -- production fail-fast for missing credentials. Never add weak default passwords.
3. **`_safe_detail()` in main.py** -- strips internal error details in production to prevent information leakage. Never bypass for production.
4. **Kernel zero-dependency contract** -- `src/kernel/` uses only stdlib. Never add third-party imports to kernel packages.
5. **Audit trail integrity** -- `ComplianceLayer.audit.verify_integrity()` is the chain-of-custody check. Never disable or weaken audit logging.
