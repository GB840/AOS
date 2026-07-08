# 用户 8 条清单 → AOS 整改映射

> 时间：2026-07-09
> 来源：用户贴出一份「需要关注的问题」清单（原称 8 条，实际列了 9 项）
> 结论先行：**该清单描述的是另一个代码库**（含 `AgentGenesis` / `scheduler-server` / `agentos_*` 命名，疑似 AgentOS/AgentGenesis 项目），经 `Glob` 在 `/d/AOS` 全仓检索 `AgentGenesis/`、`scheduler-server/`、`agentos_*`、`test_agentos_*` 均为空，唯一撞名 `wasmtime` 是 AOS 自己 `WasmSandbox` 的可选依赖。
> 但其中 **9 项有 7 项在 AOS 存在同类问题**。下表逐条映射，并标注 AOS 现状、严重度、整改动作与优先级。

---

## 映射总表

| # | 用户清单条目 | 是否命中本仓 | AOS 对应问题 | 严重度 | AOS 现状 | 整改动作 | 优先级 |
|---|---|---|---|---|---|---|---|
| 1 | AgentGenesis 冗余 | ❌（无 AgentGenesis） | 大量自研智能体（brain/swarm_flow/meta_debate/negotiation/lemon_orchestrator、src/subagents、agency_roles 300+ 角色）与「四核心 OSS 优先」方针的边界 | 高（铁律合规） | 四核心 OSS 已接；自研大脑保留为合法集成层（04:41 用户校正：brain.py 合法不删） | 渐进把自研能力路由到真 OSS，不物理删 | P0（边界已界定） |
| 2 | test 文件位置 | ✅ | 顶层散落 7 个 `test_*.py`（test_architecture/db/e2e/final/graphrag_full/memory/planner） | 低（代码组织） | 散落仓库根 | 归集到 `tests/`，更新 import | P3 |
| 3 | Alembic 替代启动补丁 | ✅（同类） | persistence 用裸 SQL 启动补丁建表/初始化，无迁移管理 | 中（可维护/数据一致性） | 裸 SQL 补丁 | 评估引入 Alembic；若 schema 稳定则文档化补丁 | P2 |
| 4 | 依赖声明 | ✅（高危） | `requirements.txt` 仅 30 行，漏声明 mcp/ag2/litellm/PyJWT/psycopg2/zhipuai 等 | 高（全新安装即崩） | **本轮已补**（见 requirements.txt） | 完成 | P1（已执行） |
| 5 | mcp SDK 未声明 | ✅（高危，属 #4 子集但更具体） | `main.py:22` 顶层 `from mcp import MCPMessage` 硬依赖，但 requirements 未声明，此前仅靠 `AOS_EXTRA_SITE` 从 default venv 借入（不设变量 AOS 启动即崩） | 高 | **本轮已显式声明 `mcp>=1.28.0`** | 完成 | P1（已执行） |
| 6 | wasmtime 未声明 | ✅（可选） | `src/core/platform/sandbox.py:92` 懒导入 `wasmtime`（WasmSandbox 可选依赖），缺失仅禁用 Wasm 沙箱 | 低（可选能力） | 懒导入，缺则降级 | 在 requirements 可选段注释标注 | P3（本轮已标注） |
| 7 | 同步异步混用 | ✅ | `DeerFlowGatewayClient` 用 `threading` + `asyncio` 混用（run() 起后台线程、stream() 异步） | 中（可维护/潜在竞态） | 工作正常但混用 | 路线图标注，重构为纯异步待评估 | P2 |
| 8 | exec(code) 注入 | ✅（已缓解） | `skills/composition.py:78` 与 `factory.py:141` 用 `eval(condition, {}, safe_vars)` | 中（安全） | 已用**空 globals + 正则白名单 + try** 缓解（审计复核确认非裸 eval） | 进一步替换为受限求值器 / `ast.literal_eval` 彻底消除注入面 | P2 |
| 9 | 结构化日志缺失 | ✅ | 混用 `print` 与 `logging`，无统一结构化格式 | 中（可观测性） | 混合输出 | 引入统一 logger（JSON 格式 + 级别 + 上下文） | P3 |

---

## 关键发现（本轮已修复）

- **`mcp` 是 AOS 启动的硬依赖，此前却完全未声明**：`main.py` 在模块顶层 `from mcp import MCPMessage`，而 `mcp` 仅装在 default venv、靠 `AOS_EXTRA_SITE` 注入才被解析。这意味着任何不设置 `AOS_EXTRA_SITE` 的启动方式（如直接 `pip install -r requirements.txt && uvicorn`）都会 `ModuleNotFoundError` 崩溃。
  - **修复**：`requirements.txt` 新增 `mcp>=1.28.0`（实测 1.28.1），使 aos venv 自洽。
- **`ag2` / `litellm` / `PyJWT` / `psycopg2-binary` / `zhipuai` 同为生产路径依赖，此前漏声明**：一并补全（见 `requirements.txt` 新增段）。
- 可选平面 `mem0ai`(2.0.11) / `langfuse`(4.13.1) / `browser-use`(0.11.13) 装在 default venv，已在 requirements 注释段登记版本供复现。

---

## 未在本轮执行（路线图项，非阻塞）

- **P2｜Alembic 迁移**：评估是否用 Alembic 替代裸 SQL 启动补丁。当前补丁可用，改动需谨慎（涉及表结构演进）。
- **P2｜同步异步统一**：`DeerFlowGatewayClient` 的 threading+asyncio 混用重构为纯异步。功能正常，重构有回归风险，建议单独排期。
- **P2｜eval 安全加固**：将 `skills/*` 的 `eval` 替换为受限求值器。当前空 globals+白名单已缓解，属纵深防御。
- **P3｜测试归集 / 结构化日志 / wasmtime 声明**：代码组织与可观测性改进，低优先级。

---

## 与既有整改文档的关系

- 铁律合规与四 OSS 收敛：见 `docs/AUDIT_REPORT_2026-07-08.md` §「🔴 重大铁律偏差」与 `docs/AOS_AUDIT.md`。
- 生产级能力缺口与路线图：见 `docs/AOS_BUILD_STRATEGY.md` / `docs/EVOLUTION_ROADMAP.md`。
- 本文件仅聚焦「用户清单 → AOS 同类问题」的映射与本轮已落地的依赖修复。
