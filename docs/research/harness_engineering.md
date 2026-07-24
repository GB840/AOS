# harness-engineering 核实与可用方式（2026-07-24）

> 用户原描述：「harness-engineering：Demo 内容生成指南，快速做出能看的 Demo」。
> 经核实，用户给的 `harness-engineering/harness-engineering` 是**死链**；真实对应物有两个，均为 MIT、可用。
> 处置原则（用户铁律）：能商用开源 → 能用就用；不能用的才借鉴优化。

## 一、两个真实仓库（均 MIT，已核实）

### 1. haripery/harness-engineering —— 全栈 SaaS Boilerplate（Demo 起点）
- 语言：TypeScript（React+Vite 前端 / Express+TS 后端 / PostgreSQL）。
- 本质：**完全由 AI agent 编写的生产级全栈骨架**，内含一个现成的「自我文档化」Demo 落地页
  （Hero / Why This Exists / Get It Running / How It's Built 四板块），以及 Auth、Billing 示例领域模块。
- **它不是代码生成器**，不能按 prompt 自动产出任意 UI；但可直接 `git clone` 后改文案，作为产品 Demo 站起点。
- 用法（传统仓库，非 CLI 生成器）：
  ```
  git clone <repo-url>
  cd harness-engineering-saas
  cp .env.example .env
  npm install
  docker-compose up -d
  npm run db:setup
  npm run dev        # 前端 http://localhost:5180
  npm run validate   # typecheck+format+lint+test+structural+E2E
  ```
- **对护眼眼镜的用处**：护眼眼镜目前**无代码库**，等它有代码库（或要先做宣传 Demo 站）时，
  直接克隆此 boilerplate 改文案即可快速得到一个「能看的 Demo 站」，省去从零搭前端。

### 2. 10xChengTu/harness-engineering —— agent skill（强化 harness 层）
- 本质：**一个 agent skill**（"harness = AI agent 的 OS；model 是 CPU，上下文是 RAM，harness 是 OS"），
  教 AI agent 如何为任意项目搭建 / 维护 harness 层（AGENTS.md、docs/、lint 规则、约束、评估系统）。
- 许可：MIT（Agent Skills 规范，兼容 Claude Code / Cursor / Codex / Cline / Copilot 等 40+ agent）。
- 核心原则：Start simple，add complexity only when needed；Poor agent output 几乎总是 harness 问题而非 model 问题。
- 含 7 个 reference 模块：01-project-setup / 02-context-engineering / 03-constraints / 04-multi-agent /
  05-eval-feedback / 06-long-running / 07-diagnosis。
- 安装（给支持 skills 的 agent）：
  ```
  npx skills add 10xChengTu/harness-engineering/skills/harness-engineering
  npx skills add 10xChengTu/harness-engineering/skills/harness-engineering-zh
  ```
- **对 AOS 自身的用处**：AOS 已有极强的 AGENTS.md 宪法体系，此 skill 是「如何把 harness 搭得更好」的
  现成工程化知识，**已装入 AOS 项目级 skill**（`.workbuddy/skills/harness-engineering/SKILL.md`，仅入口，
  references 7 模块待从原仓补齐），强化我们的 harness 而非替代。

## 二、处置结论

| 仓库 | 类型 | 处置 | 落点 |
|---|---|---|---|
| haripery/harness-engineering | 全栈 Demo Boilerplate | 能用就用（护眼眼镜有库后克隆改文案） | 本文件标记 + 待护眼眼镜代码库 |
| 10xChengTu/harness-engineering | agent skill | 能用就用（已装 AOS 项目级 skill） | `.workbuddy/skills/harness-engineering/` |

> 注意：用户原贴的 `harness-engineering/harness-engineering` 不存在；`harness-engineering` 本是 OpenAI 2026-02
> 提出的「驭缰工程」范式，以上两个是其实质性开源落地。未把死链当事实写入。
