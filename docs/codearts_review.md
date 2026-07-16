# 华为云码道（CodeArts）核实与借鉴研判

> 用户贴来 CodeArts 资料并要求"看看能不能用 / 有没有借鉴"。按 AOS 求是铁律：
> **先全网交叉验证真实性，再判可用性与借鉴点，不凭记忆下结论。**
> 配套文档：`docs/agentarts_openjiuwen_review.md`（智果/openJiuwen）。

---

## 一、真实性核实（2026-07-16 全网交叉验证）

**结论：CodeArts（华为云码道）是真实产品，非编撰。** 多方官方来源交叉印证：

| 来源 | 核实内容 |
|---|---|
| 华为云官网 `huaweicloud.com/product/devcloud.html` | 软件开发生产线 CodeArts，一站式 DevOps，10+ 子服务 |
| 华为云帮助中心 `support.huaweicloud.com/productdesc-devcloud` | 服务构成：Req/Repo/Pipeline/Check/Build/Deploy/TestPlan/Artifact 等 |
| `codearts.huaweicloud.com`（码道代码智能体） | Agent Team 多 Agent 并发、项目级代码生成、代码续写、单测生成、研发问答 |
| PDF 产品概述 `codearts-productdesc-pdf.pdf`（Issue 01, 2025-08-15） | 官方规格，含服务组合、优势、应用场景 |
| 用户提供的资料 | 与官方一致：定位"怎么写代码"、Agent Team、GLM/DeepSeek 模型、免费体验版 |

**关键事实校准**（避免误信营销口径）：
- **更名**：软件开发生产线于 **2026-07-14 更名为"华为云码道 CodeArts"**（用户资料所述"码道"即此）。
- **模型**：代码智能体使用 **GLM-4.7 / GLM-5 / DeepSeek-V3.2** 等三方模型（混合，非纯自研），说明它本质是"编排 + 三方 LLM"的产品化包装。
- **免费边界**：体验版"个人&企业免费"是 **50 人内 / 资源受限** 的限时档；商用按套餐/资源扩展计费 —— **非零成本**，与 AOS"零付费必选"理念冲突。

---

## 二、能不能用（可用性判定）

**不能直接做 AOS 组件。** 原因与 AgentArts 同源：

1. **云 SaaS 属性**：代码/流水线/制品全在华为云，数据主权在华为侧，按订阅/资源计费。违反 AOS 理念 4（万物为我所用、零付费必选项）、理念 1（不手配自闭环）、主权在己。
2. **定位不同层**：CodeArts 是**工具链/研发平台**（解决"怎么写代码 + 怎么交付软件"），AOS 是**智能体操作系统**（解决"怎么让智能体自主干活"）。用户原话"码道解决怎么写代码，智果解决怎么让智能体自主干活"——**精准**。两者是上下游关系，不是替代关系。
3. **结论**：只能**参考其架构与产品思路**，绝不能把 AOS 做成它的前端，也不引入其 CI/CD/制品仓库（那是用户自己的基建，AOS 不做平台）。

---

## 三、有没有借鉴（按性价比分级，映射到 AOS 现有代码）

| 借鉴项 | CodeArts 做法 | AOS 现状 / 映射 | 级别 | 落地建议 |
|---|---|---|---|---|
| 多 Agent 代码团队 | Agent Team 自动组建研发团队、多 Agent 并发执行 | 已有 `SubAgentRegistry` + `OrchestrationChiplet`（DAG 编排）+ `code_execution_adapter` | **P1** | 强化 code-exec 适配器的"多 Agent 协作生成代码"编排：复用现有芯粒，不新造团队框架。思路借，组件不借 |
| 代码质量门 | 3000+ 检查规则、Top10 语言、安全/合规/通用质量 | 已有 `compliance.py`（`PolicyEngine` allow/deny + 速率 + `AuditEntry` 链式哈希不可篡改） | **P1** | 借鉴其"安全/合规/通用质量"三分规则类型，丰富 AOS 审计策略维度；不引入其规则引擎 |
| 单元测试自动生成 | 自动生成单测、发现问题自动修复 | ag2/llm 调 `code_execution_adapter` 跑 `pytest` 已可行 | **P2（不新做）** | 作为 AOS 的一个 **skill**（复用现有 LLM + code-exec），不造平台 |
| 代码智能体 IDE 集成 | 沉浸式编码、IDE 插件、代码续写 | 已有 `ui_layer.py`（可换皮 UI）+ 刚落的 **A2UI**（声明式 agent 画界面） | **P2（确认不新做）** | CodeArts 的"沉浸式编码"体验可被 A2UI 的声明式 UI 思路覆盖；不引入其 IDE/插件体系 |
| 研发知识问答 / Agent 知识增强 | 深度理解项目知识、精准检索 | 已有 mem0 本地记忆 + IMA 知识库 + `memory_compression.py` | **P2** | 复用现有记忆/检索层；不引入其知识引擎 |

**明确不借**：
- 整个 CodeArts 平台（SaaS，无法嵌）。
- 流水线 / 制品仓库 / 部署（CI/CD 是用户自己的基建，AOS 是编排内核，不做平台）。
- "体验版免费"的错觉——商用付费，重申非零成本。

---

## 四、与智果（AgentArts）/ AOS 的三层对照

| 层 | 华为产品 | 对 AOS 的意义 |
|---|---|---|
| 怎么写代码（工具链） | 码道 CodeArts | 参考其多 Agent 代码团队 / 质量门思路，映射到 AOS 的 code-exec + compliance |
| 怎么让智能体自主干活（运行平台） | 智果 AgentArts | 参考其 Harness / A2UI / 上下文引擎，映射 AOS 的 workflow + 刚落的 A2UI + memory_compression |
| 怎么训/推模型（模型层） | 魔坊 ModelArts | 与 AOS 无关（AOS 是编排内核，模型是能力端点） |

**一句话**：码道（写代码）+ 智果（跑智能体）+ 魔坊（训模型）= 华为的全栈 Agentic 云；AOS 是更底层的"操作系统"，三者都可作为**外部能力端点**被 AOS 路由调用，但不替换 AOS 内核。

---

## 五、待用户拍板

- 是否要我把"多 Agent 代码团队（P1）"作为下一个落地项（复用 `OrchestrationChiplet` + `code_execution_adapter`，让 AOS 能像 CodeArts 一样协作生成代码）？
- 是否要顺手把 CodeArts 的"质量门三分规则"补进 `compliance.py`（P1，低成本）？

> 注：本文档与 `agentarts_openjiuwen_review.md` 构成"华为云 Agentic 全家桶"双产品研判，均经全网交叉验证，非编撰。
