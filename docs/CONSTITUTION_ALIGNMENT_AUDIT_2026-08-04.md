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
| 9 | 自动进化·终身学习 | **L2** | `src/kernel/autopilot.py:1071` 硬判定、`:1152-1171` 反思分档、`:1449` 跨任务教训；`evolution_distiller.py:103` `distill()`；`resilience_bus.py` 接线 | **L3 核心痛点未验**：真 LLM 跑一轮→反思→变好从未端到端验证（用户自认） |
| 10 | 身体延伸·灵魂唯一 | **L2** | `src/kernel/soul_sync.py:46` `.aospkg`、`:168` LocalDir 零联网默认、`:390/397` Fernet、`:473/500/577` push/pull/adopt；`constitution_gaps.py:158-166` `sync_protocol` 已非 `NOT_IMPLEMENTED` | 两台真机+真 U 盘未验 |

**十条结论**：真完成（含端到端实证）= **原则7 普通话** 1 项；落到 L2（代码+单测+反向验证）= 1/2/4/6/8/9/10 共 7 项；混合（抽成 L2 + 无中心节点 GAP）= 原则5；被订正为 L2 = 原则3。**真 GAP 仅 1 处：原则5「无中心节点」**。

---

## 二、九大理念对照

| 理念 | 状态 | 证据（摘要） |
|---|---|---|
| 不手配自闭环 | L2 | `src/kernel/plugins/fabric_hub.py:1612-1634` `run_task(reflect=)` 委托 autopilot 闭环 |
| 失败即训练（有生有灭） | L2 | `evolution_distiller.py:65` `ingest(trace)`；`memory_distiller.py:113,340,399` TTL/热度/分层 |
| 2.5 目标驱动长程反思 | L2 | `autopilot.py:1790-1833` confidence+verdict；`:1152` 反思上限（同原则9，L3未验） |
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
2. **原则9 / 理念2.5 的 L3 是用户亲认的核心痛点**：真实 LLM 下「跑一轮→反思→下一轮变好」从未端到端验证。这是"自进化"卖点的最大诚实欠账，优先级最高。
3. **DBX 为 AGPL-3.0**（§0.0.5 自曝），与选型铁律「引入须 MIT/Apache-2.0（无 AGPL）」**直接冲突**。须二选一：替换 DBX 为兼容协议组件，或正式豁免并在合规文档留痕。

**文档漂移（已订正 1 处）**：原则3 由「🟡 一键安装未做」订正为「🟢 已落 L2」。另 `value_ledger.py` 真实在 `src/kernel/`，文档若写 `src/core/fabric/` 需同步。

---

## 四、总体结论

**没有全部完成。** 诚实状态：
- 1 项真端到端实证（原则7 普通话识别）
- 7 项落到 L2（代码+单测+反向验证真过关）
- 1 项混合（原则5：抽成 L2，无中心节点 GAP）
- 九大理念全 L2，无缺口
- 最大欠账：**原则9 自进化闭环 L3 端到端未验**（用户自认痛点）+ **原则5 无中心节点纯口号**

守门测试 `tests/test_no_harvest_charter.py` 实测 **32 项**（与文档声称一致），含多条反向验证（诚实拒绝不冒充 / 密文不含明文 / 指标不虚高）。
