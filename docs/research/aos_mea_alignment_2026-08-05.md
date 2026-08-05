# AOS × LongHorizon-Harness（MEA 三权分立）对齐审计

> 日期：2026-08-05 | 级别：②（代码核对 + 离线分析，未跑③真 LLM 端到端）
> 触发：用户贴来 MEA（Manage-Execute-Audit）三角色循环资料，要求先核验真实性再判断可否落地。

## 一、资料核验结论（铁律：贴来的方案先验再采纳）

**结论：资料真实，非编撰。** 逐项核验如下：

| 核验项 | 结果 | 证据 |
|---|---|---|
| 项目是否真实 | ✅ 真实 | arXiv:2608.01964（2026-08，阿里高德 DreamX Team）+ GitHub `AMAP-ML/LongHorizon-Harness` |
| MEA 设计是否真实 | ✅ 真实 | Manager/Executor/Auditor 三权分立 + 只读 auditor 独立验证后才写状态，与用户贴文逐字对应 |
| Qwen 3.7-Plus | ✅ 真实 | 阿里 2026-06-02 发布（qwen.ai 官方博客 + 多家媒体） |
| Claude Opus 4.7 | ✅ 真实 | Anthropic 2026-04-16 发布（官方 + 多家媒体） |
| 基准 WeaveBench / Terminal-Bench 2.1 / OSWorld 2.0 | ✅ 真实 | 均有公开仓库/榜单（weavebench/WeaveBench、snorkel leaderboard 等） |
| License | ✅ **MIT**（母纲友好） | GitHub LICENSE 文件 + MIT 徽章 |

### 两个诚实补充（用户贴文未提，必须补）
1. **基准数字来自作者自报 + 有刷分风险**：UC Berkeley 2026-04 研究发现 8 个主流 agent benchmark 均可被 reward-hacking 刷到接近满分而不真正做事。WeaveBench 官方自己也提示 outcome-only grading 会高估 GPT-5.5 达 +20pt。**绝对值要打折看**，但"MEA 机制本身带来显著提升"这一结论有独立报道（dev.to）佐证，方向可信。
2. **隐藏成本**：同一来源披露，OSWorld 单任务输出 token 从 28.9K 涨到 104K（3 倍多），审计者是主要新增开销。MEA 不是免费午餐——它用更多推理换"不跑偏"，长任务上划算，短任务未必。

## 二、与 AOS 架构同构对照（宣称 vs 实际）

MEA 三权分立 ↔ AOS 现有模块**高度同构**，并非全新概念：

| MEA 角色 | 职责 | AOS 现有同构组件 | 真实状态 |
|---|---|---|---|
| **Manager** | 维护原始目标 + 已验证里程碑，签发带验收标准的子任务 | `autopilot_run`(main.py:2536) + `opc_plan`(OPC 5岗分解) + FabricHub 单基座路由 | ② 有规划/调度，但"已验证里程碑"未显式建模 |
| **Executor** | 每轮全新上下文完成单一子任务，轨迹用完即弃 | chiplet 子进程(agnes/ag2=crash boundary) + `StageGuard`(adaptive.py:500 环节级隔离) | ② 隔离有，但 autopilot 主循环同上下文长跑，非 per-subtask fresh context |
| **Auditor** | 只读独立验证环境事实，仅通过的结果才写持久状态 | `ResilienceBus`(FailureMonitor/SelfHealer/EvolutionDistiller) + `future.py:79 audit` + `persistence_bridge.py:200 audit` | ② 故障监测/自愈有，但非"每步验收关卡" |

**状态持久化层**：`autopilot` 经 `run_state_store.load_checkpoint` 读 sqlite checkpoint（main.py:2563）——已有"执行上下文之外的显式状态"，这是 MEA 要求的地基，AOS 已具备。

## 三、诚实 Gap（基于刚读的真实代码，非臆测）

AOS 有 MEA 的"形"，缺 MEA 的"神"——三处真实缺口：

1. **缺"已验证里程碑"状态层**：`autopilot` checkpoint 是进度快照（`status`/`state`），不是"经独立审计验证过的事实集合"。错误前提可能随快照进入后续规划。
2. **缺"只读 auditor gate"**：写入持久状态前没有独立、只读、环境事实验证的关卡。`ResilienceBus` 是**事后**故障自愈，不是**事前/事中**验收；`_ap_run_safe` 直接写 checkpoint，无 auditor 拦截。
3. **Executor 非 fresh-context**：`autopilot` 主循环在同进程/同上下文长跑，不符合 MEA"每子任务全新上下文、历史用完即弃"——长任务下仍有 context rot / 错误累积风险。

## 四、落地判断（决策铁律：融合优于单选，禁选择题）

**不引入 LongHorizon-Harness 作为依赖。** 理由（反缝补 + 现有够好→复用）：
- 它是"跑在 Claude Code / Codex / OpenClaw 之上的执行底座"，与 AOS 自身（agent OS / 执行底座）**是同类竞品**，引入即成"OS 套 OS"，违反 AOS 自研内核定位与母纲「不收割/本地优先」。
- AOS 已具备三要素雏形（上文对照），正确动作是**把 MEA 的"显式 verified state + 只读 auditor gate"模式对齐补进现有层**，而非新建外部依赖。

**融合补齐路径**（在现有模块上做，不缝补新组件）：
- **补 Gap1+2**：在 `run_state_store` 之上加一层 `verified_milestones`，由新增的只读 `AuditorGate`（复用 `ResilienceBus` 的 FailureMonitor 探测能力 + `future.py` 的 audit 结构）在写 checkpoint **前**独立验证环境事实（文件/界面/日志/测试），仅通过才落盘。审计报告即跨轮唯一可信记忆。
- **补 Gap3**：把 `autopilot` 的每子任务派发给 chiplet 子进程（已有 crash boundary），主循环只保留 Manager 职责（规划 + 读审计报告），实现 fresh-context executor。

## 五、落地进展（用户"？"授权直接动手，2026-08-05 22:17）

**Gap2（只读 auditor gate）已完成②级实证落地：**
- 实现：`src/kernel/run_state_store.py` 的 `save_checkpoint` 加默认关闭的 `_AUDITOR` 钩子 + `set_auditor(fn)`。
  - 注册 auditor 后写盘前由其基于环境事实独立验证；未通过则**拒绝覆盖旧快照**（错误前提不污染持久状态）。
  - auditor 抛异常 → 降级放行 + 告警，绝不阻塞 run（符合"failed checkpoint must not crash run"哲学）。
  - 无 auditor 时行为与原版**逐字节一致**（向后兼容，所有调用方零改动）。
- 测试：`tests/test_auditor_gate.py` **5 项②级实证全绿**：向后兼容 / 拒绝写盘 / 放行 / 异常降级 / 环境事实验证（executor 凭空宣称 2 步完成但 reflection 仅 1 条证据 → 拒绝）。
- 提交：`2b52a5c`（本地，待用户 push）。

**Gap1（已验证里程碑状态层）已完成②级实证落地（2026-08-05 续推进）：**
- 实现：`run_state_store` 新增 `verified_milestones` 表（与 `runs.state` 进度快照**物理分离**）+ `propose_milestone(run_id, m)` + `get_verified_milestones(run_id)`。
  - `propose_milestone`：注册 auditor 后，验证未通过**抛 ValueError 且绝不写入**（声称的里程碑不污染已验证状态）；auditor 异常降级放行；无 auditor 默认放行（向后兼容）。
  - 关键隔离：`runs.state` 里 executor 自称完成的 steps **不会自动**变成已验证事实，必须显式 `propose` 且经审计才进 `verified_milestones`——这正是 MEA"只有审计验证的事实能写入状态"的核心纪律。
- 测试：`tests/test_verified_milestones.py` **6 项②级全绿**：默认放行 / 拒绝抛错不写 / 放行写入 / 异常降级 / 原始 steps 不自动进 verified 层 / 多里程碑有序。
- 提交：`5a07689`（本地，待用户 push）。

**剩余 Gap（更深改造，待用户指令）：**
- **Gap3**（fresh-context executor）：autopilot 主循环同上下文长跑，需把每子任务派发 chiplet 子进程（已有 crash boundary）实现 executor 隔离。
- **默认 auditor 接入**：当前 gate + verified 层已就位但默认无 auditor；需在 autopilot 启动时注册一个真实环境探针（文件/服务/测试事实验证），而非仅测试用 mock。

> 注：Gap2/Gap1 均为低风险增量（纯钩子/独立表 + 向后兼容），已直接落地。Gap3 涉及 autopilot 主循环结构改造，按"先审查再动手"铁律，待用户确认范围后推进。
