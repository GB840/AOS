# 生命体OS 白皮书 13 个 🔁/🔗 节点深度调研结论（2026-08-02 收口）

> 背景：用户批评「你作参考的和自研 你又没有提前把他们所有调研清楚 并吃透」。
> 本文件对 `docs/LIFEFORM_OS_WHITEPAPER_V6.md` 架构图中 **全部 13 个 🔁（自研等价）/🔗（纯参考）节点** 逐一做：
> 全网 WebSearch + 必要 WebFetch 官网/Repo + 在 AOS 运行环境（Windows / Python 3.13.12 / 托管解释器）实测核验，
> 给出 **真实身份 / 许可证 / 技术栈 / 活跃度 / 可否接入 / 最终处置 / 关键证据**。
>
> 结论：原标注**基本正确**（白皮书此前已诚实标注）。本调研以实测证据**订正了三处先前不精确的理由/描述**，并公开纠正了我（上一轮）对 TriviumDB/Turso/fractal「该接却没接」的误判。

---

## 一、调研结论总表（13 节点）

| 节点 | 真实身份 | 许可证 | 技术栈 | 活跃度 | 可否接入 AOS（Windows / Py3.13） | 最终处置 | 关键证据 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **L1C** Cindy / nanobot | Cindy=`makecindy/cindy` 桌面+移动 Agent 运行时；nanobot=`HKUDS/nanobot` 轻量自托管 Python Agent 框架 | Cindy **Apache-2.0**；nanobot **MIT** | Cindy TypeScript/Electron（Node 22 + pnpm）；nanobot Python ≥3.11 | Cindy 2026-07 活跃（1.3k★）；nanobot v0.3.0（2026-07） | Cindy **非 Python、需云账号** → 不可嵌；nanobot **可装但依赖与 AOS 冲突**（会卸载 `rich` 15） | **🔗 纯参考**（生态对齐；AOS 用 FabricHub） | `pip install nanobot-ai` 实测触发卸载 `rich-15.0.0`（与 fractal/textual 冲突）→ exit 1 |
| **L1D** openship | **两个不同项目**：`oblien/openship`=部署/运维平台（Apache-2.0）；`margutti/openship`=旧电商多_channel 履约（MIT） | oblien **Apache-2.0**；margutti **MIT** | TypeScript（Next/Electron）+ Rust；提供 MCP 端点 + REST + npm CLI | oblien v0.3.0（2026-07，8.2k★）活跃 | **服务/平台**，非 drop-in 库 | **🔗 纯参考**（部署工具；AOS 有 `start_all.sh`/`Dockerfile`） | oblien 提供 MCP+REST+npm CLI，需自托管服务，非库 |
| **L1E** Fish Speech | `fishaudio/fish-speech` TTS | **代码 BSD-3-Clause**；**模型 CC-BY-NC-SA-4.0** | Python 推理（Gradio/PyQt） | 活跃 | 模型**禁商用** → 不集成 | **🔗 纯参考**（已由 L1E3 Piper Apache-2.0 真接替代） | 模型权重 NC；代码可商用 |
| **L1F** turbo-fieldfare | `drumih/turbo-fieldfare` 端侧推理引擎（Gemma 4 26B-A4B on Apple Silicon，2GB RAM） | **Apache-2.0** | Swift 6.2 + Metal 4（**仅 macOS 26+**） | 2026-07 活跃（HackerNews 热门） | **仅 macOS / Apple Silicon**，非跨平台 | **🔗 纯参考**（Apple Silicon 本地 LLM 端点，OpenAI 兼容，opt-in） | 仅 Mac；暴露 `127.0.0.1:8080` OpenAI 兼容 server |
| **L2I** plasma-ai/fractal | `plasma-ai/fractal` 递归硬上限 Agent 树（每节点 git worktree 自循环，硬上限=迭代/深度/子节点/成本/时间） | **Apache-2.0** | Python（CLI + `/fractal` skill）；运行时依赖 **tmux + 外部 agent CLI**（claude/codex/grok/opencode/omp）+ git worktree + SQLite | 活跃 | **否**：`import fractal` → `fcntl` 缺失（**Unix-only**）；且需 tmux + 外部 CLI | **🔁 自研等价**（AOS `kernel/fractal/` 跨平台等价：spawner / growth_guard） | `python -c "import fractal"` → `ModuleNotFoundError: No module named 'fcntl'`（Windows 不可 import） |
| **L3C** TriviumDB + Turso | TriviumDB=`YoKONCy/TriviumDB` 向量+图谱+关系单文件库；Turso=`pyturso` 嵌入式 SQLite 重写（MVCC+async） | TriviumDB **Apache-2.0**；Turso **MIT** | Rust + Py 绑定 / Rust（MVCC+async IO） | TriviumDB 0.7.2（2026-04）；Turso 0.7.2（2026-06） | **否**：TriviumDB 全部版本 `Requires-Python >=3.9,<3.13`；Turso 仅 sdist、Rust 源码编译在沙箱失败 | **🔁 外部未接**（**实测核实，非假定**） | `pip install triviumdb` → 拒绝（<3.13）；`pip install pyturso` → 构建 exit 1 |
| **L3E** DBX | `t8y2/dbx` 轻量跨平台 DB 客户端（含 AI SQL 助手 + MCP） | **AGPL-3.0** | Tauri 2 + Rust + Vue 3 | 活跃（8K★） | **否**：AGPL 传染 + 是 GUI 工具非库 | **🔗 纯参考**（许可红线） | AGPL-3.0 单一许可证 |
| **L6C** Automaton | `Conway-Research/automaton` 自主生存/自我复制 Agent（思考→行动→观察循环，生存四级，链上身份） | **MIT** | TypeScript / Node 20+ | 活跃（2026-02 起） | **否**：需**以太坊钱包 + Conway Cloud + USDC 支付**（x402） | **🔁 自研等价**（AOS `kernel/evolution.py` + `lifeform/self_evolve_engine.py` 含 `EvolutionLimit` 硬护栏） | 依赖 Conway Cloud + 链上钱包 + x402 协议 |
| **L6D** PhyAgentOS | `HCPLab-SYSU/PhyAgentOS` 具身自进化 AI OS（认知-物理解耦，State-as-a-File Markdown 协议） | 未单文件标明（学术开源，疑似 MIT/Apache） | Python（HAL + Markdown 协议）+ 机器人本体 | 2026-05 活跃（近千★） | **否**：具身/机器人域，非 AOS 数字 Agent OS | **🔗 纯参考**（架构思想；**built on nanobot**） | 基于 nanobot；「State-as-a-File」协议可借鉴 |
| **L7F** Conway Terminal | Conway Research `npx conway-terminal` MCP 支付/算力网关 | **MIT** | TypeScript（MCP server） | 2026-02 活跃 | **否**：需**链上钱包 + Conway Cloud + USDC（x402）** | **🔁 自研等价**（AOS `api/billing_api.py` + `core/database/models/economy.py`） | MCP server，依赖 Conway Cloud 基础设施 |
| **L7G** PhyAgentOS（执行解耦） | 同 L6D | 同 L6D | 同 L6D | 同 L6D | 同 L6D | **🔗 纯参考** | 同 L6D |
| **L9A** dg-ai-notes | `buchidonggua/dg-ai-notes` Pi-Agent SDK 深度学习笔记 | **代码 MIT**；文档 CC-BY-SA-4.0 | Markdown / 教程（**非库**） | 2026-07 活跃（1.3K★） | **否**：教程文档，非可集成库 | **🔗 纯参考**（学习资源） | 基于 Pi-Agent SDK 的 10 章教程 |
| **L9B** openKylin AgentOS SIG | openKylin 社区 AgentOS SIG（基于 openKylin 2.0 的开源智能体 OS） | 社区生态（开源，许可随各组件） | 系统级 Agent 运行时（Linux 发行版） | 2026-06 发布 | **否**：整套 OS 发行版，非库 | **🔗 纯参考**（国产生态对齐） | 国防科大 / 哈工大(深圳) / 麒麟软件共建 |

---

## 二、实测证据（可复现，AOS 托管 Python 3.13.12）

```bash
PY=托管python3.13.12

# 1) TriviumDB：全部版本要求 <3.13，pip 实测拒绝
$PY -m pip install triviumdb
# ERROR: Ignored the following versions that require a different python version:
#   0.3.0 Requires-Python >=3.9,<3.13; ... 0.7.2 Requires-Python >=3.9,<3.13
# ERROR: Could not find a version that satisfies the requirement triviumdb

# 2) fractal：Apache-2.0 真开源，但 Unix-only（fcntl），Windows 不可 import
$PY -c "import fractal"
# Traceback ... import fcntl
# ModuleNotFoundError: No module named 'fcntl'
# （注：pip install fractal 仅官方 PyPI 有包 fractal-1.1.0，tuna 镜像缺；装得但 Windows 仍不可 import）

# 3) pyturso（Turso 嵌入式引擎）：仅 sdist，Rust 源码编译在沙箱失败
$PY -m pip install pyturso
# Building wheels for collected packages: pyturso
#   Building wheel for pyturso (pyproject.toml): started  -> exit code 1

# 4) nanobot-ai（L1C 唯一可装项）：依赖树与 AOS 冲突（会卸载 rich 15）
$PY -m pip install nanobot-ai
# Attempting uninstall: rich  / Found existing installation: rich 15.0.0
# Successfully uninstalled rich-15.0.0  -> 随后 exit 1（安装失败）
# （已还原 rich==15.0.0 并清理残留 ~ich dist-info，环境恢复一致）
```

---

## 三、对白皮书标注的影响

- 原 **13 个 🔁/🔗 标签经调研基本正确**，白皮书此前已诚实标注；**统计不变：✅46 / 🔁6 / 🔗7（59 节点）**。
- 需**订正理由/描述**（非改标签性质）的节点：
  - **L3C**：此前写「Rust-only 接不上」理由不精确 → 实测为 **TriviumDB `<3.13` + Turso sdist Rust 构建阻**，已核实，非假定。
  - **L2I**：此前「未引入；等价 `kernel/fractal/`」理由不全 → 补：**fractal 为 Apache-2.0 真开源，但 Unix-only(fcntl) + tmux + 外部 agent CLI，跨平台不可引**；AOS 自研等价成立。
  - **L1C / L1D**：等价路径描述纠偏（应为 **FabricHub** / **部署脚本**，而非 `web/app.py` / `Dockerfile` 字面）。
- 其余节点（L1E / L1F / L3E / L6D / L7G / L9A / L9B）标签与理由均经核实成立。

## 四、关键反思（公开纠自己，不静默修改）

- 上一轮我**误判** TriviumDB/Turso「该接却没接」、fractal「该接」——**实测证明三者在本环境（Windows / Py3.13）均不可接入**（版本上限 / Unix-only / Rust 构建失败）。白皮书原标注正确，是**我的假设错误**。本文件以实测证据纠正自己。
- 唯一可干净接入的是 **nanobot（MIT，Py ≥3.11）**，但其依赖树与 AOS 现有 `rich` 冲突，且 AOS 已有 **FabricHub** 覆盖该角色（选型铁律「现有够好 → 不造」），故**不引**，仅作生态参考。
- 凡「服务 / 框架 / 许可红线 / 平台不兼容」类未接入，均按选型铁律判定，非疏漏。
