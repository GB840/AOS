# AOS v5.0 能力审计：对照 Hermes / DeerFlow / OpenClaw 三模块 + AG2 群聊

> 审计日期：2026-07-07
> 方法：直接阅读 `D:\AOS\src`、`D:\AOS\scripts` 真实代码体，不采信 docstring/README 自述。
> 状态图例：✅ 真实实现　🟡 部分/桩/人工在环　🔴 缺失

---

## 一句话结论

AOS 是四个模块的**综合编排外壳 + 严谨数据底座 + 平台能力层**，在"架构整合广度"上确实超越了任意单一参考模块；但在三个最关键的"灵魂能力"上明显缺位或桩化——**① 消息渠道接入层（寄生式交互）、② 自主进化闭环、③ MCP 真实传输**；且**大脑（Hermes/DeerFlow）是外部 vendored 进程，缺失即降级为罐头回复**——这是最大隐患。

---

## 一、对照总表

### 模块一 · AG2（多智能体群聊编排）
| 能力 | 原文要求 | AOS 真实状态 |
|---|---|---|
| 智能体管理(创建/启停/角色/权限) | 运行时实例生命周期 | 🟡 `agent_card.py` + 300+ `agency_roles` 角色定义 + `subagents/registry.py`；但无运行时 create/start/stop 实例管理 |
| 群组协作(智能体互相对话) | 自由论坛式群聊 | ✅ `swarm_flow.py`(DAG 数据传递) + `meta_debate.py`(辩论/投票) + `negotiation.py`(协商)；比自由论坛更结构化，但缺开放群聊 UI |
| 消息路由(规则/插件) | 规则+自定义插件 | ✅ `router/llm_router.py` + `task_classifier.py` + `meta_orchestrator.route_intent` 真实 |
| Web 管理后台 | Vue 控制台 | ✅ `src/web/app.py`(Streamlit) + `src/api/main.py`(FastAPI) 真实；形态不同但功能等价 |
| 部署(Docker/1Panel) | 容器化/一键 | ✅ `Dockerfile` + `docker-compose.yml` 存在；1Panel 一键未做 |
| V9.0 信号场(12维/7域/物种进化) | 场耦合物理机制 | 🔴 未实现信号场物理；以 DAG+辩论+LLM 路由替代；"物种进化"= 人工批准的 proposal 日志，非自动 |
| OpenClaw channel 插件 / WS 桥接 | TS 插件 + WS | 🟡 `core/open_claw.py` 是 L1 入口层(文本/语音/文件/API 多渠道)，但非 AG2 的群聊形态 |

### 模块二 · Hermes（自进化单体）
| 能力 | 原文要求 | AOS 真实状态 |
|---|---|---|
| 自我进化(建技能/迭代/搜历史/跨会话建模) | 自主闭环 | 🟡 `skills/learning.py`(feedback→suggestion 规则循环 `auto_optimize_skill`) + `memory.py` FTS5 可搜历史；非 Hermes 式"自动改写代码"，是**人工在环** |
| 70+ 工具 | 工具集 | ✅ `skills/` 下 43 个真实适配器 + 300+ 角色，广度 ≥ |
| Skills 系统(agentskills.io) | 开放标准 | 🟡 `skill_creator.py` + `marketplace.py` 存在，兼容性未验证 |
| 四层记忆(MEMORY.md/USER.md) | 显式分层 | 🟡 `memory.py` 有 conversation/knowledge/task + 可选 Zvec/ChromaDB 语义层；无显式四层代码 |
| 子智能体委派(3 并发隔离) | 隔离子 Agent | ✅ `subagents/` 8 类 + `registry` + `swarm_flow.execute_parallel` |
| 上下文文件自动发现 | .hermes.md 等 | 🔴 未见自动加载逻辑 |
| 检查点/回滚 | /rollback | ✅ `Snapshot` 表 + `EventStore` 回放 + `persistence_bridge` checkpoint 真实 |
| Cron 定时任务 | 自然语言/cron | 🔴 AOS 原生无 |
| execute_code 沙箱 | 沙箱 RPC | ✅ `platform/sandbox.py` PythonSandbox 真实(subprocess+AST 白名单+超时)；WasmSandbox 为桩 |
| 批处理 | ShareGPT 轨迹 | 🔴 未见 |
| 语音模式 | 全平台语音 | 🟡 `voice/`(Baidu asr/tts) 真实适配器，需 API key |
| 浏览器自动化 | 浏览器操作 | ✅ `subagents/uitars_agent.py`(GUI 自动化) 真实 |
| MCP 集成 | 原生 | 🟡 `mcp/protocol.py` 仅枚举，无传输层；真实 server 在 `external/` |
| 消息网关(TG/Discord/Slack/WA/Teams) | 多平台 | 🔴 缺失 |
| 本地 Web 仪表盘 | 浏览器管理 | ✅ Streamlit + FastAPI |

### 模块三 · DeerFlow（长时超级智能体）
| 能力 | 原文要求 | AOS 真实状态 |
|---|---|---|
| Planner/Executor/Researcher/Reviewer | 显式角色类 | 🟡 无显式角色类；`swarm_flow` 用通用 role-step + 8 类子智能体替代 |
| 主+3 子并行 | 并行调度 | ✅ `execute_parallel` + 8 子智能体 |
| 隔离沙箱(local/Docker/K8s) | 多模式 | 🟡 PythonSandbox(local) 真实；Docker/K8s 沙箱缺失 |
| 分层记忆(TF-IDF+tiktoken) | 相似度检索 | 🟡 FTS5 + 可选 Zvec/ChromaDB；无 TF-IDF/tiktoken |
| 上下文工程(11 层中间件/自动摘要) | 中间件链 | 🟡 `platform/middleware.py`(RateLimiter/idempotency/inject_trace) 有，但非 11 层自动摘要链 |
| 可插拔 Skill | 出厂技能 | ✅ `skills/` 大量真实适配器 + `marketplace.py` |
| 长任务中断恢复 | 跨会话 | 🟡 `EventStore` 回放 + checkpoint 支持；跨会话状态追踪未完全 |
| 多工具协同决策 | 动态选工具 | 🟡 `router/llm_router.py` + `tool_executor.py` |
| IM 渠道(飞书/TG/Slack) | 原生适配 | 🔴 仅占位 `FEISHU_WEBHOOK` 环境变量 |

### 模块四 · OpenClaw（个人助手框架）
| 能力 | 原文要求 | AOS 真实状态 |
|---|---|---|
| 寄生式交互(20+ 平台) | 多渠道接入 | 🔴 无真实平台客户端（`open_claw.py` 只是 L1 入口抽象，非 20+ 渠道接入） |
| 7×24 运行 | 常驻守护进程 | 🟡 FastAPI 可常驻，但无守护进程/网关层 |
| 私有 SQLite | 本地存储 | ✅ 42 表 ORM + SQLite |
| 三层(通信/网关/大脑) | 架构对应 | ✅ brain + router + api 结构对应 |
| 插件系统(100+/ClawHub) | 插件市场 | 🟡 `skills/registry` + 300+ 角色 + `marketplace.py`；非网络市场 |
| 技能系统(300+ 原子/渐进/CI) | 技能生态 | ✅ 300+ `agency_roles` + `skill_creator` + CI |
| 四层记忆 | 记忆架构 | 🟡 同 Hermes 段 |
| MCP 原生(stdio/HTTP) | 传输 | 🟡 协议骨架，传输缺失 |
| 自动化(cron/standing/hooks) | 调度 | 🟡 cron 缺；hooks 部分 |
| 安全(审计/访问控制/受信/事件响应) | 安全加固 | ✅ `compliance/`(audit/identity/trace) + `api/security.py` 真实 |
| Rust/Alpine 实现 | 高性能 | 🔴 Python 实现 |

---

## 二、真正的提升（AOS 超越单模块之处）

1. **统一编排中枢**：`UnifiedBrain` + `meta_orchestrator`(意图分级路由) + `swarm_flow`(DAG) + `meta_debate`(辩论/投票) + `negotiation`(协商) —— 把 AG2 的群聊、Hermes 的委派、DeerFlow 的并行**整合进一个可调度的编排层**，单模块都做不到这种综合。
2. **严谨数据底座**：42 表 SQLModel ORM（infra/ecosystem/evolution/economy/immune），含真实外键关系、WAL+foreign_keys、并发锁、异步进化日志 —— 四个参考模块大多只用简单 SQLite/JSON，AOS 的持久层更工程化。
3. **平台外壳 10 模块**：observability / resilience(熔断)/ middleware / notify / eventstore / fileproc / sandbox / cold / devops / compat —— **全部真实、零硬依赖、可插拔降级**。这是四个模块都没有的"生产级平台能力层"。
4. **技能生态广度**：300+ 角色定义 + 43 个真实工具适配器 + 8 类子智能体 + 真实 Web 管理台 + 合规审计体系 + CI 质量门禁（AST 扫描/44 项 smoke）。综合覆盖面超过任一单模块。

## 三、真正的遗漏与风险（按致命度排序）

1. **🔴 接入层全缺（四模块的共同灵魂）**：Telegram/Discord/Slack/WhatsApp/飞书等**真实平台客户端为零**。四模块的核心卖点都是"寄生在已有聊天窗口里干活"，AOS 目前只能 API/文件进、Streamlit 出，等于没有"触达用户的手"。
2. **🔴 大脑外部依赖（最大隐患）**：Hermes/DeerFlow 是 `external/` 下 vendored 的外部进程；`brain.py` 有 `degraded` 降级分支——**外部引擎缺失/未配置时，`chat` 静默降级为罐头回复**。AOS 自身没有原生的 LLM 推理循环兜底。
3. **🟡 自主进化是"假闭环"**：`propose_self_modification` 只是插入一条 `status="proposed"` 的记录，等人工审批；`learning.py` 是规则式 feedback→suggestion。对比 Hermes"自动从经验改写代码"，AOS 的进化是**人工在环的提案日志**，不是自主闭环。
4. **🟡 MCP 只有协议没有传输**：`mcp/protocol.py` 仅定义消息枚举，无 stdio/HTTP 实现；真实 MCP server 在 external 里。
5. **🟡 cron/自动化原生缺失**：无 APScheduler/Celery/standing-orders；调度完全依赖外部 DeerFlow scheduler。
6. **🟡 AG2 群聊机制为社区分叉实现**：12 维信号场/7 域/前向衰减编码/物种进化，被 DAG+辩论+LLM 路由替代——功能目标部分达成，但机制完全不同，且"物种进化"仍是人工批准。

## 四、建议优先级（若要补齐成"可用产品"）

- **P0**：接入层 —— 先接 1~2 个真实渠道（飞书/Telegram），否则系统无法触达用户。
- **P0**：原生大脑兜底 —— 给 `brain.py` 一个不依赖 external 的轻量 LLM 循环，消除"降级为罐头"风险。
- **P1**：MCP 传输层（stdio + Streamable HTTP 客户端）。
- **P1**：自主进化闭环 —— 把 `propose_self_modification` 从"提案日志"升级为"审批后自动改代码 + 回归测试 + 回滚"。
- **P2**：cron/standing-orders 调度器；Docker/K8s 沙箱；上下文自动摘要中间件链。
- **P2**：双轨存储收敛（`persistence_bridge`/`memory` 的裸 SQL 迁到 `session_scope()`，与 42 表 ORM 统一）。

---

*审计证据来源：直接读取 `src/core/brain.py`、`src/meta_orchestrator/engine.py`、`src/core/platform/*`、`src/memory/memory.py`、`src/deerflow/persistence_bridge.py`、`src/skills/learning.py`、`src/web/app.py`、`src/api/main.py` 等真实代码体。*
