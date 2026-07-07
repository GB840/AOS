# AOS 缺了什么？—— 2026 全网前沿照镜子

> 结论先说：你感觉的"差点意思"是**结构性**的。OpenClaw / Hermes / DeerFlow（群聊编排由 AG2 驱动）
> 这 4 个真实开源，**全都处在同一个平面——「智能体行为 / 协调平面」**。它们解决的是
> "agent 怎么接入用户、怎么开会、怎么进化、怎么长跑"。但一个能在 2026 打的生产级
> Agentic OS 是**多层平面**的，我们缺了它下面的 4 个基础设施平面。每一个缺口都对应一个
> 具体、真实、可 vendored 的开源项目（不违反"必须真开源、不可自研"的硬约束）。

---

## 一、我们用 4 个 OSS 覆盖了什么（已有 ✅）

| 平面 | 项目 | 角色 |
|---|---|---|
| 行为/协调平面 | OpenClaw | 接入用户（嘴耳） |
| 行为/协调平面 | AG2 | 多 agent 群聊编排（会议室） |
| 行为/协调平面 | Hermes | 自我进化引擎（脑） |
| 行为/协调平面 | DeerFlow | 长时任务执行（体） |

**问题**：这 4 个本质是"会调 LLM 的框架壳"。它们自己**不生产智能**，都靠外接 LLM API。
而它们之下的基础设施——谁供 token、谁管知识、谁让 agent 动手、谁看住它别乱来——
在我们的设计里**一个都没有**。

---

## 二、缺的 4 个平面（缺失 ❌，附真实开源候选）

### ❌ 平面 1：推理网关（最致命）
- **为什么缺**：4 个 OSS 都是"调 LLM 的壳"，但没有任何一个提供**统一的 LLM 接入/路由/容灾/计费**。
  等于"有脑框架，没有神经元燃料"。这是 AOS 当前最大的"差点意思"。
- **真实开源**：[**LiteLLM**](https://github.com/BerriAI/litellm)（BerriAI，MIT）——单一 OpenAI 格式接口
  统一接入 100+ LLM（OpenAI/Anthropic/Gemini/Bedrock/Azure…），自带负载均衡、故障转移、成本追踪。
  已被 1B+ 请求验证，Fortune 500 在用。
- **AOS 怎么用**：作为「燃料层」插在 4 个 OSS 之下，它们不再各自硬编码 LLM key，统一走 LiteLLM。

### ❌ 平面 2：记忆 / 知识中枢（RAG）
- **为什么缺**：2026 的共识是"长期记忆已从可选插件升级为核心基础设施"，演化出
  Graph-RAG / Agentic RAG。我们的 4 个 OSS 里，DeerFlow 只有 TF-IDF 轻量检索，
  **没有一个以"知识/检索中枢"为主业**。AOS 的 42 表是结构化状态，不是语义检索。
- **真实开源**：[**Mem0**](https://github.com/mem0ai/mem0)（MIT，arXiv 2504.19413，记忆中心架构）、
  [**LlamaIndex**](https://github.com/run-llama/llama_index)（RAG / Agentic RAG 的事实标准）。
- **AOS 怎么用**：作为「知识平面」接在推理网关之上、行为平面之下，给所有引擎共享语义记忆。

### ❌ 平面 3：动手 / ACI 平面（Agent Computer Interface）
- **为什么缺**：OpenClaw 是"嘴耳"（文本渠道），但 agent 要"干活"得操作浏览器/OS。
  ACI（Agent-Computer Interface）是 2025 末命名的范式（aci.dev 开源接 600+ 工具）。
  我们在 taxonomy 里预置了 `action.aci`，但**没有任何真实 OSS 落地它**。
- **真实开源**：[**browser-use**](https://github.com/browser-use/browser-use)（83K–93K ★，MIT，
  Playwright 驱动，"让网站对 AI 代理可访问"）、[**Cua**](https://github.com/trycua/cua)
  （15K ★，MIT，完整 Computer-Use 基础设施：沙箱+评测+桌面虚拟化）。
- **AOS 怎么用**：作为「手」平面，暴露 `action.aci` 能力给所有引擎统一调用。

### ❌ 平面 4：观测 / 评测 / 护栏（生产就绪）
- **为什么缺**：2026 年 agent observability 已成独立学科（tool-call tracing、multi-agent span、
  evals、guardrails）。我们虽有 `platform/observability.py` 骨架，但是**空壳**，没有真实
  评测与护栏。没有这一层，4 个 OSS 跑起来就是"黑箱 + 静默失败"。
- **真实开源**：[**Langfuse**](https://github.com/langfuse/langfuse)（OSS LLM 观测 + 评测）、
  [**Phoenix (Arize)**](https://github.com/Arize-ai/phoenix)（OSS LLM 评测 / 追踪）。
- **AOS 怎么用**：作为「神经健康」平面，包裹所有引擎，提供 tracing / eval / guardrail。

---

## 三、修正后的完整栈（分层平面模型）

```
┌─────────────────────────────────────────────────────────────┐
│  提升层  AOS 总部（已有✅）                                    │
│  42表统一状态 · 安全进化治理 · 平台外壳 · 控制台/合规          │
├─────────────────────────────────────────────────────────────┤
│  行为/协调平面（已有✅）—— 4 个真实开源                        │
│  OpenClaw(接入) ← Hermes/DeerFlow(引擎) , AG2(协调)     │
╞═══════════════════════════════════════════════════════════════╡
│  ✅ 推理网关平面   → LiteLLM（100+ LLM 统一网关，最致命缺口）  │
│  ✅ 记忆/知识平面  → Mem0 · LlamaIndex                         │
│  ✅ 动手/ACI平面  → browser-use · Cua                          │
│  ✅ 观测/评测/护栏 → Langfuse · Phoenix                        │
└─────────────────────────────────────────────────────────────┘

> ✅ = 薄适配已接进 fabric（真实 OSS 包可 `pip install` 后即时激活）。
> 行为引擎只需把 LLM base_url 指向 LiteLLM、把记忆/动手/观测调用路由到对应平面即可。
```

---

## 四、优先级建议（逻辑一致即可做）

1. **P0 — 推理网关 LiteLLM ✅ 已接入**：薄适配 `src/core/fabric/adapters/litellm_adapter.py` 接真实 LiteLLM（MIT），暴露 `inference.llm` 能力，AOS 的 LLM 调用统一走它；4 个行为引擎也可把 `base_url` 指向 LiteLLM 代理共享同一推理平面。这是"差点意思"的根，已补。
2. **P1 — 记忆/知识 Mem0 ✅ 已接入**：薄适配 `src/core/fabric/adapters/mem0_adapter.py` 接真实 `mem0ai`（MIT），暴露 `memory.semantic` / `memory.knowledge`，作为跨引擎共享的语义记忆/RAG 中枢（替代 DeerFlow 仅有的 TF-IDF）。
3. **P2 — 动手/ACI browser-use ✅ 已接入**：薄适配 `src/core/fabric/adapters/aci_browser_adapter.py` 接真实 `browser-use`（MIT），暴露 `action.aci` / `action.tool_use`，给所有引擎统一的"浏览器动手"能力（OpenClaw 是嘴耳、browser-use 是手）。
4. **P3 — 观测/护栏 Langfuse ✅ 已接入**：薄适配 `src/core/fabric/adapters/observability_langfuse_adapter.py` 接真实 `langfuse`（MIT，OpenTelemetry），暴露 `system.observability`，包裹所有引擎做 tracing / eval / guardrail，消掉"黑箱+静默失败"。

> 全部是真实开源、可 vendored，**不违反"必须真开源、不可自研"**。AOS 仍只做「提升层 +
> 接线板」，新平面同样以"薄适配"接入 fabric，引擎可替换。
