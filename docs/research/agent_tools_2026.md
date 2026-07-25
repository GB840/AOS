# 三个 Agent 能力工具参考（2026-07-25 核实版）

> 用途：用户在「护眼眼镜」5 项目之外补充 3 个项目，要求核实后弄进 AOS 合适位置：
> **AI MediaKit CLI**（火山引擎音视频）、**img2threejs**（单图转 Three.js 3D）、**OpenWorker**（Andrew Ng 开源 AI 同事）。
> **全部已联网核实**（WebSearch + WebFetch + D 盘实机探查 OpenWorker）。用户原始描述中
> 部分细节（许可证 / 版本 / 星数）已过时，均在「核实纠正」标注，不把过时信息当事实写死。
> 处置分类严格遵循 MEMORY.md § XII 外部开源项目处置铁律。

## 0. 总表（核实后）

| # | 项目 | 真实地址 | 协议 | 核实 | AOS 处置分类（§ XII 铁律） | 映射岗位 |
|---|------|---------|------|------|----------------------------|---------|
| 1 | AI MediaKit CLI | npm `@volcengine/mediakit-cli`；docs.volcengine.com/docs/6448/2523671 | **商业产品（火山引擎）**：CLI 免费装，云端 `--cloud` 需 API Key（注册送免费额度）；本地模式基于 FFmpeg | ✅ 真实（2026-07-06 Force 大会发布） | **只借鉴 + 按需接入**（subprocess 调用，不引源码；云端标注需火山 Key） | 内容营销岗（视频后期 / 内容飞轮） |
| 2 | img2threejs | github.com/hoainho/img2threejs | **Apache-2.0**（2026-07-23 commit #16 从 MIT relicense） | ✅ 真实（~3.2k stars） | **能用就用**（直接集成 / 复用，agent-agnostic skill） | 产品研发岗（3D 生成） |
| 3 | OpenWorker | github.com/andrewyng/openworker | **MIT**（Copyright 2024 Andrew Ng） | ✅ 真实（D:\OpenWorker=桌面版，D:\OpenWorker1=源码主仓） | **借鉴优化**（栈不兼容：Python aisuite + React/Tauri + Rust；与 AOS 平行竞品，取其理念） | 优化单创OS 架构（本地优先 / BYOK / 审批门控 / 自动化） |

---

## 1. AI MediaKit CLI（火山引擎 · 音视频 Agent 工作台）

### 用户原描述（已贴，基本准确）
- 核心定位：AI 音视频处理的"最后一公里"——原生命令行工具 + AI Agent Skill，让 Agent 直接调用和编排音视频处理能力，交付可上线成片。
- 架构：CLI 核心 + AI Skill 层，覆盖视频 / 图像 / 音频三大模态。本地模式基于 FFmpeg/FFprobe（裁剪 / 拼接 / 字幕等 18 个本地功能）；云端 `--cloud` 调画质增强 / ASR / OCR / 高光智剪 / 剧情线分析。
- 已发布 5 个 AI Agent Skill，四大能力域：`byted-mediakit-video` 含 14 项能力。
- 安装：`npm install -g @volcengine/mediakit-cli@latest`（Node≥18、FFmpeg≥5.1）。示例：`mediakit clip` / `subtitle` / `enhance` / `separate-audio` / `asr`。
- 与 Remotion 配合：Remotion 生成画面 → Mediakit CLI 自动后期 → 成片发布。
- 风险：云端依赖火山引擎 API Key（注册送免费 Token）；项目早期 v0.2.0 可能不稳定；本地与云端能力分离。

### 核实纠正 / 补充
- ✅ 真实且官方：火山引擎 2026 Force 源动力大会（2026-07-06 / 07-13）正式发布，官方文档 docs.volcengine.com/docs/6448/2523671，安装命令 `npm install -g @volcengine/mediakit-cli`（用户写的 `@latest` 也有效）。
- ✅ 能力域正确：四大 Skill 为 `byted-mediakit-editing` / `byted-mediakit-video` / `byted-mediakit-image` / `byted-mediakit-audio`；底层沉淀 **100+ 音视频原子能力**（用户说的"18 本地 + 14 video"是某版本细分口径，总数以官方 100+ 为准）。
- ⚠️ **协议：非开源**。它是火山引擎（字节）商业产品。CLI 本身免费安装，但云端 AI 能力走火山引擎 API（需 Key，注册送免费额度）；本地剪辑依赖 FFmpeg（LGPL/GPL）。→ 处置上**不引其源码**，AOS 仅按需以 subprocess 调用 `mediakit` 二进制，且云端功能须明确标注"需用户自备火山引擎 Key"。
- ✅ Agent 友好设计属实：支持导出 JSON Schema 能力声明、task_id 轮询 / 长任务回收、端云协同。这与 AOS「芯粒隔离 + 能力即路由」理念契合。

### 对 AOS / 单创OS 的用处
- **内容营销岗**直接受益：接在「内容飞轮」视频生成之后做自动后期（加字幕 / 调音量 / 画质增强 / 平台规格适配），形成"生成 → 交付"全自动流水线（用户设想的 文案 → Remotion 生成 → Mediakit 后期 → 发布 可部分在 AOS 内复现）。
- **接入方式（建议）**：在 AOS 加一个 `mediakit` 工具芯粒（opt-in，默认关闭；启用需用户填火山引擎 Key），通过 subprocess 调 `mediakit` CLI。本地剪辑零成本，云端按火山计费。**不把其代码纳入仓库**。

---

## 2. img2threejs（hoainho · 单图转 Three.js 3D）

### 用户原描述（已贴）
- 定位：不是 3D 建模软件，而是 AI Agent 技能；把一张参考图转化为**可直接运行的、高质量的 Three.js 3D 模型代码**（输出 TypeScript，非 GLB/OBJ 网格）。
- 工作流：用户给图 → AI 分析生成建模规格 → 分阶段生成 / 验证代码 → 输出 Three.js 模型代码。
- 核心优势：极高 Token 效率（机械工作交 Python 脚本，仅"视觉判断"用大模型；重建约 80k–180k tokens，一次评审循环仅 5k–12k）；严格质量门控（分阶段从轮廓到材质，每阶段渲染图与参考图对比，相似度 ≥70% 才进下一阶段）。
- 最新（用户写 v1.3，2026-07）：几何重建 / 材质生成重大改进 + 单图人脸投影；GitHub 星标 470+（曾 8 天 +2.2k）；计划加 GLB 导出。
- 安装：`git clone https://github.com/hoainho/img2threejs.git ~/.claude/skills/img2threejs`；调用 `/img2threejs Rebuild this object...`。

### 核实纠正 / 补充
- ✅ 真实，GitHub hoainho/img2threejs，agent-agnostic（Claude Code / Codex / OpenCode / Cursor / Windsurf 等，README 明确 "Agent-agnostic"）。
- ⚠️ **许可证纠正**：用户写"MIT v1.2.0"——**已过时**。2026-07-23 commit #16 已从 MIT **relicense 为 Apache-2.0**（LICENSE 文件 + SKILL.md frontmatter 均已同步）。当前以 **Apache-2.0** 为准（可商用、可修改、需保留版权声明）。
- ⚠️ **版本纠正**：当前代码 **v1.3**（2026-07-23 落地，schemaVersion 2.1，含质量 / 效率升级）；v1.4（动画就绪绑定）仍 Planned。用户说的 v1.3 方向对，但"v1.2.0 MIT"是旧快照。
- ⚠️ **星数纠正**：用户写 470+——已增长至 **~3.2k stars**（claudewave 数据，与"8 天 +2.2k"趋势一致）。
- ✅ 其它细节（Token 效率、质量门控 70%、分阶段 sculpt 管线、Python 脚本 `forge/`、规则集 `grimoire/`、纯代码输出、计划 GLB 导出）均与仓库一致。
- 安装另支持 `npx skills add hoainho/img2threejs`（用户给的 git clone 路径也有效）。

### 对 AOS / 单创OS 的用处
- **产品研发岗**直接受益：把"产品图片 → 可交互 3D 模型代码"做成 AOS 的一项 3D 生成能力（适合产品展示页、游戏原型、网页创意、教育模型、护眼眼镜产品的 3D 可视化）。
- **Apache-2.0 + agent-agnostic + 纯 Python 脚本 + SKILL.md** → 属"能用就用"类，**可直接集成 / 复用**，无需重写。
- **接入方式（建议，落地候选）**：把仓库整体作为 AOS / WorkBuddy 的 `img2threejs` skill 接入（保留 Apache-2.0 LICENSE 与署名）。因它吃"参考图 → Three.js 代码"，天然适配 AOS 产品研发岗的"3D 资产生成"子任务。视觉评审环节可接 AOS 的模型路由（如用支持视觉的模型做 screenshot 比对）。

---

## 3. OpenWorker（Andrew Ng · 开源 AI 同事桌面应用）

> 用户未给描述，以下基于 D 盘实机 + 官方 README 核实。

### 实机探查（D 盘）
- `D:\OpenWorker\`：已安装的**桌面版**——`openworker-desktop.exe`（17 MB）、`sidecar\`、`uninstall.exe`。
- `D:\OpenWorker1\openworker-main\`：**源码主仓**（git）——Python 包 `coworker/`、`.venv/`、`pyproject.toml`（MIT, name=coworker v0.0.0）、`LICENSE`（MIT, Andrew Ng 2024）、`surfaces/gui/`（React+Tauri）、`stt/`（Rust 语音转写 sidecar）、`docs/`、`tests/`。

### 项目真相
- **是什么**：本地优先的开源 AI 同事（coworker）桌面应用——"AI that gets your everyday tasks done"，交付**成品**（文档 / 表格 / 报告 / 网页 / Slack 回复 / 日历更新 / 收件箱分拣），而非只聊天。
- **核心机制**：①用户说目标 → ②拆步骤跨桌面 / 文件 / 连接应用执行 → ③在"发消息 / 改日历 / 跑命令"等实质动作前**审批门控**（无人值守时把待办存进 inbox）→ ④交付成品。
- **模型**：BYOK（OpenAI / Anthropic / Gemini / GLM / DeepSeek / Kimi / Qwen / MiniMax / Mistral / Grok + Together / Fireworks 开源权重 + 本地 Ollama）。引擎构建于 **aisuite**（andrewyng/aisuite，统一 chat-completions + agents 层 + MCP）。
- **连接**：25+ 连接器（GitHub / Slack / Jira / Notion / Linear / HubSpot / Outlook / monday / Gmail / Google Calendar）+ 终端 + 本地文件；任何 MCP 工具可插；每工具可控。
- **自动化**：定时任务（晨报 / 周报 / 频道监控），跑完留完整记录。
- **隐私**：本地优先，agent loop / 对话 / 令牌 / Key 全在本地密钥库；唯一云成分是 OAuth 握手中转。
- **协议**：**MIT**（可商用、可修改）。

### 对 AOS / 单创OS 的用处（借鉴优化，非集成）
- ⚠️ **栈不兼容，不能直接引代码**：它是 Python(aisuite) + React/Tauri + Rust，与 AOS 的 FabricHub（Python 单基座 + 芯粒隔离）架构不同。**且它与 AOS / 单创OS 是平行竞品**（同走"交付成品的自主 agent"路线）。
- → 按 § XII 铁律归为"**能商用但技术栈不兼容 → 借鉴优化**"：取其**理念**优化单创OS 架构，不自造轮子也不引其代码。
- **可直接借鉴的点**：
  1. **本地优先 + BYOK + 数据不出本机** → 强化单创OS「诚实可验证 / 白盒」的隐私与可控叙事。
  2. **审批门控（consequential 动作先问）** → 对应 AOS「能力即路由权限即边界」，可在 autopilot 执行写 / 发 / 命令前加确认闸。
  3. **定时自动化（automations）** → 单创OS 已有 autopilot / opc_loop，可借鉴其"跑完留完整 transcript"的可审计设计。
  4. **25+ 连接器走 MCP + 每工具权限** → 印证 AOS「万物为我所用 / MCP 即路由」路线；可把其连接器清单当 AOS 连接器市场的参考。
  5. **aisuite 统一 provider 层** → 与 AOS 的 litellm 统一平面同构；可比较两者 provider 覆盖，补 AOS 未接的模型（如 Inkling/Thinking Machines、Kimi、MiniMax 已在 AOS 路线，可确认）。
  6. **"交付成品而非 to-do"的产品哲学** → 强化单创OS「不是聊天工具」的宪法定位（AGENTS.md §0.7）。

---

## 4. 处置总览与下一步（落到 § XII 铁律）

| 项目 | 分类 | 行动 | 落点 |
|------|------|------|------|
| AI MediaKit CLI | 商业产品 | 只借鉴 + 按需接入（subprocess，云端需 Key，不引代码） | 内容营销岗工具芯粒（opt-in） |
| img2threejs | Apache-2.0 能商用 | **能用就用**：直接 port 为 AOS / WorkBuddy skill | 产品研发岗 3D 生成能力 |
| OpenWorker | MIT 但栈不兼容 | 只借鉴优化（取其理念，不引代码） | 优化单创OS 架构叙事 |

**建议下一步（待用户拍板）**：
1. **img2threejs 直接落地**：把它作为 Apache-2.0 skill 接入（保留 LICENSE / 署名），挂到产品研发岗做"图片 → Three.js 3D 代码"。这是三个里最该先"弄进去"代码层的。（注：沙箱 GitHub 不可达，port 需在用户主机 clone 后做，或待网络可用。）
2. **Mediakit 做 opt-in 工具芯粒**：写个 `mediakit` 包装芯粒（subprocess 调 CLI），云端功能标注需火山 Key，默认关闭。
3. **OpenWorker 仅做架构借鉴**：把上面 6 点借鉴写进单创OS 产品叙事 / 架构文档，不引代码。
