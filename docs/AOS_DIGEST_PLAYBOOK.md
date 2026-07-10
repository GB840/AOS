# AOS 消化 awesome-llm-apps —— 备忘录与有序执行计划

> 创建：2026-07-10（二期）
> 背景：用户递交一份「AOS vs awesome-llm-apps（11.4万 star 模板库）」战略分析。
> 纪律：沿用「验证够再定性」原则——本轮先逐条核验 AOS 侧前提，再据此执行。
> 边界：awesome-llm-apps 侧用户自承「公开知识级」，未独立读源码；以下 AOS 侧结论均来自代码实测。

---

## 0. 核心定位（一句话）

awesome-llm-apps 是**模板库**（100+ 独立应用，互不关联，各自 `streamlit run app.py`）；AOS 是**统一 Agent 操作系统**（统一大脑/fabric/记忆/合规，单进程拉起全部）。

**结论：不「对标」它，要「消化」它**——把它当 fabric 的能力填充物，把它的用户体验（3 行启动、端到端闭环）当 AOS 的准入门槛设计参考，然后在它到不了的地方（统一架构、合规、多引擎语义路由、可编程工作流）做出它做不出的东西。

---

## 1. 验证结论（AOS 侧事实校正表）

| # | 分析中的断言 | 实测结果 | 处置 |
|---|---|---|---|
| 1 | 4 进程启动（:8000/:8501/:18789/:2026） | ✅ 属实（`launch.py`→`scripts/aos_supervisor.py` 拉起 aos+web+openclaw+deerflow） | 保留：启动摩擦是真实痛点 |
| 2 | `web/app.py` 211KB 单体 | ❌ 文件指向错：仓库无 `web/app.py`；真实入口 `web/console.py`（轻量代理） | 纠正：展示层单体需另定位 |
| 3 | RAG 散落（codebase_memory/lightrag/cognee/jina_reader） | ✅ 属实，均为 `.py` 模块（610/379/726/454 行） | 建议#3 对症 |
| 4 | agency_roles 是纯 system-prompt 文件 | ✅ 属实：270 个 `.py`，样本 `短视频剪辑指导师.py`=Skill 子类，`execute()` 仅 `_build_prompt()`+`brain.chat()`，无自有工具/记忆/输出 schema | 建议#4 对症 |
| 5 | skills 大多只实现核心逻辑、无端到端闭环 | ✅ 属实：43 个模块仅 1 个（engineering.py）带 `__main__`；`vimax` 无 CLI | 建议#2 对症 |
| 6 | `protocols.py` 声明 MCP/A2A/ACP/AG-UI 四槽位 | ❌ 错：文件实为 `src/mcp/protocol.py`（单数），**仅实现 MCP**；A2A/ACP/AG-UI 无协议层 | 纠正：升华5 被高估 |
| 7 | gateway：hop-by-hop / Location 重写 / 连接时序 | ✅ 精准属实（`protocol.py:34/82/133/165-166`） | 保留：运维级差异点 |
| 8 | MASTER_PLAN 1.3 = 暴露 MCP Server | ✅ 属实 | 升华1/建议落地锚点 |
| 9 | `llm_router`+LiteLLMAdapter 按任务类型自动选模型 | ⚠️ 半真：router 真实可用且已接入 `brain.py:814`，但仅作 fallback；`task_type` 由调用方硬传、**无语义分类器** | 升华2 前提缺失，需新建 |

### 1.1 三处必须纠正的事实错误
- **`web/app.py` 不存在**。展示层入口是 `web/console.py`（轻量 Streamlit 壳，只代理 `/api`）。
- **协议层只有 MCP，没有「四槽位」**。此前的对话描述（"protocols.py 声明四槽位"）是未读代码就说的，已作废。真实：`src/mcp/protocol.py` 仅 `MCPProtocol/MCPTool/MCPResource/MCPPrompt`。
- **`llm_router` 不是语义路由器**。`LLMRouter.chat(messages, task_type=TaskType.GENERAL)` 的 `task_type` 由调用方硬传，全文件零处 embedding/LLM 语义分类；`_get_provider_priority()` 按 `config.ROUTER_*_PRIMARY` 管理员静态配置映射，再按可用性 fallback。主模型硬编码 `glm-4-flash`+智谱。

### 1.2 跨轮系统性发现（重要）
AOS 反复出现「**能力脚手架已建，但智能/接线缺失**」模式：
- `classify_with_llm`：LLM 分类器**写了但路由从不调**（死代码）。
- `llm_router`：provider fallback **真实可用且已接入**，但**语义分类器不存在**。

→ 任何「AOS 已具备 X 智能能力」的断言，都须先查「谁在调用、是否真走智能路径」，否则易重蹈 `classify_with_llm` 覆辙。

---

## 2. 战略定位：消化而非对标

AOS 已做得比它好的（别妄自菲薄）：统一架构 vs 模板孤岛、fabric 能力总线、合规（GB/Z 185）、统一网关（hop-by-hop/Location/连接时序）、开放协议方向（但当前仅 MCP 落地）。

AOS 该向它借的（具体、可操作）：见阶段 B/C。

AOS 真正该「升华」的方向（在它到不了处做出它做不出的）：见阶段 D。

---

## 3. 有序执行计划

### 阶段 A — 备忘录与文档校正（先把依据摆正）
- **A1（#130）** 本备忘录。
- **A2（#131）** 校正 MASTER_PLAN/DECISIONS/BRAIN_TRIAGE：protocol 四槽位→仅 MCP；llm_router 无语义；web/app.py→web/console.py；刷新过期指标（brain.py 1965+144、7 模块 2237、git 40、表 42）。

### 阶段 B — 降低准入门槛（借它的用户体验）
- **B1（#132）** 建 `examples/`：3-5 个独立可跑单应用，每个 3 行启动、不依赖 DeerFlow/Hermes/OpenClaw/brain.py（pdf_qa 纯 RAG / chat_bot 纯对话 / code_review 单 skill）。
- **B2（#133）** 核心 skill 加最小 CLI（`python -m skills.vimax --task ...`），证明脱离大脑可独立跑。

### 阶段 C — 能力矩阵与角色升级
- **C1（#134）** RAG 能力矩阵文档（你要做 X → 用 Y skill → 依赖）。
- **C2（#135）** agency_roles 试点升级为带工具/记忆/输出 schema 的完整 Agent 类（先 1-2 个试点验证模式）。

### 阶段 D — 升华项（依赖前面地基通电）
- **D1（#136）** 暴露 MCP Server（MASTER_PLAN 1.3，官方 mcp/fastmcp SDK 挂 transport）。
- **D2（#137）** 语义分类器接 llm_router（升华2 前提）。
- **D3（#138）** swarm_flow 真并发（升华3 前提；当前串行已确认）。
- **D4（#139）** 合规层自动继承（升华4：skill 执行自动审计/AID/trace）。

---

## 4. 执行纪律（本轮铁则）

1. **先审查，再动手**：每个任务动手前先读相关代码/确认依赖，不在未核实状态写码。
2. **无遗漏**：按 #130→#139 顺序推进，每项完成标记 completed 后才进下一项；跨会话靠本备忘录+任务清单续接。
3. **验收可证伪**：examples 真能 3 行跑；skill CLI 真能 `python -m`；MCP Server 真能被客户端发现；语义分类器给定 prompt 真能推断 TaskType。
4. **不破坏现有系统**：examples/ 与 skill CLI 为纯新增/低风险；阶段 D 改动核心前先确认调用链与测试不破。
5. **记忆同步**：每阶段完成追加 `D:/AI_Intel_Factory/.workbuddy/memory/2026-07-10.md` 纪要。
