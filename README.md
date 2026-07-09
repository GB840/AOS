# AOS v5.0 — Agent Operating System

> 🧠 **Powered by Hermes Agent + DeerFlow 2.0** — An intelligent AI agent operating system with multi-agent orchestration, skill evolution, and visual interface.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-orange.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30-red.svg)](https://streamlit.io/)

## 🎯 What is AOS?

AOS (Agent Operating System) v5.0 is a unified platform that integrates multiple AI agent frameworks into a single cohesive system:

| Component | Framework | Role |
|-----------|-----------|------|
| 🧠 **Brain** | Hermes Agent v0.15.2 (NousResearch) | Intent recognition, reasoning, conversation |
| 🔄 **Orchestrator** | DeerFlow 2.0 (ByteDance) | Multi-agent workflow scheduling, task management |
| 🎨 **UI** | Streamlit | Visual interface with 32+ functional pages |
| 🗄️ **Memory** | SQLite + ChromaDB / Zvec | Hybrid storage with FTS5 + vector search |
| 🛡️ **Compliance** | GB/Z 185-2026 | Audit logging, identity management, distributed tracing |

## ✨ Features

- **🤖 Dual-Brain Architecture**: Hermes for chat/reasoning + DeerFlow for complex task orchestration
- **🧩 25+ Built-in Skills**: Skill Creator, Loop Engineering, Codebase Memory, ComfyUI, ViMax Video, and more
- **👥 8 Sub-Agents**: OpenClaw (browser), UI-TARS (desktop), Lobster (office), RuFlo (development), etc.
- **🔀 Dynamic Model Routing**: Automatically select the best model based on task type
- **📊 Multi-Provider Support**: Zhipu GLM, SiliconFlow, Baidu ERNIE, 讯飞, Ollama
- **🎙️ Voice Interaction**: ASR + TTS with particle cloud visualization
- **📈 Observable**: Full audit trail, identity management, distributed tracing
- **🐳 Docker-Ready**: Production-grade multi-stage Dockerfile + docker-compose profiles

## 📁 Project Structure

```
AOS/
├── src/
│   ├── api/              # FastAPI REST API (8000)
│   ├── web/              # Streamlit UI (8501)
│   ├── core/             # UnifiedBrain — the central hub
│   ├── hermes/           # Hermes Agent wrapper + DeepHermes integration
│   ├── deerflow/         # DeerFlow wrapper + 4 bridge modules
│   │   ├── scheduler.py       # 26-method DeerFlow client
│   │   ├── sandbox_bridge.py  # Real DeerFlow sandbox
│   │   ├── guardrails_bridge.py # Tool allow/deny gating
│   │   ├── agents_bridge.py   # LangGraph agent factory
│   │   └── subagent_executor.py # 965-line subagent system
│   ├── memory/           # SQLite + ChromaDB/Zvec hybrid storage
│   ├── skills/           # 25+ skill implementations
│   ├── subagents/        # Sub-agent implementations
│   ├── compliance/       # Audit, Identity, Trace
│   ├── router/           # LLM dynamic routing
│   ├── mcp/              # Model Context Protocol
│   ├── voice/            # ASR + TTS
│   └── execution/        # Sandbox, tool executor, task runner
├── configs/              # Deployment configs, Postgres init, Temporal
├── external/             # External framework clones (optional)
│   ├── hermes-agent/     # NousResearch/hermes-agent
│   └── deer-flow/        # ByteDance/deer-flow
├── tests/                # pytest test suite
├── data/                 # SQLite DB, ChromaDB, outputs (gitignored)
├── outputs/              # Generated skills, images, videos
├── docker/               # Docker utilities
├── launch.py             # Unified launcher (API + UI together)
├── pyproject.toml        # PEP 621 project definition
├── Dockerfile            # Multi-stage production build
└── docker-compose.yml    # Full stack with profiles

```

## 🗄️ Database

AOS 的全部结构化状态存于**单一 SQLite 数据库**（`config.SQLITE_DB_PATH`，WAL 模式 + 外键约束），由 `src/core/database/` 的 SQLModel ORM 定义作为唯一真相来源，分五层共 **42 张表**：基础设施 (infra) / 生态 (ecosystem) / 进化 (evolution) / 经济 (economy) / 免疫 (immune)。全文检索 (FTS5) 在 `memory` 层以虚拟表提供。

> 完整建表结构（逐表逐列）见 **[`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md)**，由 `scripts/gen_schema_doc.py` 从模型自动内省生成，与代码严格一致。

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or 3.11
- (Optional) Docker & Docker Compose
- (Optional) Ollama for local LLM

### 1. Clone & Install

```bash
# Clone the repository
cd D:\AOS

# Copy environment template
cp .env.example .env

# Install dependencies
pip install -e .

# Or install with dev tools
pip install -e ".[dev]"
```

### 2. Configure API Keys

Edit `.env` and add your API keys:

```env
ZHIPU_API_KEY=your_zhipu_key_here
SILICONFLOW_API_KEY=your_siliconflow_key_here
BAIDU_API_KEY=your_baidu_key_here
```

### 3. Start the System

**Option A: Direct Python (development)**
```bash
python launch.py
```
- API: http://localhost:8000
- Web UI: http://localhost:8501
- API Docs: http://localhost:8000/docs

**Option B: Docker Compose (production)**
```bash
# Build and run API + Web UI
make run

# Or run with database + Redis
make run-full

# Run specific profiles
docker compose --profile api up        # API only
docker compose --profile web up        # Web UI only
docker compose --profile ollama up     # Include local Ollama
docker compose --profile tracing up    # Include Jaeger tracing
```

### 4. Verify

```bash
# Check system health
curl http://localhost:8000/health

# Or use the Makefile
make health
```

## 📋 Makefile Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make dev` | Start development mode |
| `make test` | Run unit tests |
| `make test-all` | Run all tests with coverage |
| `make lint` | Run ruff linter |
| `make lint-fix` | Auto-fix linting issues |
| `make build` | Build Docker image |
| `make run` | Run API + Web UI |
| `make run-full` | Run full stack (with DB, Redis) |
| `make stop` | Stop all containers |
| `make clean` | Clean build artifacts |
| `make health` | Check system health |

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root info |
| `/health` | GET | System health check |
| `/api/chat` | POST | Chat with AOS |
| `/api/chat/stream` | POST | Streaming chat |
| `/api/knowledge` | GET/POST | Knowledge management |
| `/api/search` | POST | Memory search |
| `/api/sessions` | GET | Session management |
| `/api/tasks` | GET/POST | Task management |
| `/api/skills` | GET | List skills |
| `/api/subagents` | GET | List sub-agents |
| `/api/stats` | GET | Full system statistics |
| `/api/compliance/*` | GET | Audit, identity, trace |
| `/api/voice/*` | POST | ASR, TTS, voice chat |
| `/api/vimax/*` | GET/POST | Video generation |
| `/api/ruflo/*` | GET/POST | Development automation |
| `/api/comfyui/*` | GET/POST | Visual generation |
| `/api/ollama/*` | GET/POST | Local LLM management |
| `/api/uitars/*` | GET/POST | Desktop automation |

Full API documentation at http://localhost:8000/docs

## 🧩 Skills System

AOS includes 25+ built-in skills across categories:

### Autonomous AI Agents
- `skill-creator` — Create new skills from workflows
- `find-skills` — Discover skills from marketplace
- `superpowers` — Meta-skill for skill composition
- `j-stack` — JavaScript/TypeScript development stack

### Creative
- `frontend-design` — Generate frontend code from design specs
- `ui-ux-pro-max` — Advanced UI/UX generation

### Research & Data
- `duckduckgo-search` — Free web search
- `jina-reader` — Extract content from any URL
- `codebase-memory` — Index and query your codebase
- `lightrag` — Lightweight RAG implementation
- `searxng` — Self-hosted meta search engine
- `cognee` — Knowledge graph from text

### Media Generation
- `vimax` — Multi-agent video generation (idea→video)
- `pixelle-video` — Short video automation
- `comfyui` — Visual generation (txt2img, img2vid, style transfer)
- `open-montage` — 12 production video pipelines
- `video-use` — Video editing and processing

### Local AI
- `ollama` — Local LLM management
- `llama-cpp` — GGUF model support
- `viitor-voice` — Voice synthesis

### Automation
- `uitars` — Desktop GUI automation
- `loop-engineering` — Iterative task completion with verification
- `ruflo` — Full-stack development automation

### Utilities
- `agency-agents` — External agent integration
- `omni-route` — Smart routing
- `zvec` — Fast vector storage
- `design-md` — Design document generation
- `no-mistakes` — Error prevention
- `lingbot-map` — 3D reconstruction

## 👥 Sub-Agents

| Name | Capability | Source |
|------|-----------|--------|
| OpenClaw | Browser automation, code generation | `jiuwenclaw` |
| UI-TARS | Desktop GUI automation, screen capture | `UI-TARS-desktop` |
| Lobster | Office automation, document processing | `LobsterAI` |
| RuFlo | Code generation, review, test, security | AOS built-in |
| ViMax | Video generation (idea/novel/script→video) | HKUDS |
| Pixelle | Short video automation | Alibaba |
| Loop Engineering | Iterative task completion | AOS built-in |
| Skill Agent | Execute any registered skill | AOS built-in |

## 🏗️ Architecture

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    UnifiedBrain                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Hermes      │  │  DeerFlow    │  │  Skill       │  │
│  │  Agent       │  │  Scheduler   │  │  Registry    │  │
│  │  (chat/      │  │  (26-method  │  │  (25+ skills)│  │
│  │   reasoning) │  │   client)    │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Memory      │  │  Sub-Agent   │  │  Compliance  │  │
│  │  Manager     │  │  Registry    │  │  (Audit/     │  │
│  │  (SQLite+    │  │  (8 agents)  │  │   Identity/  │  │
│  │   ChromaDB)  │  │              │  │   Trace)     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
    │
    ├──► FastAPI (port 8000) ───► REST clients
    │
    ├──► Streamlit (port 8501) ───► Web browser
    │
    └──► DeerFlow Bridges ───► External frameworks
         (sandbox, guardrails, agents, subagents)
```

## 🧪 Testing

```bash
# Run all tests
make test-all

# Run unit tests only
make test

# Run with coverage
make test-all

# Run specific test file
pytest tests/test_memory.py -v

# Run with pytest watch mode
make test-watch
```

## 🐛 Troubleshooting

### "Hermes/DeerFlow not found" warnings

The system will fall back to built-in implementations. To use the real frameworks:

1. Clone external dependencies:
   ```bash
   git clone https://github.com/NousResearch/hermes-agent external/hermes-agent
   git clone https://github.com/ByteDance/deer-flow external/deer-flow
   ```

2. Update `.env`:
   ```env
   HERMES_SOURCE_PATH=external/hermes-agent
   DEERFLOW_SOURCE_PATH=external/deer-flow/backend
   ```

### Database locked errors

```bash
# Clean WAL files
rm -f data/sqlite/*.db-wal data/sqlite/*.db-shm
```

### Port already in use

```bash
# Find and kill the process
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Docker build fails

```bash
# Clean Docker cache
make docker-clean
docker builder prune -af
make build
```

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Run tests: `make test`
4. Run linting: `make lint-fix`
5. Commit: `git commit -am 'Add my feature'`
6. Push: `git push origin feature/my-feature`
7. Open a Pull Request

## 📚 References

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) — NousResearch
- [DeerFlow](https://github.com/ByteDance/deer-flow) — ByteDance
- [LangGraph](https://github.com/langchain-ai/langgraph) — LangChain
- [ChromaDB](https://github.com/chroma-core/chroma) — Chroma
- [Streamlit](https://streamlit.io/) — Streamlit

---

**AOS v5.0** — Built with ❤️ for the AI agent ecosystem.
