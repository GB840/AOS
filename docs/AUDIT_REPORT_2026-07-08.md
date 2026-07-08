# AOS 全面全方位审查报告

> 审查时间：2026-07-08 23:28 (GMT+8)
> 审查范围：运行态 / Git 卫生与安全 / 代码组织 / 四核心 OSS 集成真实度（铁律合规）/ AOS 子系统内部一致性 / 配置一致性
> 审查方式：运行态实测 + 静态走查 + 全仓引用检索（3 个 Explore agent 并行深度审计，只读未改）
> 仓库路径：`/d/AOS`，分支 `feature/infra-setup`

---

## 0. 执行摘要

**总体结论：系统"骨架正确、可运行、且有真实 OSS 接入"，但内部存在一套从未生效的能力路由、一处被铁律禁止却仍激活的自研模块、一组只在 fallback 才工作的端点、以及分裂的配置读取通道。技术债偏高，铁律有 1~2 处被内部违反。**

| 维度 | 评分(10) | 一句话 |
|---|---|---|
| 运行态 | **9** | 四端口全活，AOS /health 200，三上游经网关 307 重定向正常 |
| 四核心 OSS 集成真实度 | **6.5** | Hermes/DeerFlow 真在跑；AG2 假接入（违反铁律）；OpenClaw 半真半自研 |
| 代码组织 | **5** | 历史平行目录已清，但仍有平行控制台、嵌套空目录、明文口令、多个 God File |
| 架构一致性 | **5** | Fabric 能力路由是死设计；生产路由与宣称路由双轨并存 |
| 安全/配置 | **6** | 敏感文件已忽略、无入库；但明文口令 + 配置分裂是隐患 |
| **综合** | **≈ 6.3** | 生产可用，但需一轮"铁律合规 + 死代码收敛"重构 |

**最该立刻处理的三件事（P0）：**
1. **AG2 假接入** —— 适配器真实且 `live=True`，但 `route_via_fabric()` 全仓零调用，生产群聊实际由 AOS 自研 `swarm_flow/negotiation/meta_debate` 承担，**直接违反"群聊编排 → AG2 真实驱动"铁律**。
2. **明文管理员口令** —— `setup_deerflow.py:5` 硬编码 `aos123456`，且写在仓库里。
3. **自研 OpenClaw 仍激活** —— `brain.py:745` 实例化了文件头自标 `DEPRECATED`、明确"违反用户铁律"的 `core.open_claw.OpenClaw`。

---

## 1. 运行态盘点（实测）

四端口全部监听，进程均存活：

| 服务 | 端口 | PID | 状态 |
|---|---|---|---|
| AOS (统一前门) | 8000 | 2272 (161MB) | ✅ /health → 200 |
| Web 控制台 (Streamlit) | 8501 | 14768 | ✅ LISTEN |
| OpenClaw Gateway | 18789 | 14144 | ✅ LISTEN（真实返回模型文本） |
| DeerFlow Gateway | 2026 | 12864 | ✅ LISTEN（/health 200） |

- AOS 经网关探活三上游：`web/openclaw/deerflow` 均返回 **307**（重定向到真实上游，路由正常）。
- 运行日志抽样：`Meta-orchestrator (L3.5) ready`、`Mem0 ready (mem0 real)`、`Langfuse observability ready (disabled-no-key)`、`unified gateway mounted`、`Application startup complete` —— 全绿。

**结论：运行态健康，无崩溃、无重启循环。**

---

## 2. Git 卫生与敏感文件安全

- 分支：`feature/infra-setup`；最近提交 `1b4ada7`（本轮三块工作已入库）。
- **未提交改动（预存，非本轮，刻意未纳入）**：`src/skills/*`(9 文件)、`src/voice/tts.py`、`src/web/app.py`。建议单独 review 后提交。
- **敏感文件覆盖**：`.env` / `.env.security` / `cookies.txt` 均被 `.gitignore` 忽略，且 `git ls-files | grep` 确认**无任何密钥入库** ✅。
- **`.env.example`**：全部为空占位（`ZHIPU_API_KEY=` 等），无真实密钥泄露 ✅。
- **`secrets/` 目录**：`.gitignore` **未**忽略它，但实测为**空目录**（无害）。建议补 `.gitignore` 一行 `secrets/` 防未来误提交。

**结论：密钥治理基本到位，仅 `secrets/` 缺忽略规则（空，低风险）。**

---

## 3. 代码组织与冗余/垃圾（Agent A）

### 🔴 高
- **H1 平行冗余 Web 控制台**：`web/console.py`（~360 行，指向 :8000）全仓零引用；与 `src/web/app.py` 功能重叠。应删。
- **H2 嵌套空目录**：`src/src/` 及 `src/src/skills/` 为空，历史"平行目录"残留。应删。
- **H3 明文管理员口令（高危）**：`setup_deerflow.py:5` `{"username":"admin","password":"aos123456",...}` 写在仓库。
- **H4 God File**：`src/web/app.py` **4297 行**单文件承担对话/技能/语音/合规/ComfyUI/前端设计。

### 🟠 中
- **M1** `config/` 与 `configs/` 并存，`config/hermes` 孤立无引用。
- **M2** 硬编码 Windows 绝对路径：`start_deerflow.py:9` `os.chdir(r"d:\AOS\external\deer-flow\backend")`；`logs/*.py` 探针硬编码 `/d/AOS/...`。
- **M3** 更多 God File：`brain.py` 1699 行、`main.py` 1466 行。
- **M4** `.env` 在仓库目录（已忽略未入库，属管理异味，非泄露）。
- **M5** `logs/` 放探针脚本（`probe_deerflow2x.py` 等 `.py` 源码放日志目录）。
- **M6** OpenClaw 双实现（`core/open_claw.py` vs `fabric/adapters/openclaw_adapter.py`）；三个同名 `sandbox.py`。

### 🟡 低
- 空壳目录 `src/chroma_data/`、`src/outputs/`；未完成 stub `scripts/test_meta_orchestrator.py`；顶层散落 8 个 `test_*.py`；`omni_route.py`(914)/`memory.py`(912)/`agency_agents.py`(902) 接近大文件阈值。

**历史对照**：此前点名的 `aos_deerflow/` 与 `common/` 平行目录**已清理**（当前仅 `src/common` 单一来源）。说明重构有效，但缺常态化"平行目录检测"防复发。

---

## 4. 四核心 OSS 集成真实度（铁律合规，Agent B）

| 能力 | 来源 | 真实度 | 证据 |
|---|---|---|---|
| **Hermes** | external/hermes-agent（完整 vendored） | ✅ 真实运行 | `brain._init_real_hermes` 真加载 `AIAgent`；日志 `✅ REAL Hermes-Agent loaded`；L1/技能/路由重度使用 |
| **DeerFlow** | external/deer-flow @:2026 | ✅ 真实运行 | `DeerFlowGatewayClient` 真实 HTTP（/api/runs/wait·stream、submit_task）；端点契约与 vendored 后端匹配；`/api/tasks`、`/deerflow/*`、gateway 代理多路调用 |
| **OpenClaw** | openclaws.io @:18789 | ⚠️ 半真半自研 | 网关真实跑推理（日志有真实返回文本）；但 AOS 侧 L1 入口仍挂自研废弃 `core.open_claw.OpenClaw` |
| **AG2** | pip `ag2`(autogen) | ❌ 假接入风险 | 适配器真实且 `live=True`，但 `route_via_fabric()` 全仓零调用；生产 `chat()` 群聊由 AOS 自研 `swarm_flow/negotiation/meta_debate` 承担 |

### 重大偏差：AG2 违反铁律
- 铁律约束："群聊/多智能体编排 → **AG2** 真实驱动"。
- 实际：`ag2_adapter.py` 内有真实 `GroupChat`/`GroupChatManager`/`initiate_chat` 调用，且启动日志 `live 5` 含 `ag2`。但 `route_via_fabric` 除定义外**无任何调用点**；`brain.chat()` 的群聊/多智能体实际走 AOS 自研模块（对 `ag2|GroupChat|autogen` 检索 0 命中）。**AG2 仅存在于 demo 脚本 `scripts/slice_groupchat.py`，未进入生产主链路。**
- 影响：这是最关键的假接入点，等于"装好了没用"，且对外宣称与实际不符。

### OpenClaw 自研残留
- `core/open_claw.py` 文件头自标 `DEPRECATED (2026-07-08) — 违反用户铁律"不能自己写"`，但 `brain.py:745` 仍 `self.open_claw = OpenClaw(brain=self)` 实例化；且 `subagents/openclaw_agent.py`（同标 DEPRECATED）在 `OPENCLAW_ENABLED` 为真时默认注册。官方 Fabric `OpenClawAdapter` 反而未 live（health 探测未过）。

### ClawSwarm
- 已**彻底移除**（无代码/配置/import 引用）；仅 `docs/GLOBAL_REVIEW.md`、`docs/OPEN_FABRIC.md` 两处良性说明性引用。✅

---

## 5. AOS 子系统内部一致性（Agent C）

### 5.1 双轨未收敛（最严重架构问题）
- Fabric 的"能力路由体系"（`FabricRegistry.route` / `providers_for` / `snapshot` / `route_via_fabric` / 所有 adapter `.invoke`）在生产路径上**零调用**。
- 真实路由由 `task_classifier.classify()` + `meta_orchestrator.route_intent()` 承担，与 Fabric 互不相交。
- `/api/fabric` 端点仅做自省，不做路由。
- **结论**：Fabric 实际只是"注册表 + 可视化面板"，其设计卖点是死设计，误导后续维护。

### 5.2 声明未实现的端点（生产链路会坏）
| 端点 | 问题 | 严重度 |
|---|---|---|
| `/api/subagents/deep/*`（5 个） | 调用 `brain.deerflow.register_subagent/list_subagents/execute_subagent_async/get_subagent_result/cancel_subagent` —— **这些方法只存在于 fallback `DeerFlowScheduler`，不存在于真实 `DeerFlowGatewayClient`**。REAL 模式下 → `AttributeError` → HTTP 500。`src/web/app.py` 同样调用 | **高** |
| `/api/multimodal/analyze` | 读取图片字节后仅返回硬编码提示语，未接任何视觉 LLM | 中 |

### 5.3 死代码 / 未接钩子
- `route_via_fabric`、`FabricRegistry.route/providers_for/snapshot`：零调用。
- 全部 6 个 Fabric adapter 的 `.invoke()`：因路由死而永不可达。
- `self.open_claw`（自研，DEPRECATED）：赋值后再无引用 → 死属性。
- `meta_orchestrator/server.py:serve()`（gRPC :50051）：启动脚本**从未启动**它 → gRPC 面是孤岛；且模块级 `_engine = MetaOrchestratorEngine()` 若手动启动会与 `brain.meta_orchestrator` 成**双引擎**。
- `MetaOrchestratorEngine.inject_persona`：仅经 gRPC 调用，而 gRPC 不启动 → 生产不可达。
- （澄清：`meta_orchestrator_pb2_grpc.py` 中的 `NotImplementedError` 桩已被 `server.py` 同名类正确覆盖，非真 stub。）

### 5.4 meta_orchestrator 接通度（已接但冗余）
- `route_intent` 三重暴露（brain.chat / `/api/meta/route` / gRPC）。**问题：每次 `/api/chat` 触发两次 `route_intent`** —— 一次在 `main.py:305` 仅用于附加 meta 元数据，一次在 `brain.chat()` 内部裁决 → 重复计算 + `evolution_log` 双倍写入。
- `propose_self_modification` 两处；`query_priority` 两处（未接 chat）；`inject_persona` 仅 gRPC（不可达）。
- 评价：已从"孤岛"变为"接通但有冗余"，比前序审计好，但仍需收敛。

### 5.5 memory / observability 接通度
- **Mem0Store**：真接（`/api/memory/semantic/*` → `brain.semantic_memory_*`），降级安全。缺口：`chat()` 主链路**从不调用**语义记忆（无 RAG-in-chat）。且 Fabric 里另有 `Mem0Adapter` 永不被路由 → 双接线。
- **LangfuseTracer**：三者里接通最干净（`/api/chat` best-effort 发 trace）；但 Fabric registry 的 `langfuse` 条目同样是冗余装饰。

---

## 6. 配置一致性（隐性地雷）

根因：**`pydantic-settings` 在 import 时读 `.env` 但不回写 `os.environ`**。于是所有用 `os.getenv` 的模块能否拿值，取决于**启动脚本是否 export**。

| 配置 | `utils/config.py`(pydantic) | 直接 `os.getenv` 模块 | 风险 |
|---|---|---|---|
| 智谱 LLM | `ZHIPU_*` | `mem0_store.py` 读 `AOS_LLM_*` | 两套同名不同键，易漂移 |
| 智谱 key | `config.ZHIPU_API_KEY` | `mem0_store.py` 读 `ZHIPU_API_KEY` | mem0 拿值**完全依赖 start_all.sh 的 export**；换启动方式即静默降级 |
| Langfuse | config 无字段 | `langfuse_tracer.py` 读 `LANGFUSE_*` | 脱离统一配置面 |
| OpenClaw token | config 无字段 | `gateway.py` 读 `OPENCLAW_GATEWAY_TOKEN` | 依赖 start_all.sh export |
| DeerFlow 凭证 | `config.DEERFLOW_ADMIN_*` | `brain.py:86` 硬编码 `admin/aos123456` 兜底 | 与 config 默认不一致但能跑 |

**影响**：`mem0/langfuse/gateway/openclaw` 的正确行为隐式依赖 `start_all.sh` 的 export；用 `uvicorn` 直接起则这些会静默降级（Hermes 仍正常，制造行为不一致）。

---

## 7. 关键风险 TOP 清单（按优先级）

### P0 — 铁律合规 / 安全（建议本周内处理）
1. **AG2 假接入**：把 L4 群聊或新增 `/api/groupchat` 接到 `route_via_fabric(GROUP_ORCHESTRATION)`，让真实 `GroupChat` 进入生产链路。
2. **明文口令** `setup_deerflow.py:5`：改为环境变量/随机生成，勿硬编码入库。
3. **自研 OpenClaw 激活**：删除 `brain.py:743-749` 对 `core.open_claw.OpenClaw` 的实例化；收敛到 `gateway.py` 反向代理 + Fabric `OpenClawAdapter`（并修其 health 探测使其 live）。

### P1 — 生产链路 bug（避免线上 500）
4. **`/api/subagents/deep/*`**：在 `DeerFlowGatewayClient` 补齐委派方法（转发 :2026），或显式判 `real_deerflow` 返回 501。
5. **Fabric 死路由**：要么在 `brain.chat()` 真插入 `route_via_fabric` 委派，要么把 Fabric 显式降级为"能力目录/可视化"，删 `route/providers_for/snapshot` 等死代码。
6. **meta 双调用**：`/api/chat` 只调一次 `route_intent`（统一在 `brain.chat` 内做，结果携带 meta）。
7. **配置分裂**：`config.py` 增 `LANGFUSE_*`/`OPENCLAW_GATEWAY_TOKEN`/`AOS_LLM_*` 字段，相关模块改读 `config.xxx`；或 `config` 加载后 `os.environ.setdefault` 回写。

### P2 — 技术债 / 整洁
8. 删平行冗余：`web/console.py`、`src/src/` 空目录、`config/hermes` 孤立项。
9. 收敛 `logs/` 探针脚本、`test_*.py` 散落文件到 `scripts/`/`tests/`。
10. `multimodal/analyze` 接真实视觉 LLM 或从 `/info` 移除避免误导。
11. 删 Fabric 重复 adapter（`Mem0Adapter`/`LangfuseAdapter`/`OpenClawAdapter` 中与 `mem0_store`/`langfuse_tracer`/gateway 重复的装饰项）。
12. 给 `secrets/` 补 `.gitignore` 规则（当前空，低风险）。

### P3 — 长线
13. 拆分 God File（`app.py` 4297 / `brain.py` 1699 / `main.py` 1466）。
14. 在 CI 加"平行目录检测 + 空文件/硬编码密钥扫描"防复发。
15. 清理 `docs/` 中两处 ClawSwarm 良性说明引用（满足"彻底移除"字面要求）。

---

## 8. 整改路线图建议

| 轮次 | 目标 | 关键动作 |
|---|---|---|
| 第一轮 | 铁律合规 + 安全 | AG2 接入生产群聊；删自研 OpenClaw 激活；改明文口令 |
| 第二轮 | 修生产 bug | subagents/deep 补齐或 501；Fabric 死路由收敛或降级；meta 双调用改单次 |
| 第三轮 | 配置统一 | config 对象统一；start_all export 收敛 |
| 第四轮 | 整洁 | 删平行控制台/空目录；移脚本；拆 God File；CI 防护 |

---

## 附录：证据索引（关键路径）

- 运行态：`netstat` 四端口 LISTEN；`aos_live.log` 全绿 markers。
- AG2 假接入：`src/core/brain.py:635`（route_via_fabric 定义，零调用）、`src/core/fabric/adapters/ag2_adapter.py:103-110`（真实 GroupChat）。
- 明文口令：`setup_deerflow.py:5`。
- 自研 OpenClaw：`src/core/brain.py:745-746`；`src/core/open_claw.py:1-5`（DEPRECATED 标注）。
- subagents/deep 缺失：`src/api/main.py:669-703`；缺方法仅存在于 `src/deerflow/scheduler.py:479`（fallback）。
- meta 双调用：`src/api/main.py:305` + `src/core/brain.py:1122-1134`。
- 配置分裂：`src/utils/config.py` vs `src/core/memory/mem0_store.py:31-36` / `src/core/observability/langfuse_tracer.py:34-36` / `src/api/gateway.py:122,191`。
- 平行冗余：`web/console.py`（零引用）、`src/src/`（空）。

> 本报告为只读审查产出，未对任何文件做修改。所有判定基于 `/d/AOS/src/`、`/d/AOS/external/`（含子仓）源码与运行日志指纹。
