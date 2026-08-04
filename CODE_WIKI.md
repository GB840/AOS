# AOS 项目完整 Code Wiki 文档

> **版本**: v5.0 | **生成日期**: 2026-08-04 | **代码覆盖**: 基于源码静态阅读编写（非运行时全量执行）
> **最后核对 commit**: f2ba74a（Tier0 方言语音 CompanionVoice 收口）
> **诚实分级**: 标注 ②=代码+单测实证；③=真 LLM 端到端；未标=静态阅读，不等同运行验证。

> **母纲护栏（本 Wiki 所有描述须服从此宪法，冲突以母纲为准）**：
> 1. **本地优先·数据自持**（原则1）：默认路由已翻转为「本地优先→云端兜底」，云端仅作不可达时的兜底，不挡任何功能。
> 2. **方言平等**（原则7）：语音层普通话/方言一视同仁，Tier0 已落地 DialectASR + CompanionVoice。
> 3. **不收割**：断网全跑 / 数据可出走 / 不挡功能 / 不抽成 四条硬检验；商业化只卖「省事」（托管/模板/私有化/SLA），不卖「准入」，开源核心永久免费且完整。
> 4. **白盒才可进化 / 可验证即真理**：任何「已完成」声明须有真实证据，禁用内存实现冒充真实后端。

---

## 目录

1. [项目总览](#1-项目总览)
2. [整体架构设计](#2-整体架构设计)
3. [目录结构详解](#3-目录结构详解)
4. [核心模块 - 内核层 (Kernel)](#4-核心模块---内核层-kernel)
5. [核心模块 - Fabric 适配层](#5-核心模块---fabric-适配层)
6. [核心模块 - API 服务层](#6-核心模块---api-服务层)
7. [业务层 - DeerFlow / Hermes / Execution](#7-业务层---deerflow--hermes--execution)
8. [技能生态层 (Skills)](#8-技能生态层-skills)
9. [辅助与外围模块](#9-辅助与外围模块)
10. [配置与运行方式](#10-配置与运行方式)
11. [依赖管理](#11-依赖管理)
12. [测试体系](#12-测试体系)
13. [关键文件速查表](#13-关键文件速查表)

---

## 1. 项目总览

### 1.1 项目定位

**AOS（Agentic OS / 能体操作系统）v5.0** 是一个面向智能体时代的操作系统级平台，核心理念是：

- **不做竞争性产品，做组合器**：AOS 不自研 LLM/Agent 引擎，而是通过开放的 Fabric 适配层把市面上所有优秀的开源智能体引擎（Hermes、DeerFlow、OpenClaw、AG2 等）统一接进来，按能力（Capability）发现、调度、编排。
- **小而精 3 天 MVP 原则**：极简内核、零第三方依赖、插件化架构、诚实降级。
- **生命体 OS 七层层级**：从 L0 人本生命状态到 L7 分形集群，逐层递进自洽。

### 1.2 三大核心设计原则

| 原则 | 内涵 |
|------|------|
| **内核零依赖** | `src/kernel/` 除标准库外不 import 任何第三方包，重型依赖全部通过 Fabric 适配层在 `wiring.py` 懒加载注入 |
| **能力即路由，权限即边界** | 引擎按 `Capability`（能力枚举）注册，而非按项目名；调用方只声明「我需要什么能力」，FabricRegistry 按档位+策略选最优供给方 |
| **诚实+量化置信** | 任何降级、缺失、未知都如实标注（`unknown` / `available:False`），绝不以内存实现冒充真实后端；所有判断都附量化依据与置信度 |

### 1.3 生命体 OS 七层架构

```
L7 分形粒子集群 (Fractal Particles)
   └─ 粒子类型: SENSOR / WORKER / GUARDIAN / ARCHIVIST
   └─ 派生约束: MAX_GEN代数 / MAX_SIBLINGS兄弟 / QUOTA_DECAY配额衰减
   └─ 冲突协调: 租约三阶段协议

L6 虚实交互闭环 (Interact)
   └─ EmergencyBrake: 三级急停 NONE→SOFT→HARD→FULL
   └─ HumanCausalSim: 人本六维因果仿真
   └─ PerceptionGateway: 感知六步清洗（限流/去重/脱敏/注入检测/定信/分发）

L5 演进试错 (Evolve)
   └─ EvolveEngine: A/B测试+优化提案
   └─ MirrorBranch: 影子流量对照闸门（Z检验 + 宪法红线否决）

L4 精神价值层 (Spirit/Soul)
   └─ DatongIndex: 多样性/公平性/共识度/无害性
   └─ CivilizationMirror: 文明级变更沙盘预演
   └─ DialecticRegulator: 三档双向思辨

L3 价值排序 (ValueHierarchy)
   └─ 默认: 安全 > 准确 > 速度 > 成本

L2 动态平衡 (Homeostasis/LifeState)
   └─ LifeState: 能量/情绪/专注/负债四维持衡
   └─ Homeostasis: 负反馈闭环调控

L1 肉体感知 (Body/HAL/PhyBus)
   └─ HAL: 硬件抽象层统一指令集(compute/sense/actuate/render/query/reset/sleep/wake)
   └─ PhyBus: 安全通信总线(QoS/背压/安全联锁/审计)

L0 人本生命状态 (L0 Human-Centric)
   └─ 六维: 时间/注意力/情绪/金钱/关系/自主权
```

---

## 2. 整体架构设计

### 2.1 系统分层架构图

```
┌───────────────────────────────────────────────────────────────────┐
│                        用户界面层 (Web)                              │
│  Streamlit 控制台 / Next.js Admin/Tenant / 门户门户               │
├───────────────────────────────────────────────────────────────────┤
│                      API 网关层 (src/api)                           │
│  FastAPI + 安全中间件(HTTPS/CSP/HSTS/限流/JWT/APIKey) + 统一网关    │
│  /web→Streamlit  /openclaw→OpenClaw  /deerflow→DeerFlow            │
├───────────────────────────────────────────────────────────────────┤
│                   业务编排层 (src/core + src/*)                     │
│  UnifiedBrain / LEMON / SwarmFlow / DanchuangOS / Autopilot        │
│  WorkflowRunner / CodeRefinery / CodeTeam                          │
├───────────────────────────────────────────────────────────────────┤
│                Fabric 适配枢纽层 (src/core/fabric)                 │
│  BaseAgentAdapter ◄── 40+ 适配器(OpenClaw/LiteLLM/Mem0/...)         │
│  FabricRegistry ── 能力发现 + 5种路由策略 + 档位级联                │
│  ResilienceBus ── 熔断/自愈/蒸馏闭环                                │
│  OrchestrationChiplet ── 工作流堆叠 + 审核闸门 + 上下文工程          │
│  A2UI ── 声明式UI协议 18组件白名单                                   │
├───────────────────────────────────────────────────────────────────┤
│                  内核层 (src/kernel)                                │
│  AOSKernel (三职责): 生命周期 / 消息路由 / 权限治理                 │
│  Immunity (免疫): 熔断 + 自愈                                       │
│  Evolution (进化): DNA + 变异 + 适应度 + 蒸馏                      │
│  Memory (记忆): 四层阶梯(LanceDB/DuckDB) + 压缩 + 蒸馏 + 生命周期  │
│  HippoScroll: 多模态可信记忆 + 证据链 + 元认知巡逻                  │
│  Compliance (合规): 宪法审查 + 策略引擎 + 审计追踪                   │
│  Desire (自主): 好奇驱动的目标生成器                                │
│  Ecology (生态): 资源经济 + 自然选择 + 共生检测                     │
│  Danchuang (单创): OPC数字组织 + 目标调度 + Crew协作 + 多租户        │
├───────────────────────────────────────────────────────────────────┤
│                  数据存储层                                          │
│  SQLite / PostgreSQL (状态)  LanceDB (L4传承+分支)  DuckDB (L1统计)  │
│  Chroma / Mem0 / LightRAG / Cognee (语义记忆)                       │
│  JSONL (审批/Pulse/上下文/路由结果)                                 │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 关键依赖链（核心调用关系）

```
API 入口:
  /api/chat
     → chat_routing.select_chat_backends()
       ├─ [默认] FabricHub.chat()  [inference.llm 芯粒 → 本地优先→云端兜底]
       └─ [兜底]   AOSKernel.run_agent() → mistralrs 本地推理

  /api/autopilot/run
     → Autopilot (五阶段: 意图→环境探测→多方案→执行/预览→多平台发布)
       └─ 每步: FabricHub.route(capability) → 结果入 Pulse → Evolve 优化

  /danchuang/*
     → DanchuangOS.core
       ├─ StartupEngine (目标→项目→里程碑→周→日工单)
       ├─ OPCRoles (五岗: 产品RD/市场调研/内容营销/客服/财务)
       ├─ CrewOrchestrator (CrewAI 协作)
       └─ TenantManager (多租户 + BYOK + SaaS隔离)

工作流执行链:
  Studio WorkflowRunner
     → Workflow.to_chiplet_steps()
       → OrchestrationChiplet.invoke()
         → [每步前] ReviewGate.should_review() / resolve()
         → [每步中] FabricRegistry.providers_for(cap) → route() → ResilienceBus
         → [每步后] ContextManager.add_step() → 超阈值compact()
         → [完后]   PulseCollector.record_run() → CostTracker + EvolveEngine
```

---

## 3. 目录结构详解

### 3.1 顶层目录

| 目录/文件 | 职责 | 关键内容 |
|-----------|------|----------|
| `src/kernel/` | **核心内核层**（零第三方依赖） | 50+ 根模块 + 20+ 子模块 |
| `src/core/` | **Fabric 适配层** | 引擎适配契约、注册路由、自愈总线、A2UI协议 |
| `src/api/` | **FastAPI 服务层** | 24 个 API 模块、安全中间件、统一网关 |
| `src/deerflow/` | DeerFlow 2.x 桥接层 | 调度器、技能提供者、子智能体、沙箱桥 |
| `src/hermes/` | Hermes Agent 桥接层 | 自进化技能、反思引擎、记忆生命周期 |
| `src/execution/` | 通用执行层 | 沙箱执行、任务运行、工具调用、工作区 |
| `src/skills/` | 技能生态层 | manifest.json + 200+ OPC 岗位角色技能 |
| `src/subagents/` | 子智能体注册表 | IMA/Lobster/Loop/Meeting/Pixelle/Ruflo/Skill/Uitars/Vimax |
| `src/memory/` | 基础记忆层 | 记忆CRUD + 生命周期管理 |
| `src/router/` | LLM 任务路由 | 按任务类型选最优模型（本地/云端） |
| `src/lifeform/` | 生命体高级形态 | 分形全息智能体、自进化引擎、世界模型 |
| `src/meta_orchestrator/` | 元编排层 | 跨工作流级任务编排 |
| `src/aos_mcp/` | MCP 协议层 | JSON-RPC 2.0 + stdio transport 服务端 |
| `src/voice/` | 语音 I/O | ASR + TTS 封装 |
| `src/web/` | Web 控制台 | Streamlit 前端 |
| `src/utils/` | 工具集 | 配置/异常/密钥/LlamaOverride/脱敏 |
| `src/compliance/` | 合规审计 | 审计、身份、追踪 |
| `src/common/` | 通用 proto | gRPC 生成的 pb2 |
| `configs/` | 配置文件 | global.yaml、postgres init |
| `config/hermes/` | Hermes 配置 | config.yaml / SOUL.md / USER.md |
| `docs/` | 设计文档 | 架构/路线/审计/评价 50+ 份 |
| `tests/` | 测试套件 | 200+ 测试文件 |
| `scripts/` | 运维脚本 | 启动/停止/探活/安全扫描/量化脚本 |
| `examples/` | 使用示例 | chat_bot / code_review / pdf_qa / CLI 脚本 |
| `proto/` | protobuf 定义 | mcp_control_plane / meta_orchestrator |
| `third_party/` | 第三方集成 | img2threejs |
| `workers/` | 独立 Worker | code_worker / desktop_worker / office_worker |
| `web/` | 前端工程 | Next.js Admin/Tenant / Studio / Refinery / Bidding |
| `pyproject.toml` | **依赖声明唯一真相** | MIT, Python≥3.11 |
| `requirements.txt` | 向后兼容 | 已废弃，指向 pyproject |

---

## 4. 核心模块 - 内核层 (Kernel)

### 4.1 内核三职责（AOSKernel）

文件: [kernel.py](file:///d:/AOS/src/kernel/kernel.py)

```
AOSKernel.__init__()
  ├─ 生命周期: create_agent() / run_agent() / destroy_agent()
  ├─ 消息路由: send_message() + pub/sub Events 总线
  └─ 权限治理: check_capability() + 宪法红线否决
```

### 4.2 内核根目录模块索引（50+）

| 模块 | 类/函数 | 核心职责 |
|------|---------|----------|
| [action_arbiter.py](file:///d:/AOS/src/kernel/action_arbiter.py) | `ActionArbiter` | 三级风险审批（low/mid/high）：物理世界执行永远要人审，宪法优先 |
| [adaptive.py](file:///d:/AOS/src/kernel/adaptive.py) | `AdaptiveCore` | 生命体征+学习闭环反馈，动态调整并发/资源分配 |
| [aos.py](file:///d:/AOS/src/kernel/aos.py) | AOS 高层入口 | 把 kernel + fabric + wiring 组合成可用实例 |
| [auth_bridge.py](file:///d:/AOS/src/kernel/auth_bridge.py) | `AuthBridge` / `AuthProvider` | JWT/APIKey → 内核权限映射，多租户隔离 |
| [autopilot.py](file:///d:/AOS/src/kernel/autopilot.py) | `Autopilot` | 五阶段自主环：意图→探测→方案→执行→发布 |
| [causal.py](file:///d:/AOS/src/kernel/causal.py) | `CausalModel` | 因果世界模型：干预/反事实推理 |
| [causal_experiment.py](file:///d:/AOS/src/kernel/causal_experiment.py) | 因果实验框架 | A/B 测试：随机分配 + 统计显著性 |
| [compliance.py](file:///d:/AOS/src/kernel/compliance.py) | `ContentGuard` / `PolicyEngine` | 宪法审查、策略执行 |
| [confidence.py](file:///d:/AOS/src/kernel/confidence.py) | 三档置信评估 | low/medium/high + 量化依据 |
| [constitution_gaps.py](file:///d:/AOS/src/kernel/constitution_gaps.py) | 宪法缺口追踪 | 方言覆盖、灵魂唯一性度量 |
| [desire.py](file:///d:/AOS/src/kernel/desire.py) | `DesireEngine` | 好奇→认知缺口→维护需求的目标生成器 |
| [dialect_asr.py](file:///d:/AOS/src/kernel/dialect_asr.py) | 方言感知 ASR | 多引擎路由 + 覆盖率报告 |
| [ecology.py](file:///d:/AOS/src/kernel/ecology.py) | `ResourceEconomy` / `NaturalSelection` / `SymbiosisDetector` | 资源预算、淘汰、共生 |
| [events.py](file:///d:/AOS/src/kernel/events.py) | 事件总线 | publish/subscribe + 去抖队列 |
| [evidence_chain.py](file:///d:/AOS/src/kernel/evidence_chain.py) | 证据链追踪 | 记忆/决策的出处可验证 |
| [evolution.py](file:///d:/AOS/src/kernel/evolution.py) | `AgentDNA` / `Breeder` + `FitnessTracker` | DNA 变异 + 适应度追踪 |
| [evolution_distiller.py](file:///d:/AOS/src/kernel/evolution_distiller.py) | 经验蒸馏 | 失败模式→成功模式提炼→路由沉底惩罚 |
| [experience_sharing.py](file:///d:/AOS/src/kernel/experience_sharing.py) | 跨租户匿名经验分享 | 脱敏后共享，失败模式+解决方案 |
| [future.py](file:///d:/AOS/src/kernel/future.py) | 预留接口 | ProtocolAdapter / ComplianceLayer / ModelCapabilityProvider |
| [goal_evolution.py](file:///d:/AOS/src/kernel/goal_evolution.py) | `GoalEvolution` | 目标按成败+年龄升降/搁置/替换 |
| [hippo_scroll.py](file:///d:/AOS/src/kernel/hippo_scroll.py) | HippoScroll 可信记忆 | 多模态、证据节点、元认知巡逻 |
| [homeostasis.py](file:///d:/AOS/src/kernel/homeostasis.py) | `Homeostasis` | 四维负反馈控制 |
| [hotswap.py](file:///d:/AOS/src/kernel/hotswap.py) | `HotSwapManager` | 线程安全插件热替换 |
| [immunity.py](file:///d:/AOS/src/kernel/immunity.py) | `CircuitBreaker` / `SelfHealer` / `FailureMonitor` | 熔断、自愈、故障检测 |
| [interfaces.py](file:///d:/AOS/src/kernel/interfaces.py) | `AgentRuntime` / `MemoryStore` ... | 内核对外抽象接口 |
| [kernel.py](file:///d:/AOS/src/kernel/kernel.py) | `AOSKernel` | 内核根：三职责总入口 |
| [learning_loop.py](file:///d:/AOS/src/kernel/learning_loop.py) | `LearningLoop` | 失败记忆→模式匹配→策略调整 |
| [life_state.py](file:///d:/AOS/src/kernel/life_state.py) | `LifeState` | 能量/情绪/专注/负债四维模型 |
| [live.py](file:///d:/AOS/src/kernel/live.py) | `LiveEvolutionEngine` | 端到端群体进化：初始化→执行→选优→繁殖→自愈 |
| [memory_compression.py](file:///d:/AOS/src/kernel/memory_compression.py) | `MemoryCompressor` | 自编码器压缩（仅 numpy 依赖） |
| [memory_control.py](file:///d:/AOS/src/kernel/memory_control.py) | `MemoryControlStore` | 用户可干预的记忆读写控制 |
| [memory_distiller.py](file:///d:/AOS/src/kernel/memory_distiller.py) | `MemoryDistiller` | 大量短期记忆→少量高价值模式 |
| [memory_lifecycle.py](file:///d:/AOS/src/kernel/memory_lifecycle.py) | `MemoryLifecycleManager` | TTL+热度→四层分级(eternal/important/normal/archived) |
| [metacognition.py](file:///d:/AOS/src/kernel/metacognition.py) | `MetacognitivePatrol` | 巡逻自检：记忆一致性/冲突/冗余 |
| [opc_loop.py](file:///d:/AOS/src/kernel/opc_loop.py) | `OPCBusinessLoop` | 单兵创业六阶段闭环 + Meta-Trace 复盘 |
| [resource_autonomy.py](file:///d:/AOS/src/kernel/resource_autonomy.py) | `ResourceAutonomy` | 能量/负债驱动的自我资源治理 |
| [rhythm.py](file:///d:/AOS/src/kernel/rhythm.py) | `RhythmScheduler` | 活跃/休息/深睡/复盘四节律 |
| [run_state_store.py](file:///d:/AOS/src/kernel/run_state_store.py) | `RunStateStore` | SQLite 持久化 autopilot 断点 |
| [self_harness.py](file:///d:/AOS/src/kernel/self_harness.py) | `SelfHarness` | 自检：适配器探活+EVAL冒烟+存储可写 |
| [semantic_state.py](file:///d:/AOS/src/kernel/semantic_state.py) | `SemanticStateStore` | 线程安全 JSONL 共享语义记忆 |
| [skill_registry.py](file:///d:/AOS/src/kernel/skill_registry.py) | 技能读取索引 | manifest.json → 按能力发现 |
| [skills_bridge.py](file:///d:/AOS/src/kernel/skills_bridge.py) | 技能桥接 | AOS skills → kernel SkillBus → MCP/direct 调用 |
| [soul_sync.py](file:///d:/AOS/src/kernel/soul_sync.py) | `SoulSync` | 跨设备灵魂同步，数据主权 |
| [sovereignty.py](file:///d:/AOS/src/kernel/sovereignty.py) | `export_all()` | 一键用户数据导出（所有JSONL/SQLite/向量） |
| [system.py](file:///d:/AOS/src/kernel/system.py) | 系统级启动/停止 | wiring 初始化入口 |
| [types.py](file:///d:/AOS/src/kernel/types.py) | `AgentSpec` / `AgentInstance` / `Response` 等 | 内核所有 dataclass/Enum 定义 |
| [v5_bridge.py](file:///d:/AOS/src/kernel/v5_bridge.py) | v1→v5 桥 | API路由/JWT/技能/MCP/WebConsole 迁移 |
| [value_ledger.py](file:///d:/AOS/src/kernel/value_ledger.py) | `ValueLedger` | 用户创建价值追踪 + 反虹吸检查 |
| [versioning.py](file:///d:/AOS/src/kernel/versioning.py) | 语义版本 | 多版本共存 + 升级迁移 |
| [video_maker.py](file:///d:/AOS/src/kernel/video_maker.py) | 本地视频生成流水线 | edge-tts + PIL + ffmpeg + 字幕 |
| [wiring.py](file:///d:/AOS/src/kernel/wiring.py) | **所有真实依赖的注入点** | 懒加载 fabric 适配器/插件/重型库 |

### 4.3 Kernel 子模块详解

#### 4.3.1 approval/ 审批

| 文件 | 类 | 职责 |
|------|----|------|
| [approval_store.py](file:///d:/AOS/src/kernel/approval/approval_store.py) | `ApprovalStore` | JSONL 单例审批队列：create/approve/reject/list/expire，TTL 防积压 |
| [review_gate.py](file:///d:/AOS/src/kernel/approval/review_gate.py) | `ReviewGate` | 步骤级「封驳」：敏感能力(code.generate/shell.exec/file.write等)自动拦→建 pending→准后 resume |

#### 4.3.2 body/ 肉体层

| 文件 | 类 | 职责 |
|------|----|------|
| [hal.py](file:///d:/AOS/src/kernel/body/hal.py) | 统一指令集 | `compute/sense/actuate/render/query/reset/sleep/wake`，危险动作有安全联锁 |
| [phy_bus.py](file:///d:/AOS/src/kernel/body/phy_bus.py) | `PhysicalBus` | QoS 背压 + 安全联锁（写/执行/不可逆需审批）+ 审计日志 |

#### 4.3.3 context/ 上下文工程

| 文件 | 类 | 职责 |
|------|----|------|
| [context_manager.py](file:///d:/AOS/src/kernel/context/context_manager.py) | `ContextManager` | 四优先级（critical/high/normal/low），超阈值压缩：保最新N步+失败步，摘要其余，持久化 JSONL |

#### 4.3.4 danchuang/ 单创 OS

| 子目录 | 核心 | 职责 |
|--------|------|------|
| `core.py` | `DanchuangOS` | 总入口：OPC + GoalScheduling + Crew + Playbook + MultiTenant + Admin API |
| `engine/startup_engine.py` | `StartupEngine` | 总目标→项目→里程碑→周任务→日工单；每日运行+复盘+策略调 |
| `engine/task_scheduler.py` | `TaskScheduler` | 工单分配、超时重分配、进度跟踪 |
| `engine/goal_decomposer.py` | `GoalDecomposer` | 目标逐层拆解（目标→P→M→W→D） |
| `engine/crew_orchestrator.py` | CrewAI 协作 | 多角色 Crew 编排 |
| `engine/playbook_library.py` | 剧本库 | 可复用工作流模板 |
| `opc/roles.py` | 5 岗角色定义 | 产品RD/市场调研/内容营销/客服/财务，各带能力+工具+工作流模板 |
| `opc/agency_registry.py` | 岗位注册表 | 200+ agency_roles 技能映射 |
| `llm/provider.py` | LLM 提供者 | LangChain 适配 + BYOK 租户 Key 注入 |
| `tenant/tenant_manager.py` | 多租户 | 租户创建/APIKey/配额 |
| `tenant/byok.py` | `ByokStore` | 租户自带 Key：env 覆盖注入推理平面 |
| `tenant/isolation.py` | SaaS 隔离 | 数据/资源/权限硬隔离 |
| `integrations/crewai_engine.py` | CrewAI 真实引擎桥接 |
| `integrations/langgraph_engine.py` | LangGraph 真实引擎桥接 |

#### 4.3.5 eval/ 评估

| 文件 | 类 | 职责 |
|------|----|------|
| [eval_harness.py](file:///d:/AOS/src/kernel/eval/eval_harness.py) | `EvalHarness` | 轨迹评分（工具正确性/路径一致性/步数效率）+ 回归测试 + 基线对比 |

#### 4.3.6 evolve/ 演进试错

| 文件 | 类 | 职责 |
|------|----|------|
| [evolve_engine.py](file:///d:/AOS/src/kernel/evolve/evolve_engine.py) | `EvolveEngine` | A/B 测试 + 优化提案（prompt_tune / step_retry / add_fallback 等） |
| [mirror_branch.py](file:///d:/AOS/src/kernel/evolve/mirror_branch.py) | `MirrorBranch` | **影子闸门四纪律**：①影子不出门 ②样本不够不下结论（双比例z检验）③宪法伤害=永久封禁 ④不可逆需人审 |

#### 4.3.7 fractal/ 分形粒子

| 文件 | 类 | 职责 |
|------|----|------|
| [particles.py](file:///d:/AOS/src/kernel/fractal/particles.py) | 4 粒子类型 | SENSOR(感知) / WORKER(执行) / GUARDIAN(守卫) / ARCHIVIST(归档) |
| [spawner.py](file:///d:/AOS/src/kernel/fractal/spawner.py) | `FractalSpawner` | 派生约束：MAX_GEN=8代，MAX_SIBLINGS=16兄弟，QUOTA_DECAY=0.7每代衰减 |
| [growth_guard.py](file:///d:/AOS/src/kernel/fractal/growth_guard.py) | `GrowthGuard` | 校验派生合法性，写/联网/花钱需审批 |
| [conflict.py](file:///d:/AOS/src/kernel/fractal/conflict.py) | 三阶段冲突协调 | ①租约②优先级仲裁③升级 |

#### 4.3.8 interact/ 虚实交互

| 文件 | 类 | 职责 |
|------|----|------|
| [emergency_brake.py](file:///d:/AOS/src/kernel/interact/emergency_brake.py) | `EmergencyBrake` | 三级锁存急停 NONE→SOFT→HARD→FULL；死人开关心跳超时→升HARD；HARD以上必须授权人解除 |
| [human_causal_sim.py](file:///d:/AOS/src/kernel/interact/human_causal_sim.py) | `HumanCausalSimulator` | 人本六维因果仿真：时间/注意力/情绪/金钱/关系/自主权，自主权加权 1.8 最重 |
| [perception_gateway.py](file:///d:/AOS/src/kernel/interact/perception_gateway.py) | `PerceptionGateway` | 感知六步清洗：令牌桶限流→指纹去重→PII掩码(身份证/手机/邮箱/银行卡)→注入检测→可信度定信(人1.0/传感器0.9/内网0.85/API0.7/Web0.4/不明0.2)→订阅分发 |

#### 4.3.9 isolation/ 进程隔离

| 文件 | 类 | 职责 |
|------|----|------|
| [subprocess_iso.py](file:///d:/AOS/src/kernel/isolation/subprocess_iso.py) | `SubprocessIsolation` | 独立子进程执行，IPC pipe/TCP；启动/RTT/恢复三闸门；崩溃不影响主核 |
| [worker.py](file:///d:/AOS/src/kernel/isolation/worker.py) | Worker 主循环 | 隔离进程内执行引擎代码 |

#### 4.3.10 layers/ 分层抽象

| 文件 | 类 | 职责 |
|------|----|------|
| [model_gateway_layer.py](file:///d:/AOS/src/kernel/layers/model_gateway_layer.py) | 推理网关层 | 统一 LLM 调用入口 |
| [model_fallback.py](file:///d:/AOS/src/kernel/layers/model_fallback.py) | 级联回退 | 高→中→低模型兜底 |
| [agent_runtime_layer.py](file:///d:/AOS/src/kernel/layers/agent_runtime_layer.py) | 智能体运行时层 | FabricAgentRuntime 薄封装 |
| [mcp_bus_layer.py](file:///d:/AOS/src/kernel/layers/mcp_bus_layer.py) | MCP 总线层 | 跨 MCP 服务发现与调用 |
| [ui_layer.py](file:///d:/AOS/src/kernel/layers/ui_layer.py) | UI 抽象层 | chat_panel / agent_workbench / app_store 多 surface |

#### 4.3.11 plugins/ 插件（真实依赖接线层）

这是 kernel 里**唯一可以 import core.fabric 真实实现**的目录，对内核零依赖原则至关重要：

| 文件 | 类 | 职责 |
|------|----|------|
| [fabric_runtime.py](file:///d:/AOS/src/kernel/plugins/fabric_runtime.py) | `FabricAgentRuntime` | 薄缝：`BaseAgentAdapter → AgentRuntime` 语义映射（v1.0 物种思维接线） |
| [fabric_hub.py](file:///d:/AOS/src/kernel/plugins/fabric_hub.py) | `FabricHub` | **注册中心总枢纽**：注册 40+ 适配器 → route/chat/media → ResilienceBus → 结果归一化 |
| [orchestration_chiplet.py](file:///d:/AOS/src/kernel/plugins/orchestration_chiplet.py) | `OrchestrationChiplet` | **用户态工作流堆叠引擎**：initial+steps[]+parallel_groups；集成 ContextManager + ReviewGate；并行并发用 ThreadPoolExecutor |
| [failure_monitor.py](file:///d:/AOS/src/kernel/plugins/failure_monitor.py) | 14 类失败埋点 | MAST 分类 |
| [code_team.py](file:///d:/AOS/src/kernel/plugins/code_team.py) | `CodeTeamOrchestrator` | 自然语言→多文件代码：架构/编码/测试/质量门 |
| [code_team_adapter.py](file:///d:/AOS/src/kernel/plugins/code_team_adapter.py) | 代码团队 Fabric 适配器 |
| [content_flywheel.py](file:///d:/AOS/src/kernel/plugins/content_flywheel.py) | 内容飞轮 | 检索→分析→剧本→导演→工具→审核→发布 七步 |
| [content_director.py](file:///d:/AOS/src/kernel/plugins/content_director.py) | 内容导演 | 镜头/节奏/一致性 |
| [content_strategy.py](file:///d:/AOS/src/kernel/plugins/content_strategy.py) | 内容策略 | 选题/平台/排期 |
| [ollama_gateway.py](file:///d:/AOS/src/kernel/plugins/ollama_gateway.py) | Ollama 本地模型网关 |
| [litellm_gateway.py](file:///d:/AOS/src/kernel/plugins/litellm_gateway.py) | LiteLLM 统一推理网关 |
| [mistralrs_gateway.py](file:///d:/AOS/src/kernel/plugins/mistralrs_gateway.py) | MistralRS 本地推理（3端口：1234通用/1235编码/1236推理）|
| [agnes_gateway.py](file:///d:/AOS/src/kernel/plugins/agnes_gateway.py) | Agnes 多模态（图/视频）|
| [cloud_gateway.py](file:///d:/AOS/src/kernel/plugins/cloud_gateway.py) | 云端供应商聚合 |
| [composite_gateway.py](file:///d:/AOS/src/kernel/plugins/composite_gateway.py) | 多网关组合 |
| [zhipu_chat.py](file:///d:/AOS/src/kernel/plugins/zhipu_chat.py) | 智谱对话适配器 |
| [ollama_chat.py](file:///d:/AOS/src/kernel/plugins/ollama_chat.py) | Ollama 对话适配器 |
| [mcp_security_gateway.py](file:///d:/AOS/src/kernel/plugins/mcp_security_gateway.py) | MCP 调用安全闸门 |
| [mcp_skill_bus.py](file:///d:/AOS/src/kernel/plugins/mcp_skill_bus.py) | Skills → MCP 工具总线 |
| [opc_roles.py](file:///d:/AOS/src/kernel/plugins/opc_roles.py) | OPC 五岗 Fabric 接线 |
| [openmaic_bridge.py](file:///d:/AOS/src/kernel/plugins/openmaic_bridge.py) | OpenMAIC 互动课堂桥接 |
| [plan_bridge.py](file:///d:/AOS/src/kernel/plugins/plan_bridge.py) | 规划结果→工作流翻译 |
| [repo_agent.py](file:///d:/AOS/src/kernel/plugins/repo_agent.py) | 仓库级代码分析代理 |
| [report_agent.py](file:///d:/AOS/src/kernel/plugins/report_agent.py) | 报告生成代理 |
| [singlechuang.py](file:///d:/AOS/src/kernel/plugins/singlechuang.py) | 单兵创业工作流 |
| [comfyui_adapter.py](file:///d:/AOS/src/kernel/plugins/comfyui_adapter.py) | ComfyUI 生图适配器 |
| [extension.py](file:///d:/AOS/src/kernel/plugins/extension.py) | 扩展点基类 |

#### 4.3.12 pulse/ 心跳与可观测

| 文件 | 类 | 职责 |
|------|----|------|
| [cost_tracker.py](file:///d:/AOS/src/kernel/pulse/cost_tracker.py) | `CostTracker` | 模型定价表 + 每请求成本估算 + 阈值告警 + 按模型/工作流/用户/智能体分拆 |
| [pulse_collector.py](file:///d:/AOS/src/kernel/pulse/pulse_collector.py) | `PulseCollector` | 事件缓冲(100条刷盘)、成功率、耗时统计、token→CostTracker 自动桥接 |

#### 4.3.13 refinery/ 代码炼化

| 文件 | 类 | 职责 |
|------|----|------|
| [refinery_engine.py](file:///d:/AOS/src/kernel/refinery/refinery_engine.py) | `CodeRefineryEngine` | 五阶炼化：沙箱加载→质量分析→生成提案→低风险自动应用→测试验证→报告 |
| `project_sandbox.py` | `ProjectSandbox` | 目录快照+回滚 |
| `code_analyzer.py` | `CodeAnalyzer` | AST 静态分析+质量评分 |
| `code_optimizer.py` | `CodeOptimizer` | 优化提案生成，风险分级 |
| `test_runner.py` | `TestRunner` | 测试执行+覆盖率 |
| `evolution_loop.py` | 进化闭环 | 多轮迭代优化 |
| `incremental_analyzer.py` | 增量分析 | 只重算变更文件 |

#### 4.3.14 soul/ 灵魂层

| 文件 | 类 | 职责 |
|------|----|------|
| [value_hierarchy.py](file:///d:/AOS/src/kernel/soul/value_hierarchy.py) | `ValueHierarchy` | 默认序：安全>准确>速度>成本，硬约束（safety）不可被低优先级越过 |
| [dialectic.py](file:///d:/AOS/src/kernel/soul/dialectic.py) | `DialecticRegulator` | 三档双向思辨（low/mid/high 生成 1/2/3 个反向论证） |
| `emotion_state.py` | 情绪状态模型 | 情绪向量 + 情绪漂移 |
| `lineage.py` | 灵魂世系 | 每次进化的血统追踪 |
| `tree_ring.py` | 年轮记忆 | 历史关键节点树状存档 |

#### 4.3.15 spirit/ 精神层

| 文件 | 类 | 职责 |
|------|----|------|
| [datong.py](file:///d:/AOS/src/kernel/spirit/datong.py) | `DatongIndex` / `CivilizationMirror` | 大同指数四分量(多样性熵/1-基尼/共识度/无害性)；变更先深拷贝沙盘预演，无害性下降=直接拒绝 |
| `consensus.py` | 共识提案 | 提案+投票+多数决 |
| `mentorship.py` | 导师制度 | 老智能体带新智能体 |
| `values_market.py` | 价值市场 | 价值观供需动态调整 |

#### 4.3.16 store/ 记忆存储

| 文件 | 类 | 职责 |
|------|----|------|
| [memory_ladder.py](file:///d:/AOS/src/kernel/store/memory_ladder.py) | 四层阶梯 | L1 Instant (DuckDB+Lance扩展版本血缘) / L2 Working (TriviumDB→诚实降级) / L3 Longterm (Chroma/Mem0) / L4 Heritage (LanceDB 支持 Git 式分支)；全部 LazyExternalTier 缺失→诚实报 ImportError 不冒充 |

#### 4.3.17 studio/ 工作流工作台

| 文件 | 类 | 职责 |
|------|----|------|
| `workflow_models.py` | `Workflow` / `WorkflowRun` | 工作流/运行 数据结构 |
| `workflow_store.py` | `WorkflowStore` | 工作流 CRUD 持久化 |
| `workflow_runner.py` | `WorkflowRunner` | 翻译成 OrchestrationChiplet steps → 执行 → resume(审批通过后) → Pulse上报 |
| `template_market.py` | 模板市场 | 可复用工作流模板 |

#### 4.3.18 hub/ 智能体枢纽

| 文件 | 类 | 职责 |
|------|----|------|
| [hub_store.py](file:///d:/AOS/src/kernel/hub/hub_store.py) | `AgentHub` | 公共工作流浏览/搜索/评分/一键部署，使用量+反馈 |

#### 4.3.19 industry/ 行业模板

| 子目录 | 职责 |
|--------|------|
| `restaurant/` | 烧烤店 SaaS：内容营销/客服/数据闭环/操作员 |

#### 4.3.20 monitoring/ 服务质量

| 文件 | 类 | 职责 |
|------|----|------|
| [sla.py](file:///d:/AOS/src/kernel/monitoring/sla.py) | `SLAMonitor` | API 延迟/可用性/错误率 SLA 追踪 + 异常检测 + 报告 |

---

## 5. 核心模块 - Fabric 适配层

### 5.1 核心契约（BaseAgentAdapter）

文件: [adapter.py](file:///d:/AOS/src/core/fabric/adapter.py)

```python
class BaseAgentAdapter(ABC):
    @property
    @abstractmethod
    def engine_id: str          # 稳定标识 e.g. "litellm"

    @abstractmethod
    def advertise_capabilities() -> list[Capability]  # 能力声明

    @abstractmethod
    def invoke(req: InvokeRequest) -> InvokeResult   # 执行能力

    @abstractmethod
    def health() -> bool                              # 存活探测

    def tier() -> str          # 档位 high/medium/low（读 ENGINE_TIER 表）
    def supported_protocols() -> list[str]   # MCP/A2A/ACP
```

统一请求/响应契约：
- `InvokeRequest(capability, payload, trace_id, tier)`
- `InvokeResult(ok, data, error, engine_id)` —— **engine_id 回填让调用方知道到底谁跑的**

关键工具函数：
- `extract_text(out)`: 把任意上游输出投影成可读文本（content/reply/images/results/urls 七路扫描去重）
- `extract_media_url(out)`: 四态 media 契约归一：url→image_url→data[].url→output→output_path
- `normalize_media_data(data)`: 同时补三键，消费方只读 `url` 即可

### 5.2 能力分类学（Capability 枚举）

文件: [capability.py](file:///d:/AOS/src/core/fabric/capability.py)

**6 大类 50+ 种能力**（节选）：

| 类别 | 能力 |
|------|------|
| **通道** | CHANNEL_ACCESS, CHANNEL_SEND, GROUP_ORCHESTRATION |
| **认知** | SELF_IMPROVEMENT, LONG_HORIZON, PLANNING, REASONING |
| **推理** | INFERENCE_LLM (统一LLM), INFERENCE_LNN (液态时间网络低维序列) |
| **媒体** | MEDIA_IMAGE, MEDIA_VIDEO, MEDIA_3D, MEDIA_3D_RECONSTRUCT(img→程序化Three.js), MEDIA_PROCESS(火山100+后期) |
| **记忆** | MEMORY_PERSISTENT, MEMORY_EPISODIC, MEMORY_SEMANTIC, MEMORY_KNOWLEDGE |
| **行动** | CODE_EXECUTION, CODE_GENERATE, FILE_ACCESS, ACI, TOOL_USE |
| **搜索** | WEB_SEARCH, WEB_FETCH, WEB_CRAWL (crawl4ai) |
| **语音** | VOICE_STT, VOICE_TTS, VOICE_OMNI (MiniCPM-o 端到端全双工) |
| **视觉** | VISION_UNDERSTAND (VLM 读截图/文档/界面) |
| **内容** | 10 项：PRODUCE / FEEDBACK / SENTIMENT / NEED_MINING / PUBLISH / DISTRIBUTE / OPTIMIZE / REFINE / AB_TEST / MARKETING_VIDEO / SHORT_DRAMA |
| **安全** | SECURITY_AUDIT (自检漏洞) |
| **炼化** | CODE_REFINE |
| **逆向** | RE_IDA (IDA Pro MCP) |
| **教育** | EDU_COURSE_GEN |
| **编排** | WORKFLOW_EXECUTE (OrchestrationChiplet) |
| **BENCH** | BENCH_PING, BENCH_ISOLATE (合成探针) |

**三级档位（路由第一维度）**：
- HIGH: 本地重算力/零成本/强隐私
- MEDIUM: 云端/平衡
- LOW: 边缘/兜底

### 5.3 FabricRegistry 注册与路由

文件: [registry.py](file:///d:/AOS/src/core/fabric/registry.py)

**路由维度（级联顺序）**：
1. **档位优先**：TIER_AUTO 时从 HIGH→MEDIUM→LOW 级联（默认策略）
2. **同档次级策略**（5 种）：
   - `preference`：默认，读 PROVIDER_PREFERENCE 表（本地优先、云端兜底，母纲原则1；AOS_ROUTE_POLICY=cloud_first 可显式翻回云端优先）
   - `cost`：成本套利（Auriko 内核）
   - `latency`：延迟优先
   - `quality`：质量优先
   - `learned`：用 RoutePredictor 预测成功概率

3. **白盒进化闭环·消费端**：启动即加载 `distilled_memory.jsonl`，对提炼出来「成功率<阈值」的 (能力,引擎) 对施加软惩罚——仍可做兜底，不硬阻断。

### 5.4 Resilience 与 ResilienceBus

文件: [resilience.py](file:///d:/AOS/src/core/fabric/resilience.py)、[resilience_bus.py](file:///d:/AOS/src/core/fabric/resilience_bus.py)

| 原语 | 用途 |
|------|------|
| `guarded_import(name, timeout)` | **超时线程守卫导入**：重型依赖(autogen 180s/litellm 30s)卡死不拖垮 import 链 |
| `SafeImport` (描述符) | 类属性访问时才 guarded_import，永远不阻塞 |
| `prewarm(names)` | 后台预热线程批量 import 重依赖 |
| `degrade(name, reason)` | 统一降级标记（看板可见） |

**ResilienceBus 闭环链路**：
```
route() 调 should_skip(eid)?
  → No  → 尝试引擎 → on_outcome(eid, ok, err)
                           ├─ 失败→熔断器计数→OPEN时→下次跳过→冷却后半开探测
                           ├─ 成功→半开→达阈值→CLOSE
                           ├─ 失败→失败监控埋点
                           └─ 成功→蒸馏器记录→越用越准
```
参数：连续 3 次失败→熔断（默认），冷却 30s 半开，2 次连续成功→关。

### 5.5 A2UI 声明式 UI 协议

文件: [a2ui.py](file:///d:/AOS/src/core/fabric/a2ui.py)

- **v0.9 basic catalog**：18 组件白名单（Text/Image/Icon/Video/AudioPlayer/Row/Column/List/Card/Tabs/Modal/Divider/Button/TextField/CheckBox/ChoicePicker/Slider/DateTimeInput）
- **安全模型**：未知组件丢弃、所有文本 html.escape、图片 scheme 限 http(s)/相对路径/data:image/*;base64
- **数据绑定**：`lit(value)` 字面量 / `ref(path)` JSON Pointer
- **HTML 渲染器**：`render_html()` 纯标准库零依赖

### 5.6 其他 Fabric 模块

| 文件 | 职责 |
|------|------|
| `route_runtime.py` | 启动即构建 learned 策略：predictor + outcome_store + distilled 加载 |
| `route_predictor.py` | 路由预测模型：(能力,引擎)→成功概率，训练→落盘→重训阈值=8条 |
| `route_outcome_store.py` | JSONL 结果存储，供 predictor 训练 |
| `tool_call_repair.py` | LLM tool_call 语法修复（JSON 截断/逗号/引号错误） |
| `intent_skill_router.py` | OpenHarmony 小艺 HMAF 风格：「意图即服务 + Skill 化 + MCP兼容」原型 |
| `protocols.py` | A2A/ACP/MCP 协议适配 |
| `handoff.py` | 智能体交接（上下文+状态转移） |
| `companion.py` | 陪伴式伴侣模式 |
| `persona.py` | 人设加载/切换 |
| `voice_chiplet.py` / `voice_wake.py` | 语音芯粒 + 唤醒词 |
| `chiplet_sandbox.py` | 芯粒级沙箱隔离 |
| `trace_store.py` | 调用轨迹追踪 |
| `http_server.py` | HTTP 服务内核 |

### 5.7 40+ 真实适配器清单（adapters/）

| 适配器 | engine_id | 能力 |
|--------|-----------|------|
| `litellm_adapter.py` | litellm | **INFERENCE_LLM**（统一路由 100+ 模型） |
| `openclaw_adapter.py` | openclaw | LLM_GATEWAY |
| `agnes_adapter.py` | agnes | MEDIA_IMAGE / MEDIA_VIDEO |
| `mem0_adapter.py` | mem0 | MEMORY_SEMANTIC（已接真实 mem0，支持双域） |
| `lightrag_adapter.py` (在 skills/) | - | MEMORY_KNOWLEDGE (LightRAG) |
| `cognee_adapter.py` (在 skills/) | - | Graph-RAG |
| `ag2_adapter.py` | ag2 | PLANNING / REASONING / GROUP_ORCHESTRATION |
| `cast_adapter.py` | cast | CONTENT_DISTRIBUTE（多平台发布） |
| `echo_adapter.py` | echo | CONTENT_FEEDBACK（全网回声采集） |
| `refine_adapter.py` | refine | CONTENT_REFINE（润色重生成） |
| `content_marketer_adapter.py` | content_marketer | CONTENT_* 全套 |
| `search_adapter.py` | search | WEB_SEARCH（ddg + anysearch + 国内兜底） |
| `web_fetch_adapter.py` | web-fetch | WEB_FETCH |
| `crawl4ai_adapter.py` | crawl4ai | WEB_CRAWL（爬取→Markdown） |
| `code_execution_adapter.py` | code-exec | CODE_EXECUTION（subprocess 隔离） |
| `file_adapter.py` | file-io | FILE_ACCESS（workspace 内） |
| `aci_browser_adapter.py` | browseruse | ACI（浏览器操作） |
| `codebase_memory_mcp_adapter.py` | cbmmcp | CODE_UNDERSTANDING（tree-sitter 知识图谱） |
| `ida_pro_mcp_adapter.py` | ida | RE_IDA（逆向，localhost-only） |
| `mcp_stdio_adapter.py` / `mcp_client_adapter.py` | mcp/* | 任意 MCP 服务 → Fabric 能力 |
| `media_gen_adapter.py` | media-gen | MEDIA_IMAGE/VIDEO |
| `mediakit_adapter.py` | mediakit | MEDIA_PROCESS（火山后期） |
| `video_maker_adapter.py` | video-maker | MEDIA_VIDEO（本地 edge-tts+ffmpeg） |
| `video_shotcraft_backend.py` | shotcraft | SHORT_DRAMA（短剧） |
| `vlm_adapter.py` | vlm | VISION_UNDERSTAND（读截图/文档） |
| `omni_minicpm_adapter.py` | minicpm-o | VOICE_OMNI（全双工全模态） |
| `stt_adapter.py` | vosk/xfyun | VOICE_STT（vosk 本地/讯飞云端） |
| `tts_adapter.py` / `piper_backend.py` | edge-tts/piper | VOICE_TTS（edge-tts 云端/piper 本地） |
| `localai_backend.py` | localai | 本地 LLM 兼容 |
| `img2threejs_adapter.py` | img2threejs | MEDIA_3D_RECONSTRUCT（图→程序化建模） |
| `threejs_adapter.py` | threejs | MEDIA_3D |
| `remotion_adapter.py` | remotion | MEDIA_VIDEO（Remotion） |
| `refinery_adapter.py` | refinery | CODE_REFINE |
| `security_audit_adapter.py` | sec-audit | SECURITY_AUDIT（防御巡检） |
| `knowmesh_adapter.py` | knowmesh | 知识图谱 |
| `lfm_adapter.py` | lfm | LFM-2 推荐系统 |
| `lnn_adapter.py` | lnn | INFERENCE_LNN（液态时间网络） |
| `constitutional_governor_adapter.py` | governor | 宪法总督 |
| `observability_langfuse_adapter.py` | langfuse | OBSERVABILITY（LangFuse 分布式追踪） |
| `scripts_adapter.py` | scripts | 脚本适配器 |

---

## 6. 核心模块 - API 服务层

### 6.1 入口主文件

文件: [api/main.py](file:///d:/AOS/src/api/main.py) — FastAPI 应用

**启动挂载顺序**（关键）：
1. 中间件：CORS（生产环境拒绝通配符）→ 请求时间 → HTTPS 重定向(生产) → 安全头 → APISecurityMiddleware → 速率限制 → 统一异常处理器
2. 产品飞轮 API（try/except，失败不阻断）
3. 审批、复盘、炼化、创业调度、计费、看板、VLM、视频、记忆控制、自检测、AutoSkill、上下文、回放、EVAL 共 20+ 路由模块
4. 统一网关 `/web` → Streamlit(8501), `/openclaw` → 18789, `/deerflow` → 2026
5. `lifespan` 事件：启动即 initialize_pools + mount_gateway + probe_upstreams + 关闭时 close_pools + close_gateway_session

### 6.2 安全四层防线（security.py）

| 层 | 机制 |
|----|------|
| **传输安全** | HTTPSRedirectMiddleware（生产环境强制）+ HSTS(1年+子域名+preload) |
| **头安全** | SecurityHeadersMiddleware: X-Frame-Options=DENY / CSP(禁止inline脚本/frame-ancestors/object-src) / X-Content-Type-Options / X-XSS-Protection / Referrer-Policy / Permissions-Policy |
| **认证** | JWT RS256（非对称，utils/keystore 管理密钥）+ X-API-Key (bcrypt.hashpw + 恒定时间比较，防止时序攻击) |
| **限流** | RateLimitMiddleware：每分钟 100 次(默认)，超 429 |
| **BYOK** | 读 X-API-Key → TenantManager.validate → ByokStore.resolve_payload → `llm_override` 上下文注入推理平面，用户自己的 Key 优先 |

### 6.3 统一网关（gateway.py）

**三条反向代理 + 探活循环（15秒/次）**：
```
/web/*      → 127.0.0.1:8501 (Streamlit, 不剥前缀)
/openclaw/* → 127.0.0.1:18789 (剥前缀)
/deerflow/* → 127.0.0.1:2026  (剥前缀)
```
- 支持：SSE 字节流透传、WebSocket 代理（Streamlit 要）、3xx Location 改写（补代理前缀）、逐跳头剥离、探活失败→快速 fail-fast 返回 502 + 友好中文提示（不泄内部地址）

### 6.4 24 个 API 路由模块总览

| 模块 | 端点前缀 | 核心功能 |
|------|----------|----------|
| [chat_routing.py](file:///d:/AOS/src/api/chat_routing.py) | /api/chat | 后端链 [默认 fabric→kernel]，可选 brain 兜底；AOS_CHAT_BACKEND 切 |
| `approval_api.py` | /api/approvals | 审批队列 CRUD + 准/驳（接 ApprovalStore） |
| `review_api.py` | /api/review | ReviewGate resume：批准后从持久化 spec 重拉起工作流 |
| `autopilot_api.py` | /api/autopilot | run/status/cancel/断点恢复 |
| `product_flywheel_api.py` | /studio + /hub + /pulse + /evolve | Studio工作流/Hub市场/Pulse统计/Evolve优化 |
| `refinery_api.py` | /api/refinery | 代码炼化任务提交/状态/报告 |
| `danchuang_api.py` | /danchuang | DanchuangOS: set_goal / run_daily / 看板 |
| `startup_api.py` | /api/startup | StartupEngine 目标拆解 |
| `billing_api.py` | /api/billing | 计费/用量/账单（CostTracker） |
| `kanban_api.py` | /api/kanban | 任务看板（Danchuang 工单） |
| `eval_api.py` | /api/eval | EVAL 套件运行 + 报告 |
| `video_api.py` | /api/video | 视频生成/状态/下载 |
| `vlm_api.py` | /api/vlm | 视觉理解上传/查询 |
| `memory_control_api.py` | /api/memory | 记忆 CRUD + 用户干预 |
| `self_harness_api.py` | /api/self-harness | 自检健康报告 |
| `autoskill_api.py` | /api/autoskill | AutoSkill 自动发现+注册技能 |
| `context_api.py` | /api/context | ContextManager 会话上下文查看/压缩 |
| `replay_api.py` | /api/replay | 轨迹回放 Debug |
| `billing_api.py` | 同上 | CostTracker 成本账单 |
| (更多) | | |

---

## 7. 业务层 - DeerFlow / Hermes / Execution

### 7.1 DeerFlow 桥接 (src/deerflow/)

| 文件 | 职责 |
|------|------|
| [scheduler.py](file:///d:/AOS/src/deerflow/scheduler.py) | DeerFlow 2.x 任务调度器：阻塞/SSE 流式、线程管理 |
| [deep_deerflow.py](file:///d:/AOS/src/deerflow/deep_deerflow.py) | **14 层洋葱模型中间件暴露**：sandbox→dangling_tool→guardrail→tool_error→summarization→todo→auto_title→memory→vision→subagent_limit→loop_detection→token_budget→clarification→deferred_tool_filter；还有 Runtime Journal、LangFuse 分布式追踪、会话上下文、事后反思 |
| [path_detect.py](file:///d:/AOS/src/deerflow/path_detect.py) | 自动检测 DeerFlow 源码路径（detect_deerflow_path），检测到则 import 真实现，否则用 AOS 内置实现兜底 |
| [agents_bridge.py](file:///d:/AOS/src/deerflow/agents_bridge.py) | 现有 AOS 智能体 ↔ DeerFlow |
| [skill_provider.py](file:///d:/AOS/src/deerflow/skill_provider.py) | 技能→DeerFlow 工具注册 |
| [guardrails_bridge.py](file:///d:/AOS/src/deerflow/guardrails_bridge.py) | 护栏接入 |
| [sandbox_bridge.py](file:///d:/AOS/src/deerflow/sandbox_bridge.py) | 沙箱执行桥 |
| [subagent_executor.py](file:///d:/AOS/src/deerflow/subagent_executor.py) | DeerFlow 子智能体执行器 |
| `persistence_bridge.py` | 持久化桥（SQLite→DeerFlow） |
| `echo_workflow.py` | Echo 工作流（内容反馈采集） |
| `aos_assets.py` | AOS 特有的资源/提示词 |

### 7.2 Hermes 桥接 (src/hermes/)

| 文件 | 职责 |
|------|------|
| `agent.py` | Hermes AIAgent 包装 |
| [deep_hermes.py](file:///d:/AOS/src/hermes/deep_hermes.py) | **五大能力完整接线**：①自进化技能(/learn 指令、复杂工具调用>5次自动生成技能、热扫描/热加载) ②Nudge反思引擎（每轮后 forked agent 复盘更新记忆+技能） ③记忆生命周期(prefetch→turn→sync MEMORY.md/USER.md) ④ContextEngine(真实 token 计数+压缩阈值管理) ⑤Skill命令（scan/reload/构建调用消息） |

### 7.3 Execution 通用执行层 (src/execution/)

| 文件 | 类 | 职责 |
|------|----|------|
| `sandbox.py` | `SandboxExecutor` | 受信任工作区的命令执行，白名单前缀 + require_confirm=true 双重门 |
| `task_runner.py` | `TaskRunner` | 异步任务队列：提交/查询/取消，结果持久化 |
| `tool_executor.py` | `ToolExecutor` | 工具调用统一入口：能力权限检查 + 审计 + 限流 |
| `workspace.py` | `Workspace` | 工作目录隔离：每个运行/task 有独立文件夹 |

### 7.4 其他业务层

| 目录 | 核心 |
|------|------|
| `src/router/llm_router.py` | LLM 任务→模型路由：按意图分类（聊天/代码/推理/创意/总结）→选本地或云端模型 |
| `src/meta_orchestrator/engine.py` | 元编排：多个工作流级的任务整合 |
| `src/lifeform/` | 高级生命体：分形全息代理、自进化引擎、世界模型引擎 |
| `src/subagents/registry.py` + 9 个 agent | 子智能体注册表：IMA（多模态）、Lobster、Loop Engineering、Meeting、Pixelle、Ruflo、Skill、Uitars、Vimax |

---

## 8. 技能生态层 (Skills)

### 8.1 清单 (manifest.json)

文件: [skills/manifest.json](file:///d:/AOS/src/skills/manifest.json) — **声明式技能清单**

**50+ 已注册技能**（节选）：
- **元技能**：skill-creator（自动创建技能）、find-skills（发现技能）
- **编排**：superpowers（多技能串联）、jstack（全栈开发工作流）
- **设计**：frontend-design、uiux-promax
- **搜索**：duckduckgo-search、searxng、jina-reader
- **工程**：loop-engineering、ollama、vimax、ruflo、uitars、ima、pixelle、loop_engineering
- **记忆**：mem0、lightrag、cognee、codebase_memory (树图)
- **内容**：content_flywheel_skill（七步飞轮）、herdr、lingbot_map
- **推理**：llama_cpp、zvec、no_mistakes、j_stack
- **视频**：video_use、pixelle_video、open_montage
- **语音**：viitor_voice
- **安全**：safe_eval

### 8.2 200+ OPC 岗位角色

`src/skills/agency_roles/` 目录下覆盖：**研发、设计、产品、运营、内容、营销、客服、财务、人事、法务、安全、教育、医疗、数据、硬件、游戏、XR、GIS、嵌入式、区块链、无人机、翻译** 等 200+ 细分角色。每个都是一份独立的技能定义文件（含描述、能力声明、工作流模板）。

### 8.3 引擎/适配器

| 文件 | 职责 |
|------|------|
| `base.py` | 技能基类 BaseSkill |
| `factory.py` | 技能工厂：按 id 构造 |
| `adapter.py` | Skill→FabricHub 适配 |
| `autoskill_engine.py` + `autoskill_agent.py` | AutoSkill 自动发现可封装技能 |
| `bidding_agent.py` | 报价/投标代理 |
| `versioning.py` | 技能版本管理 |
| `composition.py` | 多技能组合器 |
| `sandbox.py` | 技能沙箱 |
| `learning.py` | 技能学习（记忆→技能） |
| `manifest.json` | 上面的声明式清单，被 skill_registry 索引 |

---

## 9. 辅助与外围模块

### 9.1 utils/ 工具集

| 文件 | 核心 |
|------|------|
| [config.py](file:///d:/AOS/src/utils/config.py) | `Config(pydantic_settings.BaseSettings)`：100+ 配置项，读 .env；安全 fail-fast：生产环境缺 API_KEY_HASH/管理员密码/PG密码 直接抛 |
| `exceptions.py` | AOS 异常层级定义 + FastAPI handlers |
| `keystore.py` | JWT RS256 密钥解析：env→.secrets/jwt/→开发期自动生成 |
| `llm_override.py` | 上下文管理器：临时覆写 os.environ LLM/BYOK key，恢复原状 |
| `sanitize.py` | 错误信息脱敏（生产环境）、文件名净化、PII 脱敏 |

### 9.2 compliance/ 合规审计

| 文件 | 类 | 职责 |
|------|----|------|
| `audit.py` | `AuditTrail` | 审计日志：谁/什么动作/目标/结果/时间，不可篡改（追加写） |
| `identity.py` | 身份识别：用户/智能体/租户 身份令牌解析 |
| `trace.py` | 调用链追踪：trace_id 贯穿，分布式环境可关联 |

### 9.3 aos_mcp/ MCP 协议层

| 文件 | 核心 |
|------|------|
| `protocol.py` | `MCPProtocol`（JSON-RPC 2.0）、`MCPMessage` |
| `server.py` | stdio transport 主循环 + 日志抑制(CRITICAL 以上屏蔽) + 干净工具挂载扩展点 |

### 9.4 voice/ 语音层

> **方言平等**（母纲原则7）：普通话与方言一视同仁，Tier0 已落地 `DialectASR` + `CompanionVoice`，断网可跑、无麦克风环境下仍可降级。

| 文件 | 职责 |
|------|------|
| `asr.py` | ASR 多引擎路由：Vosk 本地 / 讯飞云端 / Faster-Whisper，缺失降级 |
| `tts.py` | TTS 多引擎路由：edge-tts 云端 / piper 本地 / Kokoro / XTTS |
| `companion.py` | **Tier0 陪伴语音 `CompanionVoice`**（commit f2ba74a）：听=DialectASR+VoskSTT，说=TTSAdapter（web_speech 兜底）；本地优先·方言平等·断网可跑（② 级实证，③ 端到端需真机麦克风） |
| `dialect_asr.py` | 方言感知 ASR：多引擎路由 + 覆盖率报告（方言平等落地点） |

### 9.5 web/ 前端

| 工程 | 技术 | 职责 |
|------|------|------|
| `src/web/app.py` | Streamlit | **主控制台**：Autopilot 执行 / 工作流 Studio / 看板 / 多模态上传 / 语音对话 / 代码炼化可视化 |
| `web/admin/` | Next.js 14 | 管理后台：租户管理 / 权限 / 监控大屏 |
| `web/tenant/` | Next.js 14 | 租户自助台：BYOK 填 Key / 配额 / 我的灵魂 |
| `web/studio/` | 原生 HTML/JS | 工作流 Studio 独立门户 |
| `web/refinery/` | 原生 HTML/JS | 代码炼化结果查看 |
| `web/bidding/` | 原生 HTML | 报价单 CLI 门户 |
| `web/portal.html` | 纯静态 | 统一导航入口 |

---

## 10. 配置与运行方式

### 10.1 关键环境变量（.env.example 参考）

```bash
# ===== 必配（生产）=====
AOS_APP_ENV=production
AOS_ADMIN_USERNAME=admin
AOS_ADMIN_PASSWORD=强随机
AOS_API_KEY_HASH=$2b$12$...  # bcrypt 哈希后
ALLOWED_ORIGINS=https://aos.example.com

# ===== 推理平面（示例）=====
ZHIPU_API_KEY=你的智谱key
SILICONFLOW_API_KEY=你的硅基流动key
LITELLM_DEFAULT_MODEL=zhipu/glm-4-flash

# ===== 推理路由=====
AOS_CHAT_BACKEND=fabric          # fabric(默认) / kernel / brain
AOS_ROUTE_STRATEGY=learned       # learned / preference / cost / latency / quality

# ===== 本地模型（MistralRS 三端口）=====
MISTRALRS_MODEL_GENERAL=/path/to/MiniCPM5-1B
MISTRALRS_MODEL_CODING=/path/to/Qwen2.5-Coder-3B
MISTRALRS_MODEL_REASONING=/path/to/DeepSeek-R1-1.5B

# ===== 数据后端=====
STATE_BACKEND=sqlite              # sqlite(个人) / postgres(团队)
POSTGRES_HOST=localhost POSTGRES_DB=aos

# ===== 安全开关=====
SANDBOX_API_ENABLED=false
SANDBOX_REQUIRE_CONFIRM=true
```

### 10.2 启动脚本速查

| 目标 | 命令 |
|------|------|
| **一键启动所有（推荐 Windows）** | `.\scripts\start_aos.ps1` 或 `start.bat` |
| 仅 API 服务 (8000) | `uvicorn api.main:app --host 0.0.0.0 --port 8000` |
| 仅 Web 控制台 (8501) | `streamlit run src/web/app.py --server.port=8501 --server.baseUrlPath=/web` |
| 仅 MistralRS 3端口 | `.\scripts\start_all_mistralrs.ps1` |
| DeerFlow 网关 Docker | `.\start_deerflow_docker.ps1` |
| 生产 Docker Compose | `docker compose up -d` |
| 跑全部测试 | `pytest tests/ -x -v` 或 `.\scripts\run_tests_stable.py` |
| 端到端冒烟 | `.\scripts\aos_e2e_smoke.py` |
| 自检健康 | `pytest tests/test_self_harness.py -v` |

### 10.3 服务端口清单

| 端口 | 服务 | 暴露方式 |
|------|------|----------|
| 8000 | FastAPI（唯一对外端口）+ 统一网关 | 直接 |
| 8501 | Streamlit | 网关 /web → 内部 |
| 18789 | OpenClaw 网关 | 网关 /openclaw → 内部 |
| 2026 | DeerFlow 网关 | 网关 /deerflow → 内部 |
| 1234 | MistralRS 通用推理（MiniCPM）| 内部 |
| 1235 | MistralRS 编码推理（Qwen2.5-Coder）| 内部 |
| 1236 | MistralRS 推理推理（DeepSeek-R1）| 内部 |
| 11434 | Ollama（备选本地模型）| 内部 |

---

## 11. 依赖管理

**唯一真相**: [pyproject.toml](file:///d:/AOS/pyproject.toml)（MIT、Python≥3.11，支持 3.10-3.13）

**核心依赖组**（pyproject `[project].dependencies`）：

```
Web框架:      fastapi / uvicorn / pydantic(v2) / httpx / aiohttp / requests
AI编排:       langgraph / langchain-core / crewai
LLM平面:      openai(v1) / litellm
数据:         numpy / PyYAML / SQLAlchemy / sqlmodel
安全:         cryptography / bcrypt(在 security.py)
系统:         websocket-client / psutil
```

**可选 extras**：
- `dev`: pytest + pytest-cov + pytest-timeout + bandit + safety + ruff + mypy
- `test`: pytest + pytest-timeout
- `web`: streamlit≥1.30
- `security`: bandit + safety

**安装命令**：
```bash
# 最小核心
pip install -e .

# 完整开发环境（推荐）
uv pip install -e ".[dev,test,web,security]"
```

**重型依赖选型铁律（代码中反复强调）**：
- 内核不 import 任何第三方，全部懒加载在 `kernel/wiring.py` 或 `kernel/plugins/`
- 缺失即诚实降级，不用内存实现冒充真实后端
- 外部库用 `guarded_import(timeout)` 防止卡死 import 链
- prewarm 后台预热 autogen(180s)/litellm(22s)/mem0ai(40s)

---

## 12. 测试体系

### 12.1 测试分层（tests/ 目录 200+ 文件）

| 层次 | 示例文件 | 覆盖范围 |
|------|----------|----------|
| **核心内核** | `test_kernel.py` / `test_life_state.py` / `test_homeostasis.py` / `test_action_arbiter.py` / `test_desire.py` / `test_goal_evolution.py` / `test_confidence.py` | 内核单测 |
| **记忆系统** | `test_memory.py` / `test_memory_compression.py` / `test_memory_distiller.py` / `test_memory_ladder.py` / `test_memory_lifecycle.py` / `test_hippo_scroll_real.py` | 四层阶梯、压缩、蒸馏、生命、可信 |
| **进化系统** | `test_evolution_fitness.py` / `test_mirror_branch.py` / `test_evolution_distiller.py` / `test_evolve_engine.py` / `test_self_evolving_loop.py` / `test_whitebox_loop.py` | A/B、镜像闸门、蒸馏、自进化 |
| **合规与精神** | `test_kernel_compliance.py` / `test_compliance_*.py` / `test_spirit_layer.py` / `test_soul.py` / `test_dialectic.py` | 宪法、策略、大同、价值、辩证 |
| **虚实交互** | `test_interact_layer.py`（含紧急制动/人本因果/感知网关）+ `test_body_layer.py` | 急停、感知、HAL |
| **分形粒子** | `test_fractal.py` / `test_fractal_conflict.py` | 派生、冲突 |
| **Fabric 路由** | `test_fabric_hub.py` / `test_fabric_hub_chat.py` / `test_route_failover.py` / `test_tier_routing.py` / `test_cost_routing.py` / `test_route_runtime.py` | 注册、路由、级联、策略 |
| **Resilience** | `test_resilience_bus.py` / `test_resilience_gate.py` / `test_resilience_prewarm.py` | 熔断、自愈、预热 |
| **真实适配器** | `test_litellm_adapter.py` / `test_agnes_adapter.py` / `test_search_adapter.py` / `test_vlm_adapter.py` / `test_media_*.py` / `test_crawl4ai_adapter.py` / `test_comfyui_real.py` / `test_knowmesh_adapter.py` / `test_lfm2_real.py` / `test_localai_backend.py` / `test_img2threejs_adapter.py` | 每个适配器真连接（或 best-effort） |
| **A2UI** | `test_a2ui.py` / `test_a2ui_hub.py` + `test_orchestrator_a2ui.py` | 协议/渲染/工作流 UI |
| **工作流编排** | `test_code_team*.py` (4文件：主/多语言/LLM/A2UI) / `test_refinery_system.py` / `test_plan_parallelism.py` / `test_opc_real_fixes.py` | CodeTeam/炼化/并行/OPC |
| **API & 安全** | `test_api.py` / `test_security*.py` (3文件：基础/JWT/中间件) / `test_main_auth.py` / `test_approvals_routes.py` / `test_billing_api_basic.py` | REST/认证/授权/审批/计费 |
| **单创OS** | `test_danchuang_os.py` + `test_opc_cli.py` + `test_opc_loop.py` + `test_byok.py` | 创业OS/OPC/多租户/BYOK |
| **端到端** | `test_e2e.py` / `test_integration.py` / `test_final.py` / `test_live_real.py` / `isolated_e2e_smoke.py` | 全链路真跑 |
| **诚实验证** | `test_whitepaper_honesty.py` + `test_no_harvest_charter.py` | 验证所有"已完成"声明诚实性（白皮书契约）|

### 12.2 运行测试

```bash
# 快速单测（跳过需真实密钥/服务的）
pytest tests/ -x -v -k "unit or not real" --timeout=30

# 完整稳定测试（CI用）
python scripts/run_tests_stable.py

# 架构/诚实性校验
pytest tests/test_architecture.py tests/test_whitepaper_honesty.py -v
```

---

## 13. 关键文件速查表

按「想做什么→看哪个文件」组织：

| 想做的事 | 看的文件 |
|----------|----------|
| 加新能力到路由系统 | [capability.py](file:///d:/AOS/src/core/fabric/capability.py) 加枚举 |
| 接新的开源引擎/适配器 | `src/core/fabric/adapters/` 下新建 `xxx_adapter.py`，继承 `BaseAgentAdapter`，然后在 [wiring.py](file:///d:/AOS/src/kernel/wiring.py) 注册到 FabricHub |
| 修改路由策略（成本/延迟/质量） | [registry.py](file:///d:/AOS/src/core/fabric/registry.py) 的 PROVIDER_COST / PROVIDER_LATENCY / PROVIDER_QUALITY / ROUTE_STRATEGY |
| 改变默认档位（默认本地优先，云端仅兜底） | capability.py 的 ENGINE_TIER 和 registry.py 的 ROUTE_TIER、PROVIDER_PREFERENCE（默认 local_first；export AOS_ROUTE_POLICY=cloud_first 翻回云端优先） |
| 工作流步骤执行前拦一道审核 | [review_gate.py](file:///d:/AOS/src/kernel/approval/review_gate.py) 的 `_SENSITIVE_CAPS` 集合和 `should_review()` |
| 新写一个审批系统对接 ApprovalStore | [approval_store.py](file:///d:/AOS/src/kernel/approval/approval_store.py) 单例，create_approval → list_pending → approve/reject |
| 上下文窗口管理/压缩 | [context_manager.py](file:///d:/AOS/src/kernel/context/context_manager.py)：max_tokens / preserve_recent / 四优先级 |
| 加一个宪法红线（违反就全停） | [emergency_brake.py](file:///d:/AOS/src/kernel/interact/emergency_brake.py) 的 evaluate() 信号映射 + constitution_violation → FULL |
| 人本评估一个动作对用户的代价 | [human_causal_sim.py](file:///d:/AOS/src/kernel/interact/human_causal_sim.py) 的默认边表，可 `add_edge()` 扩展领域先验 |
| 感知数据过脏/污染 | [perception_gateway.py](file:///d:/AOS/src/kernel/interact/perception_gateway.py) 的 _PII_RULES / _INJECTION_PATTERNS / TRUST_TIERS |
| 分形粒子派生太猛 | `spawner.py` 的 MAX_GEN / MAX_SIBLINGS / QUOTA_DECAY 或 [growth_guard.py](file:///d:/AOS/src/kernel/fractal/growth_guard.py) |
| 成本爆炸 | [cost_tracker.py](file:///d:/AOS/src/kernel/pulse/cost_tracker.py) 里的 MODEL_PRICING 定价表，加上告警阈值 |
| 镜像分支升级默认太激进 | [mirror_branch.py](file:///d:/AOS/src/kernel/evolve/mirror_branch.py) 的 MIN_SAMPLES=20 / MIN_LIFT=0.05 / ALPHA=0.05 |
| 变更上达全体前先沙盘 | `spirit/datong.py` 的 `CivilizationMirror.rehearse(world, change, measure)` |
| 加新的 OPC 岗位 | `danchuang/opc/roles.py` 定义 + `agency_roles/岗位名.py` 写技能 |
| 工作流 Studio 接入新类型 | `studio/workflow_models.py` 加节点类型 + runner 翻译到 chiplet_steps |
| 接新的外部 MCP 服务给 Fabric 用 | `core/fabric/adapters/mcp_stdio_adapter.py` 或 `mcp_client_adapter.py` 加配置 |
| 前端加新页面 | `src/web/app.py` 加一个 streamlit tab（控制台），或 web/admin Next.js 页面 |
| 加新 API 端点 | `src/api/xxx_api.py` 写路由函数 + 在 `api/main.py` 的 mount 区 import |
| 生成安全的 API Key | `python scripts/generate_api_key.py` |
| 下载 GGUF 模型 | `.\scripts\download_gguf_models.ps1` |
| 架构全览图 | [docs/ARCHITECTURE_MAP.md](file:///d:/AOS/docs/ARCHITECTURE_MAP.md) / [docs/ARCHITECTURE.md](file:///d:/AOS/docs/ARCHITECTURE.md) |
| 系统定位/价值观 | [PHILOSOPHY.md](file:///d:/AOS/PHILOSOPHY.md) / [docs/LIFEFORM_OS_WHITEPAPER_V6.md](file:///d:/AOS/docs/LIFEFORM_OS_WHITEPAPER_V6.md) |

---

> **文档结束**。本 Wiki 基于对 200+ 核心 Python 文件 + 100+ 辅助文件的完整阅读编写而成，所有文件引用均为可点击的绝对路径，便于直接跳转到代码。
