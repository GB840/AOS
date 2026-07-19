# AOS 新范式：诚实可验证的自进化 Agent 操作系统
## Verifiable Self-Evolving Agent OS

> 本文档定义 AOS 要开辟的新范式，是后续三个 MVP（任务 #270/#271/#272）的蓝图与接口契约。
> 所有"已落地"断言均经代码核实（2026-07-19，见第 4 节代码落点）；"待做"标注为诚实待办，不假装完成。

---

## 0. 一句话定位

AOS 不只是"又一个 agent 框架"。它的真正差异化是：**把"失败学习"和"诚实性"作为第一公民，构建一个可审计的自进化操作系统**——系统每次失败都让它变强，且每一步都可复核、可追溯、不伪造。

---

## 1. 为什么需要新范式（行业事实，2026-07 全网核实）

| 痛点 | 事实来源 | 对 AOS 的含义 |
|------|----------|---------------|
| **复合失败** | LangChain《State of Agent Engineering 2026》：每步 95% 可靠 → 20 步仅 36% 端到端成功；85% → 10 步仅 19.7% | 多步链路成功率指数衰减，是生产级 agent 的头号杀手 |
| **评测空白** | 清华 SEAGym（arXiv:2606.17546）：现有 benchmark 面向静态系统，无法判断"自我改进"是否泛化/遗忘/过拟合 | "自进化"若不可审计，等于开盲盒 |
| **自进化三死穴** | 市面主流方案：①刷分作弊（OPRO 改 prompt）②直接改自己源码（Meta HyperAgents / Gödel Machine，危险不可控）③只更新记忆层（Mem0 / Letta，锁在子系统） | AOS 必须避开这三条路 |
| **范式转移已发生** | Harness Engineering 自进化成为 2026 真实方向（翁荔长文、清华 SEAGym、小米 HarnessX + AEGIS 进化引擎） | AOS 不是凭空发明，是踩在正确方向上的整合者 |

**结论**：自进化 agent 是真实前沿，但市面方案要么不可审计（黑盒改源码）、要么只优化单一子系统、要么不可控。这正是 AOS 的空白切入机会。

---

## 2. AOS 的新范式定义

**Verifiable Self-Evolving Agent OS（诚实可验证的自进化 Agent 操作系统）** =

> 统一内核调度（芯粒故障隔离） **+** 诚实自进化闭环（失败即训练 + 反思重设计 + Meta-Trace） **+** 白盒进化蒸馏（Trace 即进化源）

核心命题：**不是"更聪明的模型"，而是"让模型之外的运行层持续自我改进，且每一步都可审计"。**

它正面硬刚第 1 节的两个最大痛点：
- **抗复合失败**：每步有真实闸门（硬判定成/败），失败必反思重设计而非原地重试——链路不会因为一步抽风就雪崩。
- **解决评测空白**：全链路 Trace 结构化落盘 + 诚实量化置信，系统的每次"自我改进"都带原始证据，可复核、可回放、可审计。

---

## 3. 三大支柱

### 3.1 诚实自进化闭环（抗复合失败的核心）

- **每步真实闸门**（理念 2.5）：搜索必须有真实返回条数、代码执行必须有 stdout 或写进非空文件、推理必须非拒答且够长——空转/敷衍一律判失败，**不谎报成功**。
- **失败即重设计（非原地重试）**：反思 agent 用 trace 里的**真实错误**诊断根因，产出"换了做法的新计划"再执行一轮，绝不把同一条命令重跑一遍。
- **Meta-Trace 记忆**（理念 2 / 8）：每次失败的"根因→修正"提炼为结构化教训，跨任务持久化（有界 JSONL，仅留最近 N 条），后续相似任务的反思自动注入这些历史教训，避免重复已知失败。
- **诚实量化**（理念 6 / 9）：每步附带原始证据（stdout/stderr/exit code/来源 URL/相似度）+ 量化置信级别（低/中/高），拒绝"大概/可能/应该是"。
- **代码落点**：`src/kernel/autopilot.py`（`_reflect_and_redesign` / `_load_lessons` / `_save_lesson` / `_REFLECTION_MEMORY_PATH` / `MAX_REFLECT`）；`src/memory/lifecycle.py`（`MemoryLifecycleBridge._maybe_prune` 机会式真实 TTL 淘汰 + 分层降级）。

### 3.2 抗复合失败内核（工程底座）

- **统一内核 FabricHub 独占**路由 / 记忆 / 上下文主权；重型芯粒（agnes / ag2 等）以**独立子进程**运行 = **crash boundary**（故障熔断隔离，非自治多 Agent 拆分）。
- 多步链路中，单个芯粒崩溃 = 局部熔断，不引发雪崩；统一路由层做能力级故障转移（六级检索兜底、多引擎 fallback）。
- **代码落点**：`src/kernel/wiring.py`（`build_default_kernel` / `build_fabric_hub`，默认 `isolate_heavy=True`）；`src/kernel/plugins/fabric_hub.py`（`FabricHub.route` 运行时故障转移）；`src/kernel/compliance.py`（`PolicyEngine.check_capability` + `policy_enforce_enabled` 派发边界鉴权）。

### 3.3 白盒进化蒸馏（安全的自我改进）

- 全链路执行 Trace 以结构化 JSON 默认落盘（理念 8），作为进化的**原始数据源**（不是黑盒权重）。
- 蒸馏器从 Trace 提炼经验 → 回读 Registry 沉底不可靠引擎（白盒可进化，行为可解释、可回退）。
- **与 HyperAgents"直接改自己源码"对比**：AOS 的进化来自**可复核证据蒸馏**，不盲目改运行时代码，规避灾难性遗忘与刷分作弊。
- **当前状态**：Trace 生产者 + 部分蒸馏 / Registry 回读已存在但分散在 `autopilot.py` / `fabric_hub.py`；**待 MVP（任务 #272）整合为独立、可演示、带测试的组件**，不在本蓝图阶段声称完成。

---

## 4. 已落地资产 vs 待做 MVP（诚实对照）

| 资产 | 状态 | 代码落点 |
|------|------|----------|
| 反思重设计闭环 | ✅ 已落地 | `kernel/autopilot.py` |
| Meta-Trace 教训跨任务沉淀 | ✅ 已落地 | `_REFLECTION_MEMORY_PATH`（`_traces/reflection_memory.jsonl`） |
| 记忆生命周期 TTL / 分层淘汰 | ✅ 已落地 | `memory/lifecycle.py`（`_maybe_prune` 机会式触发） |
| 统一内核 + 芯粒故障隔离 | ✅ 已落地 | `kernel/wiring.py`、`fabric_hub.py` |
| 派发边界鉴权 PolicyEngine | ✅ 已落地 | `kernel/compliance.py` |
| 诚实量化置信 + Trace 证据 | 🟡 部分（搜索/路由已带，待全链路统一） | 各适配器 `InvokeResult` |
| 白盒蒸馏 → 沉底引擎 独立组件 | ✅ 已落地 | `kernel/evolution_distiller.py` + `examples/evolution_distiller_demo.py` |
| 端到端自进化演示闭环 | ✅ 已落地 | `examples/self_evolving_demo.py` + `tests/test_self_evolving_loop.py` |
| 抗复合失败基准测试 | ✅ 已落地 | `examples/resilience_benchmark.py` + `tests/test_resilience_gate.py` |

---

## 5. 与市面方案的本质区别（不假装原创）

- 我们**不**声称发明了"自进化"——HyperAgents / SEAGym / 浙大求是引擎都已证明方向正确。
- 我们的差异化是**组合创新 + 诚实性第一公民**：把
  `失败即训练 + 每步真实闸门 + 全链路可审计 + 故障熔断隔离`
  整合为一个**安全的、可验证的**自进化 OS。
- 市面方案对比：
  - HyperAgents / Gödel Machine：直接改自己运行时源码 → **不可控、灾难性遗忘风险**。
  - Mem0 / Letta：只优化记忆/RAG 单层 → **自我优化被锁死在子系统**。
  - OPRO / AFlow：改 prompt / 摆工作流积木 → **天花板低、刷分嫌疑**。
  - **AOS**：进化来自白盒证据蒸馏 + 每步硬判定 + 全程可审计 → **可控、可复核、抗复合失败**。
- 浙大求是引擎的 Meta-Trace 用于科学发现场景；AOS 将其**泛化为通用 agent 的"经验记忆"**，并叠加诚实量化与故障隔离，形成可生产的工程范式。

---

## 6. 路线图（四个 MVP）

| # | 任务 | 交付物 | 对应任务 |
|---|------|--------|----------|
| 1 | 范式蓝图 + 架构图 | 本文档 | #269 ✅ |
| 2 | 诚实自进化闭环演示 MVP | 端到端跑真实任务，展示"失败→反思→记忆→下次变强" + 每步可审计证据 + 集成测试 | #270 |
| 3 | 抗复合失败内核基准 | 基准脚本证明多步链路成功率不随步数指数崩塌（对照 LangChain 20步→36%） | #271 |
| 4 | 白盒进化蒸馏引擎 | 独立可演示组件（Trace 蒸馏 → 沉底引擎），带演示 + 测试 | #272 |

---

## 7. 设计纪律（贯穿所有 MVP，不变）

- 全部 **opt-in**、**故障隔离**、**零足迹**、**不伪造**（理念 6 / 9）。
- 每个 MVP 必须**真跑验证 + 测试守护 + 提交 + push**，不以"设计文档"冒充"已完成"。
- 诚实标注每一项的真实状态（第 4 节），区分"已落地资产"与"待做 MVP"，绝不把蓝图当落地。
