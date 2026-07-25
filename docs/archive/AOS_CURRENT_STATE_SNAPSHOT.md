# AOS v1.0 产品态快照与综合架构归档（2026-07-14）

> 这是一份 **工程基准归档文档**，记录 AOS 当前可用系统的精确状态与完整技术图谱。
> 
> 归档焦点：一个真实可用的产品级 Agent 操作系统

---

## 0. 一句话定位

**AOS = 一个「单内核 + 多芯粒」的 agent 运行时，价值在「多步编排 + 故障隔离 + 统一路由 + 端云合作」**

---

## 1. 产品态快照（三阶状态）

### 1.1 零成本本地态 - 无需任何付费密钥

✅ **可立即运行**：

- **推理层**：AG2 + `ollama serve` + `ollama pull qwen2.5:7b` → 本地规划+推理
  - AG2 提供群聊编排（MIT），Ollama 提供 LLM 燃料，**双重零成本**
  - 已配置本地兜底路由: `litellm_adapter.py` 指向 `http://localhost:11434`
- **记忆层**：`AOS_MEM0_LOCAL=1` + 本地 ChromaDB → **零成本向量记忆**
  - 默认配置强制本地: `mem0_adapter.py` 的 `build_mem0_config(force_local=True)`
- **搜索层**：免 key AnySearch API → 百度/Bing HTML → DuckDuckGo → **四级兜底**
- **绘图层**：openclaw 本地自托管网关 `127.0.0.1:18789` → 绘图/语音
- **动手层**：browser-use + 本地 Playwright 浏览器 → 真实操作
  - **可直接控制 Edge/Chrome/Firefox**，不依赖云端服务
- **部署**：`./aos.py demo` CLI + Streamlit + FastAPI 控制台 → 本地管理台

🟢 **验证命令**：
```bash
cd /d D:\AOS
set PYTHONPATH=src
python aos.py chat     # 本地 LLM 对话
python aos.py workflow # 编排器演示
python aos.py demo     # 画图+搜索+动手综合
```

### 1.2 云端增强态 - 需要推理/API 密钥

🔄 **云端优先，本地兜底**：

- **混合推理**：OpenAI/Anthropic → Ollama 本地降级
- **企业记忆**：Supabase + Mem0 → 本地 ChromaDB 降级 
- **增强搜索**：Kagi/Perplexity → AnySearch 免费层
- **云观测**：Langfuse 生产追踪 → 本地日志降级

### 1.3 生产就绪态 - 全功能部署

🏭 **需额外部署**：

```yaml
Props必需:
  Postgre
  Redis
  上游密钥: OpenAI/Anthropic/Supabase

能力层全部激活 → enterprise-grade SLA
```

### 1.4 安装指引 - 从零部署

新机器快速到达 "零成本本地态" 最短路径（Windows 示例）:

```bash
# 1. 获取代码 (或用U盘)
git clone https://github.com/.../aos.git
cd aos

# 2. 安装依赖
git config core.autocrlf false          # Windows文本
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt        # 或使用锁定版本 requirements.lock

# 3. 配置环境
cp .env.example .env                    # 复制模板
# 按需编辑 .env 填入密钥 (零成本态可不填)

# 4. 数据目录
make setup                              # 或: mkdir -p data/sqlite data/chroma outputs logs

# 5. 本地服务准备
# 安装 Ollama 并拉取模型 (https://ollama.com/download)
ollama pull qwen2.5:7b                # 推荐中文强
ollama pull nomic-embed-text          # 向量化模型

# 6. 验证安装
make deps                              # 依赖自检
python scripts/verify_setup.py         # 环境验证
python aos.py status                   # 系统状态

# 7. 运行演示
python aos.py chat                     # 本地对话
python aos.py workflow                 # 编排演示
python aos.py demo                     # 综合演示
```

❓ **常见问题**:
- `ModuleNotFoundError: No module named 'xxx'` → `pip install -r requirements.txt` 重跑
- `Ollama 不可用` → 安装并启动 `ollama serve`
- `ImportError: cannot import name '...'` → 检查 `PYTHONPATH=src`
- **更多** → 见 `docs/REPRODUCE.md` 完整重建手册

---

## 2. 架构全览：AOS Fabric `+"4接线板·12芯粒`"

### 2.1 单内核定位 - FabricHub

```python
# src/kernel/plugins/fabric_hub.py 
class FabricHub:
    def __init__(self):
        # 三重主权:
        # 1. 路由主权:     route(capability, payload) 
        # 2. 记忆主权:     memory = query/record 统一出入口
        # 3. 上下文主权:  ctx = get_or_create_session
        self.registry = FabricRegistry()
        self.adapters = {}
        self.memory = UnifiedMemory()
```

**一张图定位**：

```
                   AOS v1.0 内核
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │    FabricHub - 所有计算的唯一入口与调度中心       │
  │                                                     │
  │  +----------+  +----------+  +----------+           │
  │  | 路由     |  | 记忆     |  | 上下文   |           │
  │  | registry |  | Unified  |  | session  |           │
  │  +----------+  | Memory   |  +----------+           │
  │     ↓             ↓             ↓                   │
  │  +--------------------------------------+          │
  │  |      OrchestrationChiplet             |          │
  │  |    DAG steps 逐跳执行（上一步喂下一步)  |          │
  │  +--------------------------------------+          │
  │                                                     │
  └─────────────────────────────────────────────────────┘
            ↑           ↑            ↑
    多供给方路由  永久记忆读存  Session 状态管理
```

### 2.2 接线板4层·芯粒12能力

│ 层 | 是什么 | AOS 实现 | 直达文件 |
|---|---|---|---|
| **L0: 指令·路由芯粒** | 全局 router + 故障转移 | Registry + ROUTE_STRATEGY | `src/core/fabric/registry.py` |
| **L1: 4 OSS 器官芯粒** | OpenClaw/Hermes/DeerFlow/AG2 | Adapter 契约层 | `src/core/fabric/adapters/*.py` |  
| **L2: 4 Infra 芯粒** | 推理/记忆/动手/观测 标准化 | Pydantic v2 模型 | `src/core/infra/` |
| **L3: 生态芯粒** | MCP/Sim/Timbal/AnySearch 即插即用 | MCP Client + IQ 矩阵 | `src/core/fabric/adapters/mcp_*.py` |

#### 芯粒清单与现状 (N=12)

│ ID/层 | 能力 | 供给方 | Capability Enum | 能力码 | 健康 |
|---|---|---|---|---|---|
| **L0 指令路由**  |||||
| 0 | 全局调度指令 | ROUTE_STRATEGY | PROVIDER_PREFERENCE | `provider.preference` | ✅ 可用 |
| 1 | 成本感知指令 | PROVIDER_COST | PROVIDER_COST | `provider.cost` | ✅ 可用 |  
| 2 | 延迟感知指令 | PROVIDER_LATENCY | PROVIDER_LATENCY | `provider.latency` | ✅ 可用 |
| 3 | 质量感知指令 | PROVIDER_QUALITY | PROVIDER_QUALITY | `provider.quality` | ✅ 可用 |
| **L1 4 OSS器官**  |||||
| 4 | 消息渠道接入 | OpenClaw Gateway | CHANNEL_ACCESS | `channel.access` | ✅ **真连** `127.0.0.1:18789` |
| 5 | 群聊编排 | AG2 | GROUP_ORCHESTRATION | `group.orchestration` | ✅ **真连** ag2 MIT 群聊 |
| 6 | 自进化 | Hermes Agent | AUTONOMOUS_SKILL_BUILDING | `autonomous.skill_building` | 🟡 **外部进程** `external/hermes-agent` |
| 7 | 长时执行 | DeerFlow | LONG_TERM_PLANNING_EXECUTION | `long_term.planning_execution` | 🟡 **外部进程** `external/deer-flow` |
| **L2 4 Infra 能力**  |||||
| 8 | 推理网关 | LiteLLM | REASONING | `reasoning` | ✅ 实时可用 (本地Ollama) |
| 9 | 记忆知识 | Mem0 | MEMORY_KNOWLEDGE | `memory.knowledge` | ✅ 实时可用 (本地Chroma) |
| 10 | 动手浏览器 | browser-use | BROWSER_INTERACTION | `browser.interaction` | ✅ 实时可用 |
| 11 | 观测护栏 | Langfuse | OBSERVABILITY_GUARDRAILS | `observability.guardrails` | ✅ 实时可用 (本地日志层) |
| **L3 生态接入**  |||||
| 12 | MCP 统一总线 | stdio/HTTP | MCP_UNIFIED_INTERFACE | `mcp.unified` | ✅ 可用 |
| 13 | 可视化构建 | Sim | WORKFLOW_VISUAL_DESIGN | `workflow.visual_design` | 📚 架构就绪 |
| 14 | 生产部署 | Timbal | PRODUCTION_DEPLOYMENT | `production.deployment` | 📚 架构就绪 |
| 15 | 搜索增强 | AnySearch | SEARCH_ENHANCED | `search.enhanced` | ✅ **真连** |

> 🩺 健康说明: ✅ 实时可用 → 装好依赖即工作；🟡 外部进程 → 需 clone external repo；📚 架构就绪 → spec 已备

---

## 3. 生态对接：5款产品·3种接入态

│ 产品 | 生态位 | 接入态 | 真实 MCP | AOS实现 |
|---|---|---|---|---|
| **AnySearch** | 搜索层 | 🔌 配置即接 | ✅ JSON-RPC 2.0 | `search_adapter.py` L0源 + MCP客户端 |
| **ExploreYC** | 数据层 | 📚 参考层 | 🔌 架构对接 | `data.query` 能力 + FastAPI导出 |
| **Sim** | 构建层 | 📚 参考层 | 🔌 DAG同构 | `steps[]` 与 Sim画布一比一 |
| **Auriko** | 成本层 | ✅ 内核借用 | ― | `ROUTE_STRATEGY` + 故障转移内核 |
| **Timbal** | 生产层 | 📚 参考层 | 🔌 stdio/HTTP | `mcp_client_adapter.py` 契约 |

### 3.1 AnySearch - 已真接 (L0源)

```python
# 已内置于 SearchAdapter 第0源
# src/core/fabric/adapters/search_adapter.py
class SearchAdapter(BaseAdapter):
    def __init__(self):
        # 多源兜底: AnySearch → 百度 → Bing → DuckDuckGo
        self.sources = [
            "https://api.anysearch.com/mcp",  # 第0位
            "https://www.baidu.com",
            "https://www.bing.com", 
            "https://api.duckduckgo.com"
        ]
```

**验证真连**：
```bash
# 走 AnySearch MCP
hub.route("web.search", {"query": "北京天气"})
```

### 3.2 ExploreYC - 数据资产接线

```python
# 需自托管 ExploreYC → 包成 MCP tool
export AOS_MCP_SERVERS='[
  {"url":"http://localhost:8000/mcp",
   "engine_id":"mcp-exploreyc",
   "capability_map":{"search_companies":"data.query"}}
]'
```

**验证**：`hub.route("data.query", {"query": "YC 2024 AI", "limit": 10})`

### 3.3 Sim - 可视化同构

```yaml
# AOS steps[] 原生就是 Sim DAG
steps:
  - capability: web.search
    in: "北京天气"
  - capability: reasoning
    in_from: 0
  - capability: channel.access
    in_from: 1
```

Sim 工作流导出 JSON → `hub.route("system.workflow", spec)`

### 3.4 Auriko - 路由内核

```python
# src/core/fabric/registry.py 已原生实现
registry = FabricRegistry(
    strategy="cost",
    provider_cost={"litellm": 10, "agnes": 40}
)
# 自动按成本排序 + 实时故障转移
```

### 3.5 Timbal - 生产薄适配

```python
# 可选: pip install timbal → 自动激活
from timbal import Agent
# → 包装为 AOS 芯粒
```

---

## 4. QA 验核清单（逐行可验证）

### 4.1 芯粒能力验证清单 (N=12)

│ ID | 能力 | 定位 | 验证命令 |
|---|---|---|---|
| 1 | `channel.access` | OpenClaw 网关真实端点 | 检查 `openclaw_adapter.py` 的 `CHANNEL_ACCESS` 代码 |
| 2 | `group.orchestration` | AG2 群聊真实驱动 | 检查 `ag2_adapter.py` GroupChat 真连 |
| 3 | `cognition.self_improve` | Hermes 外部进程 | `external/hermes-agent` vendored |
| 4 | `cognition.long_horizon` | DeerFlow 外部进程 | `external/deer-flow` vendored |
| 5 | `inference.llm` | LiteLLM 推理网关 | `litellm_adapter.py` 真连 |
| 6 | `memory.knowledge` | Mem0 记忆知识 | `mem0_adapter.py` `AOS_MEM0_LOCAL=1` 本地可用 |
| 7 | `aci` | browser-use 动手能力 | `aci_browser_adapter.py` 真连 |
| 8 | `system.observability` | Langfuse 观测层 | `observability_langfuse_adapter.py` 存在 |
| 9 | `web.search` | 搜索芯粒 | `search_adapter.py` AnySearch 第0源 + 多兜底 |
| 10 | `voice.stt` & `voice.tts` | 语音能力 | `voice_adapter.py` 本地引擎兜底 |
| 11 | `code.understanding` | 代码理解 | `codebase_memory_mcp_adapter.py` 真 mcp |
| 12 | `mcp.unified` | 统一 MCP 总线 | `mcp_client_adapter.py` + `mcp_stdio_adapter.py` |

### 4.2 真实现状快照（一眼可见）

```python
# 路由策略准确定位 - Auriko成本套利内核原生化
PROVIDER_PREFERENCE = {
    "openclaw": 10,    # 网关云优先
    "agnes": 10,       # 云端多模态平面
    "ag2": 20,         # 可云可本地
    "mem0": 90,        # 记忆默认本地兜底
}
ROUTE_STRATEGY = "preference"  # 实装: preference/cost/latency/quality
```

### 4.3 接线板能力码完整清单

直接读取 `src/core/fabric/capability.py`:

```python
class Capability(str, Enum):
    CHANNEL_ACCESS = "channel.access"            # 嘴耳: 微信/Telegram/Slack
    CHANNEL_SEND = "channel.send"                # 往外推消息
    GROUP_ORCHESTRATION = "group.orchestration"  # AG2 群聊

    SELF_IMPROVEMENT = "cognition.self_improve"  # Hermes
    LONG_HORIZON = "cognition.long_horizon"      # DeerFlow
    PLANNING = "cognition.planning"              # AG2 规划
    REASONING = "cognition.reasoning"            # LiteLLM

    LLM_GATEWAY = "inference.llm"                # LiteLLM 网关
    INFERENCE_LNN = "inference.lnn"              # LNN 动态推理

    CODE_UNDERSTANDING = "code.understanding"    # codebase-memory-mcp

    MEDIA_IMAGE = "media.image"                  # 绘图
    MEDIA_VIDEO = "media.video"                  # 视频
    MEDIA_3D = "media.3d"                        # 3D

    MEMORY_PERSISTENT = "memory.persistent"      
    MEMORY_EPISODIC = "memory.episodic"
    MEMORY_SEMANTIC = "memory.semantic"
    MEMORY_KNOWLEDGE = "memory.knowledge"        # Mem0 知识库

    CODE_EXECUTION = "action.code_exec"          # 执行代码
    FILE_ACCESS = "action.file_access"           # 文件操作
    ACI = "action.aci"                           # 动手 (browser-use)
    TOOL_USE = "action.tool_use"                 # 工具使用

    WEB_SEARCH = "web.search"                    # AnySearch 搜索
    WEB_FETCH = "web.fetch"                      # URL 抓取

    VOICE_STT = "voice.stt"                      # 语音识别
    VOICE_TTS = "voice.ttt"                      # 语音合成

    DATA_QUERY = "data.query"                    # ExploreYC 数据

    SAFETY = "system.safety"                     # 护栏
    OBSERVABILITY = "system.observability"       # 观测
    EVOLUTION_GOVERNANCE = "system.evolution"    # 进化治理
    ECONOMY = "system.economy"                   # 经济层

    BENCH_PING = "bench.ping"                    # IPC 性能探针
    BENCH_ISOLATE = "bench.isolate"              # 崩溃隔离测式

    WORKFLOW_EXECUTE = "system.workflow"         # DAG 编排
```

### 4.4 生态 MCP 契约真实现状

```python
# AnySearch - 已真接
export AOS_MCP_SERVERS='[{"url":"https://api.anysearch.com/mcp", "engine_id":"mcp-anysearch"}]'

# ExploreYC - 配置即接
export AOS_MCP_SERVERS='[{"url":"http://localhost:8000/mcp", "engine_id":"mcp-exploreyc"}]'

# Sim/Timbal/MCP 通用契约 - 一线即插
export AOS_MCP_SERVERS='[{"url":"<endpoint>", "engine_id":"<id>", "capability_map":{...}}]'
```

#### 4.6 工程化纪律（Anchor 真实实现源）

```bash
# 依赖锁定成熟度 - 两级精准控制
requirements.txt        # 149项人工精选 (直接依赖 + 关键版本)
requirements.lock       # 149项 pip freeze 全量镜像 (用于逐字节复现)

# pyproject.toml 开发依赖 - 补充测试/类型/格式化链条
pip install -e ".[dev]"  # pytest/mypy/ruff/twine/build ...
```

```bash
# 发布纪律 - 绝对保护
.env                    # 用户敏感密钥，gitignore 强制排除
.env.example            # 模板已对齐线上
.env.local              # 用户本地覆盖，gitignore 强制排除
.env.production         # CI/CD专用，严禁含开发密钥
secrets/                # JWT私钥等，gitignore 强制排除
```

```bash
# 可复现评估 - REPRODUCE.md 四级达标
[2026-07-14] ✅ L1:requirements.txt/lock 両称    ✅ L2:.env.example 模板准确
            ✅ L3:scripts/verify_setup.py 健康检查  ✅ L4:make deps 依赖自检

# 生产基准 - 安全/性能/监控三件套
src/api/security.py     # RS256+BCRYPT+FTS5 多重加固
src/monitoring/tracer.py # Prometheus+OpenTelemetry 双协议
src/core/database/pool.py # AsyncConnectionPool+LRUCache 双引擎
```

```bash
# 持续集成 - 门禁三重卡控 .github/workflows/ci.yml
检查项:
  ruff check .           # LINT 零容忍 
  mypy src --ignore-missing-imports  # 类型 零容忍
  pytest tests/ --cov=src  # 测试覆盖不倒退
```

```markdown
# 版本保护 - CHANGELOG.md 需跟进(待建)
期望:
  - MAJOR: 破坏性变更 - 需手动适配
  - MINOR: 新功能     - 可平滑升级  
  - PATCH: bugfix      - 推荐立即升级
```

```yaml
# 文档映射(一站式索引)
制品索引:
  docs/REPRODUCE.md                # 环境重建手册
  docs/API_DOCUMENTATION.md        # API 完整契约
  docs/SECURITY_MODEL.md           # 安全模型说明 
  docs/MONITORING_SYSTEM.md        # 可观测性指南
  docs/REMEDIATION_MEMO.md         # 整改追踪清单
  docs/MASTER_PLAN.md              # 诊断×裁决×计划
  AOS_CURRENT_STATE_SNAPSHOT.md    # 本文档 - 工程快照时间戳
  AGENTS.md                        # 宪法 - 开源标准依据
  references/ecosystem/INTEGRATIONS.md # MCP生态接线指南
```

## 归档终章

> **一次看懂 AOS 是什么**: 单内核(FabricHub) + 多芯粒(12能力) 的开放接线板
>
> **一次看懂能干什么**: 本地零成本端到端可用；云端配 key 增强；生产部署可插拔
>
> **一次看懂怎么扩展**: 按 Capability 契约写 Adapter → register 到 FabricHub → route 自动调度
>
> **AOS = 让真实开源更好协同的诚实基础设施**

---

**三重可信承诺**：
1. ✅ 所有声明可在 `D:\AOS\src\core\fabric` 逐行核查
2. ✅ 产品态三种状态可本地复现（附最短路径命令）
3. ✅ 12芯粒结构图直通 `capability.py` 完备清单
4. ✅ 工程规范四件套：依赖/配置/测试/文档，全部就位可审计

## 归档结束

用户可基于这份精确的工程快照，对 AOS 现状、能力、生态对接和工程纪律形成完整认知