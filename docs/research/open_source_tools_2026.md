# 五个开源/外部项目参考（2026-07-24 核实版）

> 用途：用户评估一批 2026 年活跃的开源/外部项目，打算用于「护眼眼镜」产品方向，并要求入库。
> **重要**：本文所有条目均已联网核实（WebFetch + WebSearch，2026-07-24）。用户原始贴文中存在
> **2 个失效链接、1 处开源协议误判、1 处金额差 10 倍**。凡与用户原描述不符处，均在「核实纠正」中标注，
> 不把未核实内容当事实写入。

## 0. 总表（核实后）

| # | 项目 | 真实/可核实地址 | 协议 | 核实状态 |
|---|------|----------------|------|----------|
| 1 | self-learning-skill | github.com/philschmid/self-learning-skill | Apache-2.0 | ✅ 真实（URL 单数，非 skills） |
| 2 | moai-adk | github.com/modu-ai/moai-adk | Apache-2.0 | ✅ 真实 |
| 3 | screenpipe | github.com/screenpipe/screenpipe | **Screenpipe Commercial（源码可见，非纯开源）** | ✅ 真实（协议被用户误判为「开源免费」） |
| 4 | Flawless（K8s 观测） | github.com/William-Lu-stack/Flawless | 源码可见非商用 | ✅ 真实（用户给的 flawless-ai/flawless 是电影 AI 公司，404） |
| 5 | harness-engineering | 概念源于 OpenAI「驭缰工程」；仓库 haripery/harness-engineering（MIT）、10xChengTu/harness-engineering | MIT | ✅ 真实（用户给的 harness-engineering/harness-engineering 404） |

---

## 1. self-learning-skill

- **核实地址**：https://github.com/philschmid/self-learning-skill （注意是单数 `skill`，不是 `skills`）
- **协议**：Apache-2.0
- **真实能力**：一个「自主 skill 生成器」——通过 `/learn <topic>` 从网络权威文档检索某库/框架/工具，
  综合成可复用的 skill（Markdown）存入工作区。灵感来自 hyperbrowserai/examples/skills。
- **用户原描述**：「让 AI 记住成功路径，避免重复踩坑，把成功代码策略存为可复用技能，Markdown 存储，集成 Claude Code/Cursor」。
- **核实纠正**：
  - 同一家族（可复用 skill），但机制不同：它偏「**学新技术→生成 skill**」，不是「**记住自己过去的成功**」。
  - 集成写的是 Claude Code / Cursor / Gemini(antigravity) 风格路径，未明确提 Cursor，但 Agent Skills 格式通用。
- **对护眼眼镜的用处（用户视角 + 补充）**：
  - 用户：让 AI 编程助手记住护眼眼镜开发的成功经验，避免重复踩坑。
  - 补充：更直接的用法是「/learn 某个硬件 SDK / 某个国产模型 API」→ 自动沉淀成团队可复用的护眼眼镜开发知识库；
    与 AOS 已有的 `skills/manifest.json` 技能生态可互补。

## 2. moai-adk

- **核实地址**：https://github.com/modu-ai/moai-adk
- **协议**：Apache-2.0
- **真实能力**：面向 Claude Code 的 **SPEC-First Agentic Development Kit**（Go 单二进制、零依赖）。
  核心是「Tokenomics 外层 harness」——用 plan→run→sync 三阶段 + TRUST 5 质量门（Tested/Readable/Unified/Secured/Trackable）
  + TDD/DDD 默认质量门，让 token 消耗可预测、代码可靠。标题称 24 AI agents / 52 skills；正文定义为 **11-Agent Catalog**
  （10 自定义 + Explore）。支持 16 种语言项目、4 种语言文档（en/ko/ja/zh）。已支持 Claude Code + GLM 混合模式。
- **用户原描述**：「先写规范再写代码，24 个专业 AI 助手，52 个内置技能，TDD/DDD 质量门，16 语言，Go、零依赖，集成 Claude Code/Cursor」。
- **核实纠正**：
  - 「24 AI 助手」与正文「11-Agent Catalog」数量表述不一致（以标题营销口径 vs 实际目录）。
  - 只明确提 **Claude Code**（及 GLM 混合），**未提 Cursor**。
- **对护眼眼镜的用处（用户视角 + 补充）**：
  - 用户：规范护眼眼镜代码质量，确保可维护、可扩展。
  - 补充：其「**预算熔断 / 验证节食**」思路正好对应 AOS AGENTS.md §2.5 的「成本硬停」与「每步真实闸门」，
    可作为护眼眼镜代码库 + AOS 自身的工程化质量门参考。

## 3. screenpipe

- **核实地址**：https://github.com/screenpipe/screenpipe
- **协议**：**Screenpipe Commercial License（源码可见；个人非商用免费；商用需授权）**——**不是纯开源**，2026-06-10 起统一为单一商业许可。
- **真实能力**：Rust/Tauri 桌面应用，24/7 **本地**录屏 + 音频转录，转成可被 AI 检索的「工作记忆」。
  事件驱动截屏（无障碍树 + OCR 兜底）、Whisper/Deepgram 转录、SQLite FTS5 全文检索、时间线回看、
  Pipes 插件系统、MCP Server（供 Claude/Cursor 查历史）、Local AI（Ollama）支持。多平台：macOS/Windows/Linux。
  资源：CPU 5–10%，RAM 0.5–3GB，存储 ~20GB/月，可离线。
- **用户原描述**：「24 小时录屏喂给 AI，解决上下文缺失；Rust；本地优先隐私；Ollama 集成；插件系统；多平台」。
- **核实纠正**：
  - 描述**完全吻合**，但「开源免费」不准确——它是 **source-available 商业许可**，商用要授权/付费。
- **对护眼眼镜的用处（用户视角 + 补充）**：
  - 用户：记录护眼眼镜开发的所有操作，给 AI 提供完整上下文。
  - 补充：也适合做**产品演示/用户研究录制**（护眼眼镜面向 C 端，录屏复盘用户使用路径很有价值）；
    但商用前需确认 Screenpipe Commercial License 的授权范围。

## 4. Flawless（Kubernetes AI 观测 / SRE 控制平面）

- **核实地址**：https://github.com/William-Lu-stack/Flawless （公开产品名 Flawless，早期曾用 LuxyAI 组织名）
- **协议**：源码可见非商用许可（**非 OSI 认证开源**）
- **真实能力**：AI-Native **SRE 控制平面**，面向 Kubernetes 与云基础设施。AgenticOps 闭环：
  `discover → diagnose → preview → approve → execute → verify → learn`。
  关键设计：**把执行边界留在平台层**——RBAC、dry-run、人工授权闸门、审计日志、恢复验证都在模型之外；
  「验证恢复」要求执行后复测原始症状，而非把「命令成功」当「修复成功」（与 AOS §2.5「真实闸门」同源思想）。
  含拓扑/CMDB 影响面分析、Skills 库、运维 RAG 知识库。Python 3.14 后端 + TypeScript 前端，2026-07-10 新建、~616★。
- **用户原描述（链接 flawless-ai/flawless）**：「AI 观测 K8s 集群，自动发现问题、自动响应、自动重启 Pod/调资源」。
- **核实纠正**：
  - 用户给的 `flawless-ai/flawless` **404**——那是**电影/电视辅助 AI 公司 Flawless AI**（TrueSync/DeepEditor），与 K8s 无关。
  - 真正的 K8s Flawless 是 `William-Lu-stack/Flawless`，能力描述基本对得上，但它是「**带人工授权闸门的可审计闭环**」，
    不是「全自动无干预」（用户描述略去了审批/安全边界，实际项目反而强调 guarded remediation）。
- **对护眼眼镜的用处（用户视角 + 补充）**：
  - 用户：护眼眼镜若做云端服务、多设备管理，用 Flawless 自动监控集群、省人工维护。
  - 补充：**直接复用价值有限**（护眼眼镜短期未必上 K8s 集群），但其「**人工授权 + 可验证恢复 + 经验沉淀**」三件套，
    是 AOS 自主执行安全边界的绝佳参考范式——建议在 AOS autopilot 的「出门检/假反思拦截」里吸收。

## 5. harness-engineering（驭缰工程）

- **概念源**：**Harness Engineering / 驭缰工程**——OpenAI 于 2026-02 公开提出的工程范式：
  工程师不再以「写代码」为主要产出，而是「设计环境、明确意图、构建反馈回路」，让 AI 可靠地完成工作。
- **核实仓库**：
  - `github.com/haripery/harness-engineering`：完全由 AI agent 构建的 full-stack boilerplate（分层架构、Zod 校验、
    双 MCP 验证工作流、DEMO hero 区、300 行文件上限），MIT。
  - `github.com/10xChengTu/harness-engineering`：一个 agent skill，用于搭建/改进 harness 层
    （AGENTS.md / docs/ / lint 规则 / eval 系统），双语，兼容 40+ agent 工具。
- **用户原描述（链接 harness-engineering/harness-engineering）**：「Demo 内容生成工程化指南，自动生成 Demo 文字/图片/视频/界面，一键完成」。
- **核实纠正**：
  - 用户给的 `harness-engineering/harness-engineering` **404**。
  - 「Demo 内容生成」是松散概括：haripery 仓库是 **boilerplate 工程**，不是「文字/图片/视频自动生成器」；
    更接近「用 AI agent 一键起一个能跑的 Demo 工程」。
- **对护眼眼镜的用处（用户视角 + 补充）**：
  - 用户：做护眼眼镜 Demo、宣传视频、产品演示时快速生成内容与界面。
  - 补充：真正值得借的是**驭缰工程思想本身**——给护眼眼镜代码库配 `AGENTS.md` 约束层 + 校验层 + 反馈回路，
    比「换更大模型」更能稳定产出；这与 AOS 的 `AGENTS.md` 宪法（本项目即此文件范式）完全一致，可直接复用。

---

## 附：失效/纠错链接对照

| 用户原链接 | 状态 | 正确去向 |
|------------|------|----------|
| github.com/flawless-ai/flawless | 404（电影 AI 公司，非 K8s） | github.com/William-Lu-stack/Flawless |
| github.com/harness-engineering/harness-engineering | 404 | github.com/haripery/harness-engineering 或 10xChengTu/harness-engineering |
| github.com/philschmid/self-learning-skills（复数） | 实际为单数 | github.com/philschmid/self-learning-skill |

> 提醒：凡引入外部依赖/框架/模型，按 AOS 铁律须先全网核实。本文即一次核实存档，后续若真要接入，
> 仍需针对「是否引入依赖」「许可证是否允许商用」再做一轮决策（尤其 screenpipe 商业许可、Flawless 非商用许可）。
