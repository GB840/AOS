# AOS 演进接口路线（个人 → 团队 → 公司）

> **核心方针（用户原话落地）**："从个人开发者到团队到公司，不要求一步到，先从个人出发，但是要有演进接口路线。"
>
> **一句话定义演进接口**：AOS 只拥有少数**稳定契约（contract）**，所有重能力来自**可插拔后端**。个人→团队→公司三层演进 = **换后端实现（接口不变）**，不是推倒重写。

---

## 0. 当前通电基线（个人级已验证 ✅）

| 项 | 状态 |
|---|---|
| 组件初始化 | **19/19 healthy**（persistence / memory / hermes[299技能,4供应商] / deerflow / skills / mcp / subagents / compliance / identity / audit / router / fabric …） |
| 端到端对话 | **3/3 成功**（本地日期 / 知识问答 / 编码任务） |
| 真实 LLM 链路 | 智谱 GLM-4-Flash 云端回落生效（Hermes 本地不可用时自动回落云端） |
| 运行形态 | 单进程 `uvicorn`（:8000）+ SQLite + 单 API Key |
| 启动方式 | `PYTHONPATH=src;AOS` 下 `python -m uvicorn src.api.main:app`（后台托管，勿用 `&` 孤儿化） |

**结论**：个人级"可对话的智能体操作系统"已通电跑通，下面是要预埋的升级 seam。

---

## 1. 演进总原则：接口不变，换实现

```
                 ┌─────────────────────────────────────────┐
   调用方 ──────▶ │  AOS 稳定契约层（永远不变）               │
                 │  · BaseAgentAdapter.invoke()             │
                 │  · LLMRouter.chat()                      │
                 │  · persistence / memory / compliance     │
                 │  · security 中间件 / meta_orchestrator    │
                 └───────────────┬─────────────────────────┘
                                 │ 实现可替换
        ┌──────────────┬─────────┴──────────┬───────────────┐
     个人级实现      团队级实现            公司级实现
     SQLite          Postgres+Redis       多租户+对象存储
     单 API Key      OAuth2+多用户         SSO+RBAC+mTLS
     OpenClaw(live)  多 OpenClaw worker    引擎池化+协议总线
```

升级时**只改右侧"实现"列**，左侧契约层纹丝不动。新增能力 = 新增一个适配器，不碰主链路。

---

## 2. 七条演进接口（Seam）详述

### 2.1 Agent 引擎层 —— Fabric 薄缝（最核心）

- **稳定契约**：`src/core/fabric/adapter.py` 的 `BaseAgentAdapter`
  - `engine_id` · `advertise_capabilities()` · `invoke(InvokeRequest)` · `health()` · `supported_protocols()`
  - AOS **只拥有这一个契约**，永不重写 agent 大脑。
- **当前（个人级）**：
  - `OpenClawAdapter` 已 live（`/health` 显示 `fabric.live=["openclaw"]`）
  - Hermes / DeerFlow 经 `brain.py` 装配直连
  - `AG2Adapter` / `LiteLLMAdapter` / `Mem0Adapter` / `BrowserUseAdapter` / `LangfuseAdapter` 已就位，**懒加载重依赖，缺包时 `health()=False` 自动绕开**，注册永不崩。
- **团队级升级 seam**：接**真实 AG2** 群聊编排、拉起多个 OpenClaw worker、DeerFlow 真实长时任务执行。换引擎 = 让对应 adapter 的 `health()` 变 True，registry 自动路由过去。
- **公司级升级 seam**：引擎池化、跨机房容灾、统一 **MCP / A2A / ACP** 协议总线（适配器声明 `supported_protocols()`，两端同协议即走标准管线，无私有桥接）。

### 2.2 LLM 路由层

- **稳定契约**：`src/router/llm_router.py` 的 `LLMRouter.chat(messages, task_type) -> {provider, model, content}`
- **当前（个人级）**：5 个供应商 `ZHIPU / SILICONFLOW / BAIDU / XFYUN / OLLAMA`，启动时可用性探测 + 调用时云端回落（`_llm_cloud_fallback`）。
- **团队级升级 seam**：加入企业内网模型网关、按团队配额限流、`task_type` 精细路由。
- **公司级升级 seam**：换 `LiteLLMAdapter` 做统一路由层，挂成本中心（cost center）、合规审查网关、模型审计。

### 2.3 状态 / 数据层

- **稳定契约**：`persistence` 抽象接口（threads / messages / knowledge / tasks / audit_entries）
- **当前（个人级）**：SQLite（`data/sqlite/aos.db`，已存 5555 条 knowledge）
- **团队级升级 seam**：换 Postgres（共享库）+ Redis（会话/缓存/限流计数）
- **公司级升级 seam**：多租户 schema 隔离 + 对象存储（大文件/产物）+ 读写分离

### 2.4 记忆层

- **稳定契约**：`memory` 接口（`add_memory` / `search_memory` / `export_memory`）
- **当前（个人级）**：SQLite only，向量搜索禁用（chromadb 未装，日志：`向量存储未安装，记忆层初始化完成`）
- **团队级升级 seam**：接 pgvector / chromadb 做语义记忆
- **公司级升级 seam**：`Mem0Adapter`（已写）做分级权限知识库、跨团队记忆共享

### 2.5 合规审计层

- **稳定契约**：`compliance`（audit / identity / tracer）
  - `audit.py:AuditLogger.log()` · `identity.py:AgentIdentity` · `trace.py:OperationTracer`
- **当前（个人级）**：本地审计日志 + AID 身份 + 操作追踪（已就绪骨架）
- **团队级升级 seam**：审计汇总到共享存储、按成员隔离视图
- **公司级升级 seam**：国标 **GB/Z 185** 合规报告导出、SIEM 接入、不可篡改审计链（WORM）

### 2.6 接入 / 安全层

- **稳定契约**：`src/api/security.py` 中间件链（认证 / 限流 / 安全头）
- **当前（个人级）**：单 `X-API-Key` 头（.env `API_KEY`，长度 35），`/health` 免鉴权
- **团队级升级 seam**：多用户 API Key + OAuth2 登录
- **公司级升级 seam**：SSO / LDAP + RBAC + mTLS + 租户隔离（中间件替换为实现，路由不变）

### 2.7 调度 / 编排层

- **稳定契约**：`meta_orchestrator`（L3.5 顶层调度/策略/信任）+ DeerFlow 26-method scheduler
- **当前（个人级）**：单进程内同步调度
- **团队级升级 seam**：队列化任务（Celery / RQ）+ 多 worker
- **公司级升级 seam**：K8s 编排 + 弹性伸缩 + 跨可用区容灾

---

## 3. 三层演进对照总表

| 维度 | 个人级（当前✅） | 团队级（换实现） | 公司级（换实现） | **不变接口** |
|---|---|---|---|---|
| Agent 引擎 | OpenClaw(live)+Hermes+DeerFlow 装配 | 真实 AG2 群聊 + 多 OpenClaw worker | 引擎池 + MCP/A2A/ACP 总线 | `BaseAgentAdapter` |
| LLM 路由 | 5 供应商 + 云端回落 | 内网网关 + 团队配额 | litellm 统一 + 成本中心 | `LLMRouter.chat()` |
| 状态存储 | SQLite | Postgres + Redis | 多租户 + 对象存储 | `persistence` |
| 记忆 | SQLite | pgvector/chromadb | Mem0 + 分级权限 | `memory` |
| 合规审计 | 本地日志 + AID | 共享审计 + 成员视图 | GB/Z 185 + SIEM + WORM | `compliance` |
| 安全接入 | 单 API Key | OAuth2 + 多用户 | SSO + RBAC + mTLS | `security` 中间件 |
| 调度 | 单进程 | 队列 + 多 worker | K8s + 弹性 | `meta_orchestrator` |
| Web 控制台 | Streamlit 单机 | 共享看板 | 角色视图 + SSO | `/api/*` 契约 |

---

## 4. 真实开源引擎接线点（4 核心 + 4 辅助）

| 能力 | 真实开源项目 | AOS 接入点 | 状态 |
|---|---|---|---|
| 群聊 / 多智能体编排 | **AG2** (MIT) | `core/fabric/adapters/ag2_adapter.py` | 适配器就位，待真实接线 |
| 自进化单体智能体 | **Hermes** (vendored `external/hermes-agent`) | `src/hermes/agent.py` | 装配中（云端回落已通） |
| 长时任务超级智能体 | **DeerFlow** (vendored `external/deer-flow`) | `src/deerflow/` + fabric | 注册 273 项资产，待真实执行 |
| 个人 AI 助手 / 接入层 | **OpenClaw** | `core/fabric/adapters/openclaw_adapter.py` | **live ✅** |
| 统一 LLM 路由 | **LiteLLM** | `litellm_adapter.py` | 适配器就位 |
| 记忆 | **Mem0** | `mem0_adapter.py` | 适配器就位 |
| 浏览器操作 | **BrowserUse** | `aci_browser_adapter.py` | 适配器就位 |
| 可观测追踪 | **Langfuse** | `observability_langfuse_adapter.py` | 适配器就位 |

> 铁律：四个核心能力必须来自真实开源，AOS 只做集成层 + 提升层（统一数据/状态、进化治理、平台外壳、Web 控制台、合规审计）。**删除标准是"是不是真垃圾"，不是"是不是开源"。**

---

## 5. 升级操作手册（换实现不换接口）

**场景 A：接真实 AG2 群聊编排（团队级起点）**
1. `pip install ag2`（或已 vendored）
2. 在 `ag2_adapter.py` 的 `invoke()` 内填入真实 AG2 调用
3. 确保 `health()` 返回 True → fabric registry 自动把群聊类 capability 路由到 AG2
4. 主链路 (`brain.chat` / `/api/chat`) **零改动**

**场景 B：状态层换 Postgres（团队级）**
1. 实现 `persistence` 接口的 Postgres 后端（保持方法签名一致）
2. 改配置 `DATA_BACKEND=postgres` + 连接串
3. `brain` / API 路由 **零改动**

**场景 C：安全层换 OAuth2（团队级）**
1. 替换 `security.py` 中的 `APISecurityMiddleware` 认证逻辑为 OAuth2 校验
2. 中间件链顺序、路由装饰器 **零改动**

**场景 D：记忆层启用语义检索（团队级）**
1. `pip install chromadb`（或 pgvector）
2. `memory` 后端实现向量检索分支
3. `search_memory()` 调用方 **零改动**

---

## 6. 当前进度与下一步

**已完成（个人级通电）**
- [x] 19/19 组件 healthy，服务可启动（`Application startup complete`）
- [x] 端到端 3/3 对话成功，智谱 GLM-4-Flash 云端回落生效
- [x] Fabric 薄缝骨架（单一 `BaseAgentAdapter` 契约 + 6 适配器）
- [x] LLM Router 5 供应商 + 可用性探测 + 云端回落
- [x] 合规骨架（audit/identity/tracer）
- [x] 本演进路线文档

**待办（按用户"演进接口"路线推进）**
- [ ] Web 控制台（Streamlit :8501）启动并连上 API 验证（阶段2）
- [ ] 外部引擎真实接线：OpenClaw Gateway、AG2、Hermes 真实、DeerFlow 真实执行
- [ ] 团队级首个 seam 实战：状态层换 Postgres / 安全层加 OAuth2
- [ ] 记忆层启用语义检索（装 chromadb）
- [ ] git 提交本轮所有改动（含本文档）做版本保护

---

*文档依据：已通电系统的 `/health` 实测输出、`src/core/fabric/adapter.py` 契约、`src/router/llm_router.py`、`src/compliance/*`、用户"个人→团队→公司 + 演进接口路线"方针。*
