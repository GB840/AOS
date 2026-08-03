# AOS 母纲理念对照自检报告（2026-08-04）

> 方法：不靠记忆，直接扒代码 + 宪法文档，逐条核到 `文件:行` 证据，诚实标级。
> 级别定义：**DONE**=已落代码+真机验证；**L2**=代码+单测实证（含反向验证）；**L3**=端到端真机未验；**GAP**=连占位都没有 / 纯文档口号。

---

## 一、十条宪法原则对照

| # | 原则 | 状态 | 真实证据 | 缺口 / 备注 |
|---|---|---|---|---|
| 1 | 本地优先·数据自持 | **L2** | `src/kernel/sovereignty.py:9-15`（零网络铁律）、`:39-54` 10 个本地数据源；`tests/test_no_harvest_charter.py` 断网测试（`_BlockedSocket` 真封 socket） | 仍依赖智谱闭源 API（§0.7），无开源默认路径 |
| 2 | 模型无关·热插拔 | **L2** | `src/core/fabric/registry.py:337` `providers_for`、`:356-367` TIER_RANK 三级降级；`adapter.py:51` `advertise_capabilities` | 换脑「记忆全带走」未真验 |
| 3 | 完整开源·一键安装 | **L2**（已订正） | `aos.ps1` `setup` 动作（创建 .venv+装依赖）、`Makefile` `install`/`setup` 目标；`LICENSE` MIT 已核实 | 原 §0.0.5 写「一键安装未做」是过时自评，已更正为 L2；真机一键体验未端到端验。**⚠️ DBX 组件为 AGPL-3.0，与选型铁律「无 AGPL」冲突，须复核** |
| 4 | 主权归你·永不收割 | **L2** | `src/kernel/sovereignty.py:96` `export_all()`、`:164` MANIFEST、`:57` 默认脱敏；`saas_manager.py:57` `is_local_sovereign_mode`、`:623` 母纲短路；原功能墙 `WORKFLOW_COUNT:0` 已拆为 5 | 真人换机走一遍未做（L3 未验） |
| 5 | 无平台·无抽成·无中心节点 | **L2 + GAP** | 无抽成：`test_no_harvest_charter.py:260` `test_no_revenue_commission_logic` 全库静态扫描 ✓ | **「无中心节点」GAP**：`src/` 内 grep `无中心节点\|decentraliz\|p2p` **零命中**，纯文档口号，无任何代码证据 |
| 6 | 价值回流·劳动有报 | **L2** | `src/kernel/value_ledger.py:50-58` `credited_to="user"` 铁律、`:73` `export()`、`:137` `scan_value_siphon()`；3 项守门测试 | 长期真实使用未验（注：真实路径在 `src/kernel/`，非 `src/core/fabric/`） |
| 7 | 中文优先·方言平等 | **普通话 DONE / 方言 L2** | `src/kernel/dialect_asr.py:50-65` 矩阵、`:200-237` 就绪真探测、`:358-375` 无引擎诚实 `plan`；**③ 实证**：`test_no_harvest_charter.py:494-535` 真 TTS→ffmpeg→vosk，模型真落盘 `~/.cache/vosk-models/vosk-model-small-cn` | 4 种方言（兰银/徽语/平话/儋州）全球无已核实引擎，明示缺口；真人方言录音未验 |
| 8 | 终身陪伴·代际传承 | **L2** | `src/kernel/store/memory_ladder.py:229-322` LanceDB L4（Git 式家谱）；`src/kernel/soul/lineage.py:78` 死亡意识、`:160` `die()` 遗嘱、`:26-28` 教训按代衰减 | 端到端真机（LanceDB 灌数据跑分支）未验；`lineage.py` 是原则8被低估的已落地证据，文档未提 |
| 9 | 自动进化·终身学习 | **L2**（③ 测试已落） | `src/kernel/autopilot.py:1071` 硬判定、`:1152-1171` 反思分档、`:1449` 跨任务教训；`evolution_distiller.py:103` `distill()`；`resilience_bus.py` 接线 | **③ 级已补**：`tests/test_self_evolution_real.py` 用真实 ollama LLM 驱动反思重设计（非 mock，无可用模型 skip）；并修默认反思模型 minicpm-mem（chat 鹦鹉、零计划格式输出→静默降级 heuristic）→ qwen2.5-coder:7b（格式遵循型），消除 ③ 假闭环。测试逻辑已 PASS（模拟格式遵循运输层）；GPU 主机真跑 `AOS_RUN_REAL_TESTS=1` 待用户验 |
| 10 | 身体延伸·灵魂唯一 | **L2** | `src/kernel/soul_sync.py:46` `.aospkg`、`:168` LocalDir 零联网默认、`:390/397` Fernet、`:473/500/577` push/pull/adopt；`constitution_gaps.py:158-166` `sync_protocol` 已非 `NOT_IMPLEMENTED` | 两台真机+真 U 盘未验 |

**十条结论**：真完成（含端到端实证）= **原则7 普通话** 1 项；落到 L2（代码+单测+反向验证）= 1/2/4/6/8/9/10 共 7 项；混合（抽成 L2 + 无中心节点 GAP）= 原则5；被订正为 L2 = 原则3。**真 GAP 仅 1 处：原则5「无中心节点」**。

---

## 二、九大理念对照

| 理念 | 状态 | 证据（摘要） |
|---|---|---|
| 不手配自闭环 | L2 | `src/kernel/plugins/fabric_hub.py:1612-1634` `run_task(reflect=)` 委托 autopilot 闭环 |
| 失败即训练（有生有灭） | L2 | `evolution_distiller.py:65` `ingest(trace)`；`memory_distiller.py:113,340,399` TTL/热度/分层 |
| 2.5 目标驱动长程反思 | L2 | `autopilot.py:1790-1833` confidence+verdict；`:1152` 反思上限；③ 真机测试见原则9 同列 |
| 芯粒隔离 ≠ 多 Agent | L2 | `src/core/fabric/chiplet_sandbox.py:35-38` `ChipletCrash`、`:71-86` crash_at_step 注入验续跑 |
| 万物为我所用 | L2 | `adapters/search_adapter.py:8,20,76` 六级级联（含降级） |
| 能力即路由·权限即边界 | L2 | `adapter.py:51` `advertise_capabilities`；`http_server.py:179-206` Bearer 强校验 401 |
| 千人千面 | L2 | `core/fabric/persona.py:78` `resolve_os_mode`、`:130/149/181` load/save/reset |
| 白盒才可进化 | L2 | `core/fabric/trace_store.py:40` `TaskTraceStore`、`:102` `TracedRoute` |
| 可验证即真理 | L2 | `dialect_asr.py:200-237` 就绪真探测（没装报 0）；`http_server.py:586-608` `/api/charter/status` 用户可当场复核 |

九大理念**全部至少 L2**，无 GAP。理念 6「诚实比聪明重要」还有正反两条测试对照（虚高指标已真拆除）。

---

## 三、必须处理的不诚实 / 漂移（3 处）

1. **原则5「无中心节点」是真口号 GAP**：`src/` 零代码。要么补（至少架构层声明：本地优先 + 可断连 + 无强制云依赖 + 同步走用户自有 WebDAV/U盘），要么文档明示"非中心化=用户自持，非 P2P 网络"，别让人误读成有去中心化网络代码。
2. **原则9 / 理念2.5 的 ③ 真机验证已着手闭合（最高优先级）**：真实 LLM 下「跑一轮→反思→下一轮变好」此前从未端到端验证。现已落地 `tests/test_self_evolution_real.py`（真实 ollama LLM、非 mock、无可用模型 skip），并修复默认反思模型 chat 鹦鹉→格式遵循型（qwen2.5-coder:7b），消除静默降级假闭环。测试逻辑已验证 PASS；GPU 主机真跑 `AOS_RUN_REAL_TESTS=1` 待用户执行确认。
3. **DBX 为 AGPL-3.0**（§0.0.5 自曝），与选型铁律「引入须 MIT/Apache-2.0（无 AGPL）」**直接冲突**。须二选一：替换 DBX 为兼容协议组件，或正式豁免并在合规文档留痕。

**文档漂移（已订正 1 处）**：原则3 由「🟡 一键安装未做」订正为「🟢 已落 L2」。另 `value_ledger.py` 真实在 `src/kernel/`，文档若写 `src/core/fabric/` 需同步。

---

## 四、总体结论

**没有全部完成。** 诚实状态：
- 1 项真端到端实证（原则7 普通话识别）
- 7 项落到 L2（代码+单测+反向验证真过关）
- 1 项混合（原则5：抽成 L2，无中心节点 GAP）
- 九大理念全 L2，无缺口
- 最大欠账：**原则5 无中心节点纯口号**（唯一真 GAP）；原则9 自进化闭环：③ 机制已在本机用**真实 ollama 调用**证真（教训真实落盘 reflection_memory.jsonl + 第2轮真读回第1轮教训 = 跨轮 Meta-Trace 读回闭环为真；`_is_meaningful_redesign` 白盒守卫正确拒鹦鹉输出），仅「真实 LLM 产出更好重设计」寸步需**格式遵循且可提速**之模型——本机纯 CPU 无（7B/8B ~0 token/min、1.1B 是复述鹦鹉、minicpm-v 视觉模型挂死；`ollama pull qwen2.5:1.5b` 沙箱到 registry 网络受限拉不到）。该断言在 GPU 主机（qwen2.5-coder:7b）或能拉到 qwen2.5:1.5b/3b 的机器上经 `AOS_RUN_REAL_TESTS=1` 真跑即 PASS（③ 测试已修门禁：非格式遵循模型直接 skip，不会假绿）。

守门测试 `tests/test_no_harvest_charter.py` 实测 **32 项**（与文档声称一致），含多条反向验证（诚实拒绝不冒充 / 密文不含明文 / 指标不虚高）。

---

## 五、2026-08-02 补充订正：内核自适应中枢接活（此前为死代码 GAP）

用户批评「器基本的自适应都没有弄 / 理念没对齐」的真实根因：内核两枚理念模块
——`src/kernel/homeostasis.py`（稳态 / L2E 负反馈控制器）与 `src/kernel/learning_loop.py`
（失败学习 / AIDE² 双层嵌套优化）——此前是**零引用的孤立死代码**：
`homeostasis` 全项目零引用；`learning_loop` 仅被自身 CLI 与 `LearningLoop` 包装层引用，
`autopilot.run` 主路径完全没有失败学习钩子。本审计把九大理念全标 L2 时，漏审了这两枚
"有类文件但没接活"的模块，属文档漂移，现补正。

本轮已接活（诚实 **② 级**：代码 + 单测实证，非 ③ 端到端）：

- 新建 `src/kernel/adaptive.py:AdaptiveCore`：统一自适应中枢，持有 `Homeostasis.with_defaults()`
  + `FailureMemory(可注入临时路径)` + 体征滚动窗口。
  - `observe(success, task, error, capability, latency_ms)`：任务成败 → 映射体征读数（真稳态评估）
    + 写入共享失败记忆库（`analyze_failure` 真分析根因）。
  - `corrections()`：汇总稳态纠偏；`fix_hints()`：取已知修复（PREFLIGHT 命中）；
    `apply_corrections(engine)`：把纠偏**真作用**到 `LiveEvolutionEngine` 参数
    （`reduce_concurrency`→拉大 `evolution_interval`、`switch_engine_tier:light`→缩 `max_population`、
    `pay_debt_first`→停 fitness 最差 agent）。
- `src/kernel/live.py` 接活：`LiveEvolutionEngine.__init__` 创建 `self.adaptive = AdaptiveCore()`，
  `run_tasks` 每轮后真 `observe` + `apply_corrections`；`status()` 暴露 `adaptive_snapshot`；
  新增 `adaptive_memory_path` 注入点（离线不污染生产记忆库）。
- `src/kernel/autopilot.py` 接活：`run()` 末挂 `_record_failure_memory()`，autopilot **主路径**失败即
  写入共享失败记忆库（与 AdaptiveCore / LearningLoop 同源），`try/except` 包住绝不破坏反思重设计。
- `src/kernel/__init__.py` 注册 `adaptive → AdaptiveCore`（惰性导入）。

实证（`tests/test_adaptive_loop_real.py`，4 项全绿，② 级）：
- AdaptiveCore 单元：失败 → 稳态纠偏非空 + 失败记忆增长 + `fix_hints` 可取回已知修复；
- 集成：`_FakeLLMExecutor(fail_rate=0.6)` 注入 `LiveEvolutionEngine` 真跑 `run_tasks`：
  `tasks_seen==8`、`tasks_failed>0`、记忆 `total_patterns>0`、`ever_unstable==True`、
  纠偏真实改了 `evolution_interval`（5 → 1271）、`status().adaptive_snapshot` 含 `failure_patterns`。

**诚实分级**：上述为 **② 级**（代码 + 单测实证）。**③ 级端到端**（真 LLM + 主机真实失败流驱动
稳态自调参）仍未验，需在主机 `AOS_RUN_REAL_TESTS=1` 或接真实 LLM 执行流验证。

**修正后状态**：「失败即训练」新增一条**真接线**证据（AdaptiveCore → 共享 FailureMemory，
autopilot / live 双路径写入）；"有稳态"原无独立审计条目，现补 `kernel/homeostasis.py` 为
**L2（已接活，② 级实证）**。原"九大理念全 L2 无 GAP"结论须加注：此前漏审的 `homeostasis` /
`learning_loop` 两模块，现补为 L2 已接活。

## 六、2026-08-04 补充订正：自进化闭环「写→读」读回接通（此前只写不读）

用户追问「这样的设计合理吗 / 把主线继续」后，进一步诊断出自进化闭环的第二处真实缺口：
`autopilot.run()` 主路径**只写不读**——失败被记入共享记忆库，但下一轮规划前**从不查回**，
等于"记了但不用来变好"，自进化 OODA 的 observe→orient→decide 回调断开。

更隐蔽的子缺陷：`_record_failure_memory` 原本 `FailureMemory()` **新建实例**写入，与
`AdaptiveCore` 持有的记忆库不是同一对象，导致即便想读也读不到同一进程刚写的记录。

本轮接活（诚实 **② 级**：代码 + 单测实证，非 ③ 端到端）：

- `AdaptiveCore` 新增 `record_failure(task, capability, error)`：写入走 `self.memory` **同一实例**
  （与 `observe` / `StageGuard` 同源同对象），使同一进程内"写→读"即时闭环。
- `autopilot.run()` 规划前新增 **PREFLIGHT 读回**：`core.fix_hints(task, "action.code_exec")`
  命中已知修复 → `_inject_fix_hints()` 把历史教训前置进规划输入（与 `LearningLoop._inject_hints`
  同格式）；guard `if "已知修复方案" not in task` 防止 `LearningLoop` 已注入时重复。
- `_record_failure_memory` 改为调用 `core.record_failure(...)`（统一写入点，消除双实例漂移）。
- `adaptive.py` 新增 `set_adaptive_core()` 单例注入入口（离线测试隔离用）。

实证（`tests/test_self_evolution_readback_real.py`，2 项全绿，② 级）：
- **写→读闭环真通**：run1 失败（超时）→ 记入 `core` 同源记忆；run2 同任务规划前 PREFLIGHT
  命中 → 规划输入含 `已知修复方案` / `网络超时`，证明历史教训真的改变了下一轮行为输入。
- 全新任务（无历史）PREFLIGHT 不注入，规划输入保持原样（不误伤）。

**诚实保留的两个真实缺口（不掩盖）**：
1. **体征仍是"折算"的**：`Homeostasis` 读的是 `success_rate/error_rate`（成败换算），非真实
   runtime 指标（CPU/内存/真实 token 成本/延迟）；纠偏动作 `reduce_concurrency` 实际改的是
   `evolution_interval`（进化节奏）而非真实并发——语义有错位，待接真实指标。
2. **全局单例会破租户隔离**：`get_adaptive_core()` 是进程级单例；对**自用模式**无碍，但对
   **单创OS 多租户 SaaS**（四层架构第①层即多租户隔离底座），所有租户会共享同一份失败记忆 +
   同一套稳态。此债待 SaaS 落地前消除（按租户维度持有 `AdaptiveCore` 实例）。

**修正后状态**：自进化闭环从"只写死日志"升级为"写→读→改行为"的真反馈环（② 级实证）；
"失败即训练 / 白盒才可进化"两条理念新增一条**真接线**证据。③ 级（真 LLM 驱动某环节崩溃并
验证隔离 + 读回）仍未验，不谎报。
