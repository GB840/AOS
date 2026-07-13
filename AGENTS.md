# AGENTS.md — AOS 宪法（Single Source of Truth）

> 本文件是 AOS 项目对所有 AI 编码工具（Claude Code / Cursor / Codex / Windsurf / Aider / Gemini CLI 等）
> 的**唯一权威规则源**。遵循 [agents.md](https://agents.md) 开放标准。
> IDE 专用规则（`.cursor/rules/*.mdc`、`.windsurfrules`）与 `CLAUDE.md` 均**引用**本文件，
> 不得与本文件冲突。改规则只改这一处。

---

## 0. 一句话定位

**AOS = 一个「单内核 + 多芯粒」的 agent 运行时。**
不是"更聪明的模型"，而是把 模型 + 工具 包成**可隔离、可编排、不绑定厂商**的流水线基础设施。
它的价值不在模型多聪明，而在：**多步编排 + 故障隔离 + 统一路由 + 端云合作**。

---

## 1. 命门哲学（违反即为"做歪了"，最高优先级）

这四条是 AOS 存在的理由。任何改动若违背，无论技术多漂亮，都是错的：

1. **万物为我所用** — 任何引擎/模型/工具都是可插拔的供给方，核心逻辑不依赖任何具体一家。
2. **端云合作** — 同一能力可由多个供给方提供；**云端优先 → 本地兜底**是路由层的机制，不是口号。
3. **一样用不了就换别样** — 云端挂了自动降级本地，一个源失败自动跳下一个，全程不中断。
4. **不绑定、零成本可跑** — 搜索、记忆、推理、绘图**全部有开源本地方案**，不充值也能端到端跑通。
   > 铁律：**永远不要因为"要花钱/要充值"而放弃一个能力**。先找开源/本地方案（ollama / sentence-transformers /
   > chroma / 百度·Bing HTML / AnySearch 等）。付费 key 只是"可选增强"，绝不能是"必需"。

---

## 2. 真架构（当前唯一运行时，勿再按 legacy 理解）

- **FabricHub 是唯一内核**，统一持有并调度：**路由 / 记忆 / 上下文主权**。谁都别自己乱管。
  - 代码：`src/kernel/plugins/fabric_hub.py`
- **Chiplet（芯粒）= 被调度的隔离计算单元**。重型/多模态引擎（agnes/ag2）默认跑在**独立子进程**，
  崩溃不传染宿主，可热备切换。这是"故障隔离（crash boundary）"，**不是**自治多 Agent 分解。
- **按能力（Capability）发现引擎，不按名字**。换任何引擎都不碰核心逻辑。
  - 代码：`src/core/fabric/capability.py`、`src/core/fabric/registry.py`
- **引擎无关契约**：所有适配器实现 `BaseAgentAdapter`（`src/core/fabric/adapter.py`）。
- **对外出口 = 标准 MCP server**（`src/mcp/protocol.py`）：`aos_list_engines / aos_route / aos_invoke_engine`。
- **编排器**：`OrchestrationChiplet`（`src/kernel/plugins/orchestration_chiplet.py`）真流水线执行器，
  `steps[]` 逐跳经 hub 路由，上一步输出喂下一步；支持 `parallel_groups` 组内并发。
- **think→do 闭环已收口**：`run_task(planner='ag2')` — ag2 规划文本 → 解析成带 `[AOS能力]` 标签的 steps → 逐跳执行。

**实际注册引擎名**：openclaw / litellm / mem0 / browser-use / langfuse / orchestrator / agnes / ag2 / web-search。
（CodeWhale / IMA / mistralrs / Page-Agent 是外部愿景，非当前注册名，不要在代码里当真实引擎引用。）

---

## 3. 反模式（血训，见到就改，别再犯）

- ❌ **路由只取 `providers[0]` 就停** — 必须遍历所有 live 供给方做故障转移（已在 `route()` 落地，勿回退）。
- ❌ **把能力焊死在付费远程 key 上** — 见哲学第 4 条。mem0 默认 `AOS_MEM0_LOCAL=1` 走本地。
- ❌ **虚报能力** — 适配器 `advertise_capabilities()` 只声明它**真能干**的（如 openclaw 只 `CHANNEL_ACCESS`）。
- ❌ **喂 legacy 双轨** — brain.py / deerflow / swarm_flow / hermes / lemon_orchestrator 是待退役老栈，
  与 FabricHub 互不打通。**新功能一律进 FabricHub**，不要往 legacy 加料。方向是灭双轨、以 FabricHub 为唯一运行时。
- ❌ **故障转移丢上游 data** — 全部失败时要返回最后一个供给方的真实结果（保留 trace/ok_steps），不能合成 `data=None`。

---

## 4. 诚实纪律（不可协商，用户会亲自复核）

1. **不弄虚作假**。真跑、贴可复核的原始证据（真实 stdout / 测试耗时 / git hash），不罗列结论蒙混。
2. **提交必当场核验**：`git commit` 后立刻 `git log -1 --format="%H %s"` 确认 hash 真进 git，再向用户报告。
   （曾虚报未落地的 hash，血训。）
3. **回应"虚"质疑铁律**：绝不辩解，直接真跑贴原始证据。常见误判根因＝**用户主机代码未同步**，须点出并给主机复现命令。
4. **先思考再编码**（Karpathy Agentic Engineering）：先说假设、亮取舍、给最简方案，再动手。见第 6 节。
5. **改动最小化（Surgical）**：只碰该改的，不顺手"美化"无关代码，不重构没坏的东西。每一行 diff 都能追溯到需求。

---

## 5. 开发规范（Qoder-style 规范库要点）

**运行环境（真机事实，照抄别猜）：**
- 跑代码/测试用系统 Python 3.14：`C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`
  + `PYTHONPATH=D:/AOS/src`。受管 3.13 venv 缺依赖不可用。
- `.env` 在 `D:\AOS\.env`（含真实 key，已 gitignore，**绝不提交**）。
- **git push 由用户主机 PowerShell 跑**（沙箱 egress 常 Empty reply）。沙箱与主机**共享同一 `.git`**，
  AI 的 commit 自动出现在主机仓库，**不需要 patch/`git am`**。流程：AI commit → 用户 `git push origin <branch>`。

**代码约定：**
- 语言 Python，包目录 `src/`，测试 pytest，linter/formatter 用 ruff，类型 mypy。
- 风格：PEP 8 + Google docstrings，行宽 120，import 顺序 stdlib→third_party→local。
- 命名：类 `PascalCase`，函数 `snake_case`，常量 `UPPER_SNAKE_CASE`，私有 `_lead`。
- 单例：模块级 `_instance` + `get_X()` 工厂。错误处理：log 到 WARNING，不静默崩溃。
- 禁止：`exec/eval` 用户输入、硬编码密钥、async 里阻塞、`print` 当日志、可变默认参数、`__init__.py` 里 import src。

**质量门（提交前自检）：**
- `ruff check src/ tests/` → 0 error
- `mypy src/ --ignore-missing-imports` → 0 error
- 相关子集 `pytest tests/<相关文件>` 全绿；不确定回归时跑更大范围。已知 legacy 债勿误修：
  `test_database::test_persistence_bridge_on_unified_db`、`test_memory`（no such table）——不 import fabric_hub，与新栈无关。

---

## 6. 工作法（Agentic Engineering，Karpathy「后 Vibe Coding」范式）

开发者是**编排者 + 审核者**，AI 代理负责具体实现。每个任务走四步协作闭环：

```
架构设计 → 任务拆解 → 代理执行 → 人工审查
   ↑                                      │
   └──────────── 不通过则回炉 ────────────┘
```

- **先思考再编码**：动手前先扒真实代码确认现状，别凭记忆写（记忆会骗人）。
- **追求简单**：能 50 行别写 200 行；不做没要求的抽象/配置/防御。
- **可验证目标**：把"修 bug"翻译成"先写复现测试→让它过"；强成功标准才能独立循环。
- **中文直白沟通**：给具体文件路径、可执行命令、真机验证结果，别堆术语长文档；能自己合理决定的先做。

---

## 7. 环境两座山（本地零成本启用，全免费）

- **记忆**：`ollama serve` + `ollama pull qwen2.5:7b nomic-embed-text`（或 `AOS_MEM0_EMBEDDER=huggingface` 走已装的
  sentence-transformers）。本机 sentence_transformers / ollama / chromadb 已装齐。
- **推理本地**：mistralrs / ollama 已在 wiring 设计好，启用即用。
- **绘图**：openclaw 是**本地自托管网关**（127.0.0.1:18789，MIT 免费）。`openclaw gateway run` 或 adapter 的
  `ensure_gateway()` 自起。openclaw dead 唯一根因＝网关没跑。
- **搜索**：AnySearch（免 key）+ 百度/Bing HTML（国内最稳）已多源兜底，不花钱。
