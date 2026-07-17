# AOS 全量架构盘点地图（feature/infra-setup）

> 目的：把整个 `src/` 摊开、一个模块都不放过，理清「谁真通电、谁闲置、谁重复、谁撞车」，
> 并给出「有效组建」的落点。所有结论均来自本机源码静态扫描 + 真实实例化探测，非臆测。
> 生成日期：2026-07-17。配套代码改动见提交 `c8d81fd` 之后本轮 content_director 接电。

---

## 0. 一句话结论

AOS 是一个**单基座 FabricHub 统一路由 + 多芯粒（adapter/chiplet/subagent）即插即用**的智能体 OS。
**路由层设计是健全的**（能力优先 + 档位优先 + 向低档级联 + 运行时故障转移）。
真正的问题不是「路由坏了」，而是**上层编排（尤其 content_director）严重低估了项目已有的富能力集**——
大量现成能力（`memory.knowledge` RAG、`vision.understand` 看图、270 个 `agency_roles` 角色库、cognee/lightrag/zvec 知识引擎）处于**通电但无人调用**的闲置状态。
本轮已把 content_director 接上这三块（详见 §6、§7）。

---

## 1. 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  接入层  api/main.py（FastAPI） · web/（Web UI）· companion   │
├─────────────────────────────────────────────────────────────┤
│  编排层  OrchestrationChiplet（通用流水线）· ContentDirector   │
│          （领域专用：内容生产）· meta_orchestrator（gRPC 意图/ │
│          优先级/persona 路由）· AG2（多智能体群）             │
├─────────────────────────────────────────────────────────────┤
│  路由层  FabricHub → FabricRegistry → providers_for()         │
│          （capability 匹配 + tier 优先 + 同级策略 + 级联）    │
├─────────────────────────────────────────────────────────────┤
│  能力层  24 个 BaseAgentAdapter（见 §3）· 10 个子智能体        │
│          （见 §5）· 270 个 agency_roles 人设库（见 §4）        │
├─────────────────────────────────────────────────────────────┤
│  底座    core/fabric（路由/适配器契约）· core/*（平台/池/     │
│          可观测/记忆/数据库）· execution（沙箱+任务队列）·     │
│          memory/persistence/compliance/hermes/voice/router/   │
│          mcp（见 §8）                                          │
└─────────────────────────────────────────────────────────────┘
```

**关键设计事实**（已核实 `registry.py:224` `providers_for`）：
- 同一 capability 可有多个提供者；路由**先按 tier（高→中→低）**，同级再按 `ROUTE_STRATEGY`（preference/cost/latency/quality）排序。
- 起始档由 `tier` 参数决定：auto/high 从高档起，向低档**级联兜底**（云端挂了用本地）。
- 排序后仍在供给方间做**运行时故障转移**（Auriko fallback 语义）。
- ⇒ **「撞车」是刻意的冗余设计，不是 bug**；下面 §7 列出的多提供者均由 tier 正确消解。

---

## 2. Capability 枚举（能力平面，共 ~30 项）

来源 `core/fabric/capability.py`，真实字符串值：

| 平面 | capability 值 | 说明 |
|---|---|---|
| 推理 | `inference.llm` | 统一大模型网关（LiteLLM） |
| 推理 | `inference.lnn` | 液态神经网络（CfC/LTC）时间序列推理 |
| 多模态 | `media.image` / `media.video` / `media.3d` | 文/图生图、文/图生视频、Three.js 3D |
| 记忆 | `memory.persistent` / `memory.episodic` / `memory.semantic` / `memory.knowledge` | 持久/情景/语义/RAG 知识库 |
| 视觉 | `vision.understand` | 图像/截图理解（图→文本） |
| 代码 | `code.generate` / `action.code_exec` / `code.understanding` | 生成 / 沙箱执行 / 索引检索 |
| 检索 | `web.search` / `web.fetch` | 联网检索 / 抓链提取 |
| 语音 | `voice.stt` / `voice.tts` / `voice.omni` | 识别 / 合成 / 全双工全模态 |
| 工具 | `action.tool_use` / `action.aci` | 工具调用 / 计算机界面操作 |
| 数据 | `data.query` | 通用数据查询（MCP） |
| 通道 | `channel.access` / `channel.send` | 20+ 聊天平台触达 |
| 编排 | `group.orchestration` / `cognition.planning` / `cognition.long_horizon` / `system.workflow` | 多体群 / 规划 / 长程自主 / 流水线执行 |
| 系统 | `system.observability` | 链路追踪（Langfuse） |
| 内容 | `content.produce` | 自主内容生产闭环（本轮接电） |

---

## 3. 24 个能力适配器（均已注册进 FabricHub `_ADAPTERS` 批量循环）

> 全部经 `fabric_hub.py` 的 `for cls in _ADAPTERS: self._registry.register(cls())` 真注册，
> 非孤儿。**多提供者**项用「⚠️」标注。

| 适配器文件 | engine_id | 广告 capability | tier |
|---|---|---|---|
| litellm_adapter | litellm | `inference.llm` ⚠️ | MEDIUM（云端网关） |
| lfm_adapter | lfm | `inference.llm` ⚠️ | 默认 MEDIUM（未显式配） |
| agnes_adapter | agnes | `inference.llm`⚠️ + `media.image`⚠️ + `media.video`⚠️ | MEDIUM（云端多模态） |
| lnn_adapter | lnn | `inference.lnn` | 默认 MEDIUM |
| comfyui_adapter | comfyui | `media.image`⚠️ + `media.video`⚠️ | **HIGH**（本地零成本） |
| threejs_adapter | threejs | `media.3d` | 默认 MEDIUM |
| mem0_adapter | mem0 | `memory.knowledge` + `memory.semantic` | **HIGH**（本地零成本，AOS_MEM0_LOCAL=1） |
| vlm_adapter | vlm | `vision.understand` | MEDIUM |
| code_team_adapter | code-team | `code.generate` | **HIGH**（本地 heuristic+隔离执行） |
| code_execution_adapter | code-exec | `action.code_exec` | **HIGH**（本地 subprocess 隔离） |
| codebase_memory_mcp_adapter | codebase-memory | `code.understanding` | 默认 MEDIUM |
| search_adapter | web-search | `web.search` | LOW（含免费源兜底） |
| web_fetch_adapter | web-fetch | `web.fetch` | LOW |
| stt_adapter | — | `voice.stt` | 默认 MEDIUM |
| tts_adapter | — | `voice.tts` | 默认 MEDIUM |
| omni_minicpm_adapter | minicpm_o | `voice.omni` | MEDIUM |
| aci_browser_adapter | — | `action.aci` + `action.tool_use`⚠️ | 默认 MEDIUM |
| scripts_adapter | — | `action.tool_use`⚠️ | 默认 MEDIUM |
| mcp_client_adapter | — | `data.query` + `action.tool_use`⚠️ | 默认 MEDIUM |
| mcp_stdio_adapter | — | `action.tool_use`⚠️ | 默认 MEDIUM |
| openclaw_adapter | openclaw | `channel.access` + `channel.send` | MEDIUM |
| ag2_adapter | ag2 | `group.orchestration` + `cognition.planning` | **HIGH**（本地规划） |
| observability_langfuse_adapter | langfuse | `system.observability` | MEDIUM |
| content_director（plugins） | content-director | `content.produce` | **HIGH** |

---

## 4. Skills 层

### 4.1 顶层技能（~52 个 .py，非角色库）
代码类：`codebase_memory` / `codebase_memory_mcp` / `cognee` / `lightrag` / `zvec` /
`engineering` / `loop_engineering` / `ruflo` / `j_stack` / `no_mistakes` / `safe_eval` /
`sandbox` / `skill_creator` / `find_skills` / `factory` / `versioning` / `learning`
检索/知识：`duckduckgo_search` / `searxng` / `jina_reader` / `ollama` / `llama_cpp`
视觉/媒体：`comfyui` / `pixelle_video` / `video_use` / `ui_ux_promax` / `frontend_design` /
`design_md` / `uitars` / `open_montage` / `vimax` / `viitor_voice`
平台/集成：`ima` / `herdr` / `lingbot_map` / `marketplace` / `monitoring` / `superpowers` /
`composition` / `template` / `templates/` / `generated/` / `agency_agents`（角色库加载器）
助手：`cli_helpers` / `skill_creator` 等。

### 4.2 agency_roles 角色库（**270 个 .py 人设**，此前纯摆设）
按文件名语义分类（自动归类，约数）：
- 开发/工程：**80**（前端/后端/架构/DevOps/DBA/嵌入式/FPGA/GIS…）
- 管理/组织/产品：**42**（项目经理/产品经理/运营/HR/高管/策略顾问…）
- 内容/媒体/视频：**20**（b站内容策略师、内容创作者、品牌守护者、linkedin 内容创作专家…）
- 金融/财务/商业：**17**（CFO、财务、税务、电商、保险、跨境…）
- AI/数据/算法：**11**（RAG、向量、知识图谱…）
- 安全/治理/合规：**5** + 语言/教育/医疗 **6**
- 其他/无法自动归类：**89**（含 backend_architect、esg、filament 优化、jira 管家、mcp 构建器…）

**关键事实**：角色库由 `skills/agency_agents.py:load_real_agency_agents()` 解析为
`{角色名: {description, prompt, ...}}`，但**没有任何编排器消费它**——直到本轮 content_director
按目标关键词挑人设定调（§6.3）。

---

## 5. 子智能体（10 个，对接外部/独立系统）
`ima_agent`（腾讯 IMA 知识库/笔记，已真接 OpenAPI）、`vimax_agent`（ViMax 子智能体）、
`meeting_agent`（会议）、`pixelle_agent`（出图）、`uitars_agent`（UI 自动化）、
`ruflo_agent`（工作流）、`loop_engineering_agent`、`skill_agent`、`lobster_agent`、
`registry`（子智能体注册表）。

---

## 6. 核心子系统职责（core/ + 其他）

| 子系统 | 职责 |
|---|---|
| `core/fabric` | 路由契约（adapter/registry/router/capability）、a2ui、companion、http_server |
| `core/platform` | 平台底座（资源/隔离） |
| `core/pool` | 模型/资源池 |
| `core/observability` | 链路追踪落地 |
| `core/memory` | 记忆抽象 |
| `core/database` | 持久化存储抽象 |
| `execution` | `SandboxManager`（代码沙箱）+ `TaskRunner`（任务队列） |
| `hermes` | `HermesAgent` 真·LLM 对话智能体（带记忆/知识检索） |
| `meta_orchestrator` | gRPC 意图分类 / 优先级 / persona 路由（高层调度，非流水线） |
| `deerflow` | legacy 工作流框架（与 FabricHub 双轨并存，**未打通**） |
| `voice` | 语音全套（STT/TTS/omni 前端） |
| `router` | 内部路由辅助 |
| `mcp` | MCP 客户端/服务端协议 |
| `memory` | 记忆实现 |
| `persistence` | 持久化实现 |
| `compliance` | 合规/策略引擎（独立 WIP，未碰） |
| `web` | AOS Web 界面层 |
| `utils` / `common` | 公共工具 |

---

## 7. 多提供者「撞车」清单（均由 tier 正确消解，非 bug）

| capability | 提供者（tier） | 谁胜出 | 兜底 |
|---|---|---|---|
| `inference.llm` | litellm(MED) / lfm(MED) / agnes(MED) | 同级→按 `ROUTE_STRATEGY` 偏好，默认 litellm（真网关） | lfm/agnes |
| `media.image` / `media.video` | comfyui(**HIGH**) / agnes(MED) | **comfyui 胜（本地零成本）** | agnes 云端简单出图 |
| `action.tool_use` | scripts / mcp_client / mcp_stdio / aci_browser | 同级按策略 | 多后端故障转移 |
| `memory.knowledge` / `memory.semantic` | mem0(**HIGH**) | mem0 本地 | — |

**结论**：content_director 调 `media.image` 默认命中 ComfyUI（动态节点图生效）；
ComfyUI 不可达才级联 Agnes（不懂 `intent`，降级简单出图——可接受兜底）。
`inference.llm` 默认命中 litellm 真网关。路由无致命缺陷。

---

## 8. 「未有效组建」缺口（待收口）

1. **content_director 此前只用 web.search+media+llm 三件套**，忽略项目已有的
   `memory.knowledge` / `vision.understand` / 270 角色库 / cognee / lightrag / zvec。
   → **本轮已修**（§6.3 / 提交）：接上知识库检索、参考图理解、角色库人设定调。
2. **270 个 agency_roles 纯摆设**（仅 `agency_agents` 技能可手动列/调，无编排自动消费）。
   → 本轮 content_director 已按意图自动挑选人设。
3. **legacy 双轨未收口**：`src/core/brain.py` 仍被 `api/main.py` import 并用作 `_BrainProxy()`
   （灰度兜底 `/api/chat`）；`deerflow/` 框架存在但与 FabricHub 新栈**未打通**。
   → 属独立收口任务，不在本轮范围（避免误触 WIP 边界）。
4. **原则 8 白盒 trace**：content_director 写文件但未产可被 `memory_distiller` 消费的结构化 trace。
   → 增强项，待做。
5. **各知识引擎（cognee/lightrag/zvec）未互联**：三者并存但无统一检索入口。
   → 属记忆系统整合任务。

---

## 9. 有效组建落点（建议优先级）

| 优先级 | 动作 | 状态 |
|---|---|---|
| P0 | content_director 复用 memory.knowledge / vision.understand / agency_roles | ✅ 本轮完成 |
| P1 | 让更多编排器（OrchestrationChiplet / AG2）自动消费 agency_roles 人设 | 待做 |
| P1 | 知识引擎（cognee/lightrag/zvec/mem0）统一检索入口 | 待做 |
| P2 | content_director 产出白盒 trace 喂 memory_distiller | 待做 |
| P2 | legacy brain.py / deerflow 双轨收口到 FabricHub | 待做（独立 WIP） |

---

## 10. 验证

- `tests/test_content_pipeline_real.py`：11 项（排除 FabricHub 真路由慢测）全绿，含
  「知识库被调用并入素材 / 角色库人设被挑选 / 参考图理解诚实降级」三条新回归。
- 真实 `FabricHub.route("content.produce", …)` 端到端慢测已往轮验证通过（~3min）。
