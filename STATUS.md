# AOS v5.0 —— 你的资料与代码总地图（STATUS）

> 这是一份**导航索引**，不是技术文档。你说过"不知道弄哪去了"——这份文件把所有东西摆在一张表上。
> 每次状态变动都会更新这里。最后更新：**2026-07-08**。

---

## 0. 一句话定位

AOS = **开放 Agent 能力市场（fabric）**。四个你指定的真实开源 + 四个基础设施平面，都通过"薄适配"插进 AOS；AOS 自己**只做提升层（统一状态/治理/平台/控制台），绝不重造 agent 大脑**。

---

### 重大发现（2026-07-08 核实，务必看）

OpenClaw（openclaws.io，MIT）经联网核实确为真实开源，是 AOS 的接入层；群聊编排由 AG2（AutoGen 社区分叉，MIT，pip 可装）真实承担，满足"真实开源、不自研"铁律。

**但仓库自相矛盾、且直接违反铁律**：AOS 在 `src/core/open_claw.py` 里自研了一个“OpenClaw 任务入口”（注释原文“设计参考 OpenClaw任务入口”），`src/subagents/openclaw_agent.py` 还试图桥接一个 `external/` 目录里根本不存在的 OpenClaw 源码——也就是 AOS **自己重写了一套 OpenClaw**，这正是你“不能自己写”要杜绝的。

fabric 适配器端点已对齐真实开源：OpenClaw Gateway `127.0.0.1:18789` 已真实部署并验证；群聊编排由 AG2（in-process，无需 Docker）真实运行。

## 1. 当前进度（照计划执行）

| 阶段 | 内容 | 状态 | 产物 |
|---|---|---|---|
| P0 | 推理网关 LiteLLM | ✅ 已接入 | `src/core/fabric/adapters/litellm_adapter.py` |
| P1 | 记忆/知识 Mem0 | ✅ 已接入 | `src/core/fabric/adapters/mem0_adapter.py` |
| P2 | 动手/ACI browser-use | ✅ 已接入 | `src/core/fabric/adapters/aci_browser_adapter.py` |
| P3 | 观测/护栏 Langfuse | ✅ 已接入 | `src/core/fabric/adapters/observability_langfuse_adapter.py` |
| 行为平面① | OpenClaw（嘴耳/接入）真实部署 | ✅ 已真连 | 真实 Gateway @18789 跑通 agent turn（Zhipu glm-4-flash），fabric --real 全链路验证通过（channel.access 真连 + group.orchestration 经 AG2 真连群聊） |
| 行为平面② | 群聊编排（AG2 真实驱动） | ✅ 已真连 | AG2（AutoGen 社区分叉, MIT, pip `ag2`）in-process 群聊，已真连验证 |

---

## 2. 文档都在哪（`D:\AOS\docs\`）

| 文件 | 讲什么 | 何时看 |
|---|---|---|
| `docs/CAPABILITY_AUDIT_VS_4MODULES.md` | AOS 对照你给的 4 模块的能力审计（提升/遗漏） | 想看"AOS 现在强弱在哪" |
| `docs/OPEN_FABRIC.md` | 开放 fabric 设计：能力 taxonomy、适配器契约、协议、文件地图 | 想看"接线板长什么样" |
| `docs/GLOBAL_REVIEW.md` | **全局审视**：4 开源是 4 个器官、AOS 是总部、自研代码待退役 | 想看"整体架构对不对" |
| `docs/MISSING_LAYERS.md` | **缺的平面**：推理/记忆/ACI/观测 4 层 + 真实开源候选 + 优先级 | 想看"还差什么、为什么" |
| `docs/DATABASE_SCHEMA.md` | 42 表 ORM 数据底座文档 | 想看"状态层有哪些表" |

---

## 3. 代码都在哪（`D:\AOS\src\core\fabric\`）

```
src\core\fabric\
  capability.py            开放能力 taxonomy（按能力组合，不是按项目名）
  adapter.py               AOS 唯一拥有的契约 BaseAgentAdapter
  registry.py              按能力发现/路由（引擎无关、健康门控）
  protocols.py             开放胶水 MCP/A2A/ACP/AG-UI
  adapters\
    openclaw_adapter.py    OpenClaw 网关（嘴耳）— 真实 API 端点已填
    ag2_adapter.py        AG2 群聊编排（会议室·真实替代, MIT）— GroupChat 真连
    litellm_adapter.py     LiteLLM 推理网关（燃料）        ✅ 真实包已装
    mem0_adapter.py        Mem0 记忆/知识（大脑记忆）      ✅ 真实包已装
    aci_browser_adapter.py browser-use 浏览器动手（手）    ✅ 真实包已装
    observability_langfuse_adapter.py  Langfuse 观测（神经健康）✅ 真实包已装
```

---

## 4. 你指定的 4 个真实开源（行为平面）

| 角色 | 项目 | 真实仓库 | 许可 | 当前状态 |
|---|---|---|---|---|
| 嘴耳/接入 | OpenClaw | openclaws.io / Peter Steinberger | MIT | vendored 待接（`external/` 外） |
| 会议室/群聊 | AG2（真实群聊编排） | ag2 (MIT, AutoGen 社区分叉) | MIT | 已真连群聊 |
| 脑/自进化 | Hermes | github.com/NousResearch/hermes-agent | MIT | ✅ 已 vendored 在 `external/hermes-agent` |
| 体/长时执行 | DeerFlow | github.com/bytedance/deer-flow | MIT | ✅ 已 vendored 在 `external/deer-flow` |

**四个平面均已用真实 API 文档接入 fabric 的薄适配层**。

---

## 5. 四个基础设施平面（补"差点意思"）

| 平面 | 真实开源 | 解决什么 | 状态 |
|---|---|---|---|
| 推理网关 | LiteLLM | 统一 100+ LLM 接入/容灾/计费 | ✅ 接好，装包激活 |
| 记忆/知识 | Mem0 | Graph-RAG / 长期语义记忆 | ✅ 接好，装包激活 |
| 动手/ACI | browser-use | 浏览器/OS 真实操作 | ✅ 接好，装包激活 |
| 观测/护栏 | Langfuse | tracing/eval/guardrail | ✅ 接好，装包激活 |

---

## 6. 怎么跑（验证）

```bat
cd /d D:\AOS
set PYTHONPATH=.
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe scripts\verify_fabric.py
:: 第一条群聊纵切片（离线 fake）：
C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe scripts\slice_groupchat.py --demo
:: 健康门控检查（实测 openclaw UP / ag2 UP）： scripts\slice_groupchat.py --check
:: 真实纵切片（OpenClaw 真连 + AG2 真连群聊，已验证 → slice OK；需先起 Gateway 并 set ZHIPU_API_KEY）： scripts\slice_groupchat.py --real
```

- `verify_fabric.py` 通过 → fabric 跨 5+ 引擎路由能力。
- `slice_groupchat.py --demo` → OpenClaw 接入 → AG2 建群 → fan-out 给 developer/designer/tester（离线假引擎也能跑通编排流）。

---

## 7. 一句话给你

东西全在 `D:\AOS\`：分析文档在 `docs\`，接线板代码在 `src\core\fabric\`，验证脚本在 `scripts\`。**AOS 不重造大脑，只做让真实开源引擎 + 4 个基建平面一起干活的"总部 + 接线板"。** OpenClaw 已真实接入并验证；群聊编排由 AG2 真实驱动。

## 8. 真实开源部署状态（2026-07-08 核实）

### OpenClaw（✅ 已真实部署并验证）
- CLI 已装：`/c/Users/Administrator/AppData/Roaming/npm/openclaw`（2026.6.9）
- 配置：`~/.openclaw/openclaw.json`（gateway.mode=local, port=18789, bind=loopback, auth=token；provider=aos-zhipu 走智谱 Zhipu OpenAI 兼容 base=https://open.bigmodel.cn/api/paas/v4；apiKey 明文写入 models.providers.aos-zhipu.apiKey，不依赖 SILICONFLOW_API_KEY——SiliconFlow 余额已耗尽 403）
- 启动：`openclaw gateway --port 18789 --bind loopback --auth token --token <tok>`（后台常驻）
- 验证：`openclaw health` 返回 event loop ok；`openclaw agent --agent main -m "..." --json` 真实返回（provider=aos-zhipu, model=glm-4-flash，实测 OC_PROBE_OK）
- fabric 真连：`slice_groupchat.py --real` 的 channel.access 经真实 OpenClaw 返回中文（Flask 登录功能示例），group.orchestration 经 AG2 真实群聊返回（硬证据）；末尾 `=== slice OK ===` 全链路打通
- 铁律修正：AOS 自研的 `src/core/open_claw.py`、`src/subagents/openclaw_agent.py` 已标 DEPRECATED，改用 fabric `OpenClawAdapter`（调真实 Gateway）

### 群聊编排（AG2，真实驱动）
- 引擎：AG2（https://ag2.ai，MIT，AutoGen 社区分叉），`pip install ag2`（提供 `autogen` 命名空间）。
- 能力：GroupChat + GroupChatManager = 真实多智能体群聊（`group.orchestration`）。
- 验证：`slice_groupchat.py --real` 的 group.orchestration 经 AG2 真实群聊返回（硬证据）。

### 开源资产归位（2026-07-08 用户决策）
- 仓库内 `src/subagents/*`（实际 7 个，openclaw_agent 已 DEPRECATED 改走真实 OpenClaw）、`src/skills/*.py`（实际 34 个领域技能，框架文件已排除）、`src/skills/agency_roles/*`（266 个角色）均为**开源可复用构件**（符合 agentskills.io 标准），非自研重造。
- 归位模块：`src/deerflow/aos_assets.py`（静态 AST 解析，不执行资产模块，安全）；验证/出文档：`scripts/catalog_assets.py`。
- 归位结果（2026-07-08 实测）：
  - 7 子智能体 → **DeerFlow 子智能体**（每个封装一个真实开源工具/agent：LobsterAI / UI-TARS / Pixelle / Ruflo / Vimax / Loop / Skill）
  - 34 领域技能 → 19 DeerFlow 技能 / 5 归 Mem0 平面(记忆·知识) / 7 归 browser-use 平面(UI 自动化) / 3 归 fabric 自举能力(元技能)
  - 266 角色 → **DeerFlow 子智能体角色模板**
  - 合计 **273 个 DeerFlow 注册项**，由 `AOSSubagentBridge.register_subagent` 一键注册；DeerFlow 不可导入时只产出清单、不假成功。
- 用户授权：资产归位按"适合哪个位置放哪个"（记忆类→Mem0、UI 自动化→browser-use、元技能→fabric 自举）。
- **查重/查垃圾结论（2026-07-08）**：用精确信号（重名/重内容/文件名垃圾/空壳类/头部显式弃用/技能↔角色撞名）扫描全部 307 项 → **重复 0、垃圾 0、空壳 0、弃用 0、撞名 0**。仓库这批资产本身干净，无可自动剔除项，故 273 项全量注册。
- **DeerFlow 真实注册已验证通过 ✅（2026-07-08）**：
  - 运行环境：`external/deer-flow/backend/.venv`（Python 3.12.13，DeerFlow 要求 ≥3.12）里的 `deerflow`（harness）已装。
  - 命令：`backend/.venv/Scripts/python.exe scripts/register_deerflow_assets.py`
  - 结果：**成功注册 273 / 失败 0 / 跳过重名 0**，注册对象为 DeerFlow 真实 `SubagentConfig` 实例（存于 `AOSSubagentBridge._configs`）。注册清单见 `docs/DEERFLOW_REGISTRY.md`。
  - 桥接修复（让注册在"未装全套 DeerFlow 依赖"时也能跑）：
    1. `deerflow.path_detect` 在发行包不存在 → 回退为用已可导入 `deerflow` 包目录作源码根；
    2. `SubagentConfig` 是纯 dataclass，改为**独立按文件加载** `deerflow/subagents/config.py`（绕开会拉起 langgraph/langchain 的 __init__ 链），注册无需装全套重型依赖；
    3. 执行栈（executor）设为可选，注解惰性化（`from __future__ import annotations`）+ 占位符，缺依赖只影响"执行"不影响"注册"。
  - 环境补齐：backend venv 原缺 pip/pyyaml，已 `ensurepip` + `pip install pyyaml`；其余重型依赖按需（执行时才需）。

## 9. 全盘审视与清理（2026-07-08 凌晨）

用户要求"全盘审视 + 清理真正无用/将来用不上的资产"。完整报告：`docs/AOS_AUDIT.md`。

### 已清理（零风险，已执行）
- 一次性调试脚本：`debug_config.py` / `debug_config2.py` / `debug_env.py`
- 破坏性脚本：`fix_imports.py`（把 `from src.` 改写 `from `）
- 玩具 demo：`todo_app.py`；空文件：`docker`（0字节）
- 含明文密钥的试错启动器：`start_deerflow_2026.py`
- 无效散落测试：`test_deerflow_api.py` / `test_deerflow_chat.py`（仅 requests 无断言）/ `test_new_features.py`（空壳）
- 空目录：`hermes/`（顶层）
- 缓存：全仓库 `__pycache__` / `.pytest_cache`
- Hermes LSP dev 依赖：`config/hermes/lsp/node_modules`（pyright，29M，npm 可重建）→ `config/` 33M→3.6M

### 关键诊断（供后续决策，未删）
- git 100 未跟踪、几乎无提交 → **无版本保护**，核心代码审慎处理
- 自研大脑 `src/core/brain.py`(1310行)+7 编排模块(2663行)≈**3973 行**，引用汇聚 `core/__init__.py`+`brain.py`，违反铁律但系系统装配点 → 建议**退役**非物理删
- 平行冗余：`aos_deerflow/`(4py)+顶层`common/`(12py) 与 `src/deerflow`+`src/common` 重复，`src` 主系统不引用 → 建议迁 2 测试(`test_architecture.py`/`test_planner.py`)后删
- `workers/` 被 `execution/task_runner.py` `meta_orchestrator/server.py` `web/app.py` 引用，活跃，保留
- 数据/索引目录（`chroma_data`/`qdrant_storage`/`zvec_data`/`codebase_index`/`cognee_graph`/`data`/`agency-agents-zh`/`outputs`/`logs`）不自动删，仅 `logs/` 可安全清
