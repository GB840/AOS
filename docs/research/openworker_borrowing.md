# OpenWorker 借鉴分析（面向 单创OS / AOS）

> 核实来源：本地已下载源码 `/d/OpenWorker1/openworker-main/README.md`（OpenWorker 官方仓库
> `github.com/andrewyng/openworker`，**MIT 许可**，2026-07 仍在 open beta）。
> 本文仅依据其 README 公开架构陈述 + 仓库目录结构，**不引其代码**（用户指令 + 技术栈不兼容，见下）。
>
> **核实结论（真实 / 营销口径）**：
> - 真实：本地优先、BYOK、审批门控、定时自动化、25+ 连接器、基于 aisuite 统一层 —— 均在 README 明确写出。
> - 未深核：未逐行审计 `coworker/` 源码实现（对"借鉴优化"叙事足够；若需精准抄机制再读源码）。
> - 许可：MIT（商用友好），但技术栈为 **Rust Tauri 桌面壳 + Python agent server + React/Vite GUI**，
>   与 AOS 的 Python 后端 + Streamlit/console 架构**不兼容直接引代码** → 按 MEMORY § XII 处置为「借鉴优化」。

---

## 一、OpenWorker 真实骨架（README 核实）

| 维度 | OpenWorker 做法 |
|------|----------------|
| 形态 | 桌面 AI 同事（desktop app），交付**完成物**（文档/表格/报告/网页），不是聊天 |
| 本地优先 | agent loop、对话、连接器 token、模型 key 全在本地 secret store；唯一云部件是 OAuth 握手 broker |
| BYOK | OpenAI / Anthropic / Gemini / GLM(Z.ai) / DeepSeek / Qwen / MiniMax / Mistral / Grok + Together/Fireworks 云端 + Ollama 本地，随时切换 |
| 审批门控 | 写/发/跑命令前必须人工 approve；无人值守时把待办**park 到 inbox** 而非自作主张 |
| 定时自动化 | automations 跑周期任务（晨报/周报/盯频道），运行带完整 transcript 落 app |
| 连接器 | 25+：GitHub/Slack/Jira/Notion/Linear/HubSpot/Outlook/monday.com/Gmail/Google Calendar + 终端 + 本地文件；任何 MCP 工具可插，且**逐工具控制** |
| 统一层 | 引擎构建于 **aisuite**（andrewyng 出品）：跨供应商统一 chat-completions API + agents 层(tools/toolkits/MCP) |

---

## 二、对 单创OS / AOS 的可借鉴理念（逐条映射）

> 结论先行：**OpenWorker 是"消费级桌面 agent 应用"，AOS 是"agent OS 后端内核"——层级不同**。
> 但它在"用户侧产品范式"上**验证了 AOS 架构选择的正确性**（本地优先 / BYOK / 审批门控 / MCP 连接器 / 统一模型层），
> 并贡献 3 个 AOS 尚未做满的可借点。可借的是**范式与缺口补齐**，不是代码。

### 1. 本地优先 / BYOK —— AOS 已具备且更强（✅ 复核通过，不重复造）
- OpenWorker：本地 secret store 存 key、Ollama 本地跑、BYOK 切供应商。
- AOS 对应：
  - 本地优先 → FabricHub 三级档位「高=本地零成本/最强隐私」为默认级联起点（capability.py `ENGINE_TIER`）。✅ 已解决
  - BYOK → **租户级 BYOK 密钥层 + 模型配置**（#377-#387）：比 OpenWorker 的单用户 key 更进一步，做到**多租户隔离 BYOK**。✅ 已超越
- **借法**：对外 pitch 直接点明「单创OS 的本地优先/BYOK 已覆盖且支持多租户」，把 OpenWorker 当"正确路线佐证"。

### 2. 审批门控 → 强化 AOS HITL（✅ 已部分，补"inbox park"范式）
- OpenWorker：无人值守时把待审批动作 **park 到 inbox**（而非自动执行或静默失败）。
- AOS 对应：HITL 审批（#235）、content-director 的 human-in-the-loop approve 才发布。✅ 已有闸门
- **借法（优化点 A）**：把 OpenWorker 的「park to inbox」范式**显式写入 AGENTS.md 诚实纪律**——
  自主环（autopilot/opc_loop）遇到"有后果动作 + 当前无人审核"时，**持久化待审项到审核收件箱**，
  等人在环再决策；绝不"假装执行"或"静默跳过"。这正好补 AOS「失败即训练 / 有生有灭」的边界。

### 3. 定时自动化（standing watch）→ OPC 调度增强（➕ 未来 opt-in）
- OpenWorker：automations 周期跑、盯频道、带 transcript。
- AOS 对应：autopilot / opc_loop 已能常驻自主环；但"按 cron 调度某岗位做周期产出并留痕"尚未产品化封装。
- **借法（优化点 B）**：在 OPC 飞轮上补「岗位级定时任务」原语（如市场调研岗每日竞品简报、客服岗每周工单复盘），
  运行落 `TaskTraceStore` 留痕——复用现有 opc_loop，不引 OpenWorker 代码。

### 4. 25+ 连接器 / 逐工具控制 → 印证 AOS 能力路由（✅ 已更强）
- OpenWorker：per-tool 控制接入；任何 MCP 可插。
- AOS 对应：FabricHub 的 **capability 级路由 + 权限即边界**（§5）比 per-tool 更统一；已有
  `MCPClientAdapter` / `MCPStdioAdapter` + `register_mcp_server`，任何 MCP 服务器可插。✅ 已超越
- **借法**：把 OpenWorker「逐工具开关」对应到 AOS「capability 级启用/禁用」（env 门控 + 不可达静默跳过），
  对外表述统一为「连接器即能力，按需开关、缺则降级」。

### 5. aisuite 统一层 → 对照 AOS inference.llm 网关（🔍 评估替代项）
- OpenWorker 用 aisuite 做跨供应商统一 chat-completions + agents(tools/toolkits/MCP)。
- AOS 用 **LiteLLM** 做统一 LLM 网关（`LLM_GATEWAY` / `litellm_adapter`），route_runtime 做档位路由。
- **借法（优化点 C）**：aisuite 的"单一 chat-completions 接口 + 内建 tool-calling/agents 层"设计，
  可作为 AOS `inference.llm` 网关的**对照参考**——若未来想简化 agent tool-call 编排，可评估
  aisuite（MIT）替换/补充 LiteLLM 的 agent 层；当前 AOS 链路已够用，**不紧急、不锁死**。

---

## 三、处置定级（按 MEMORY § XII 外部项目铁律）

| 项 | 判定 | 动作 |
|----|------|------|
| 能否商用 | MIT（能） | —— |
| 技术栈兼容？ | ❌ Rust Tauri 桌面壳，与 AOS Python 后端不兼容，不能直接引代码 | **借鉴优化** |
| 最终处置 | **借鉴优化**（范式 + 3 个缺口补齐，不引代码） | 落本文件 + AGENTS.md §5.2 + 产品愿景 10.3 对标 |

---

## 四、AOS 落地清单（只借鉴，不引代码）

1. **[优化点 A]** AGENTS.md 诚实纪律补「无人值守 → park 到审核收件箱」范式（autopilot/opc_loop 自主环边界）。
2. **[优化点 B]** OPC 飞轮加「岗位级定时任务」原语（复用 opc_loop + TaskTraceStore 留痕）。
3. **[优化点 C]** inference.llm 网关把 aisuite 列为「可选统一层对照项」（当前 LiteLLM 够用，不切换）。
4. 对外叙事：把 OpenWorker 当作「本地优先/BYOK/审批门控/MCP 连接器/统一模型层」的**正确路线佐证**，
   强调 AOS 已覆盖且多租户 BYOK / capability 级路由更统一。
