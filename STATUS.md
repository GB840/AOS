---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '1d1a7d3c-44e0-4d1e-ae36-3944943b1076'
  PropagateID: '1d1a7d3c-44e0-4d1e-ae36-3944943b1076'
  ReservedCode1: '83e8ff3a-3725-4460-b84f-3314c700a795'
  ReservedCode2: '83e8ff3a-3725-4460-b84f-3314c700a795'
---

# AOS 项目状态总地图（STATUS）

> 这是一份**导航索引**，不是技术文档。每次大状态变动更新这里。
> 最后更新：**2026-07-25**（数字纠偏：实测 **27 适配器类（基础 _ADAPTERS 26 + orchestrator） / 36 适配器文件（core/fabric/adapters 新栈 36 文件 / 34 类） / 1139 测试函数 / 178 测试文件 · FabricHub 实际注册 38 个引擎（基础 27 + 动态 11），live 31 / dead 7 · 11 内核子包 + 36 内核顶层模块 · 20 API 路由文件**）。

---

## 0. 一句话现状（2026-07-25）

AOS 已完成"融为一体"重构：以 **FabricHub（单基座能力路由器）** 为干净运行时，统一持有路由/记忆/上下文主权并调度各芯粒适配器；legacy 的 `brain.py` 仍作 `/api/chat` 灰度兜底（双轨尚未合流）。在此之上新增了**内容飞轮平台**（Studio/Hub/Pulse/Evolve + 5 适配器 + SkillHub/AutoSkill 集成），端到端已真跑通（搜索→LLM 写脚本→本地 ffmpeg+edge-tts 生成视频）。

**规模（实测，非记忆，2026-07-25 baseline_snapshot + probe_all 真机核对）：**
- **27 适配器类**（FabricHub `_ADAPTERS` 26 + orchestrator 1）/ 36 适配器文件（core/fabric/adapters 新栈 36 文件 / 34 类） / 1139 测试函数 / 178 测试文件
- FabricHub **实际注册 38 个**引擎（基础 27 + 动态 11），**live 31 / dead 7**
- 11 内核子包 + 36 内核顶层模块 / 20 API 路由文件 / 50+ 技能（manifest.json）
- **7 大 dead 引擎**（2026-07-25 probe_dead.py 实跑 8s 探活）：openclaw / stt / lfm2 / minicpm_o / vlm / mediakit / comfyui
- **反思闭环 mock 端到端首验 PASS**（2026-07-25）：6 阶段按序推进 + 教训自动注入下一轮 analyze

---

## 1. 当前进度（按时间线）

| 阶段 | 内容 | 状态 | 产物/提交 |
|---|---|---|---|
| 融为一体 Phase1-9 | 删死代码、加 FabricHub.chat、Skill 生态、Hermes 桥、litellm 配置、brain fabric 崩溃修复、VideoMaker 导出 | ✅ 已 push | `4c5d389`…`32c7862` |
| SkillHub 集成 | skill_registry 支持外部 7.9 万技能 fallback（AOS_SKILLHUB=1） | ✅ 已 push | `98068ec` |
| FabricHub chat 测试 | chat()/skill_discover() 单元测试 11 通过 | ✅ 已 push | `aec249c` |
| 内容飞轮平台 | Studio/Hub/Pulse/Evolve + 5 适配器 + SkillHub/AutoSkill + /studio 前端 | ✅ 已 commit（待 push） | `a13c489` |
| 文档刷新 | AGENTS.md 真实规模数字 | ✅ 已 commit（待 push） | `5e889c3` |

**分支**：`feature/infra-setup`；**最新提交**：`5e889c3`（之前还有 `a13c489` 内容飞轮批次）。
**运行环境**：Python 3.14，绝对路径 `C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe`（系统 Python，非 venv）。

---

## 2. 架构总览（双轨 + 内容飞轮）

```
                  ┌─────────────────────────────────────────────┐
   用户/API  ───► │  FastAPI (src/api/main.py)                   │
                  │   ├─ /api/chat        ──灰度──► brain.py(legacy 兜底)
                  │   ├─ /api/chat        ──AOS_FABRIC_CHAT=1──► FabricHub.chat()
                  │   ├─ /api/skills / /api/product_flywheel / /api/autoskill
                  │   └─ /studio          ──静态前端 web/studio/index.html
                  └─────────────────────────────────────────────┘
                                    │ 路由/调度
                  ┌─────────────────────────────────────────────┐
                  │  FabricHub (src/kernel/plugins/fabric_hub.py)│  ← 干净单一运行时
                  │   能力注册 · 健康门控 · 全局高中低三级路由     │
                  └─────────────────────────────────────────────┘
              ┌──────────────┬──────────────┬───────────────┬──────────────┐
        29 芯粒适配器   内核子包(11)     内容飞轮平台      外部生态
        (adapters/)  (kernel/*/)   (studio/hub/pulse/   (SkillHub 7.9万
                                  evolve + 5适配器)      技能 / IMA / WeKnora)
```

**双轨未灭**：FabricHub 新栈 与 legacy（`core/brain.py` + `deerflow`/`swarm_flow`/`lemon_orchestrator`）并存互不打通；`/api/chat` 仍灰度调 brain.py 兜底。**目标 FabricHub 为唯一运行时**（尚未合流）。

---

## 3. FabricHub 适配器（27 类 / 35 文件 + 11 动态注册 → 总注册 38 个）

`src/core/fabric/adapters/` 共 35 个 .py 文件，`_ADAPTERS` 注册 26 个（+1 orchestrator 运行时自动 = 27 基础），
另有 11 个引擎通过 `register_*()` 动态注册（env / opt-in 触发），**health_report 实测总 38 个注册**（live 31 / dead 7）。

### 3.1 基础 `_ADAPTERS`(26) — 27 基础引擎

按"真实开源绑定 vs AOS 自研"分类（核实结论，不编造）：

**真实开源薄适配层（接已验证的开源项目）：**
| 适配器 | 绑定开源 | 角色 |
|---|---|---|
| `OpenClawAdapter` | OpenClaw 网关（嘴耳/接入） | 多通道接入 — **dead**（端口没起） |
| `LiteLLMAdapter` | LiteLLM | 统一 100+ LLM 推理网关 |
| `Mem0Adapter` | Mem0 | Graph-RAG 长期记忆 |
| `LangfuseAdapter` | Langfuse | tracing/eval/观测 |
| `BrowserUseAdapter` | browser-use | 浏览器动手/ACI |
| `AG2Adapter` | AG2（AutoGen 社区分叉, MIT） | 群聊编排 |
| `MCPClientAdapter` / `MCPStdioAdapter` | MCP 协议 | 接任意外部 MCP Server |
| `MiniCPMOAdapter` | MiniCPM-o（OpenBMB, 全双工语音） | 语音/全模态 — **dead**（本地服务探活失败） |
| `Crawl4AIAdapter` | crawl4ai | 高质量 web 爬取 |

**AOS 自研/自包含功能适配器：**
| 适配器 | 做什么 | 状态 |
|---|---|---|
| `AgnesAdapter` | 多模态平面（OpenAI 兼容） | live |
| `ContentMarketerAdapter` / `CastAdapter` / `EchoAdapter` / `RefineAdapter` / `VideoMakerAdapter` | 内容飞轮：搜索→写脚本→生成视频→分发→回声→优化（ffmpeg+edge-tts 本地生成） | live |
| `CodeExecutionAdapter` / `FileAdapter` / `ScriptsAdapter` | 本地代码/文件/脚本执行 | live |
| `SearchAdapter` / `WebFetchAdapter` | 多源联网搜索/抓取 | live |
| `LFMAdapter` / `LNNAdapter` / `VLMAdapter` / `STTAdapter` / `TTSAdapter` / `ThreejsAdapter` | 模型/模态能力 | live / stt-vlm dead |
| `MediaGenAdapter` / `RemotionAdapter` | 媒体生成（云端 / npx） | live |
| `SecurityAuditAdapter` / `IdaProMcpAdapter` | 安全/逆向 | live |
| `Img2ThreejsAdapter` / `MediakitAdapter` | 3D / 视频后期 | live / mediakit dead |
| `RefineryAdapter` | 代码炼化（白盒蒸馏） | live |

### 3.2 动态注册（11 个）— env / opt-in 触发

| 引擎 | 触发方式 | 状态 |
|---|---|---|
| `OrchestrationChiplet` | 运行时自动 | live |
| `ComfyUIAdapter` | 运行时自动（register_comfyui） | **dead**（本机 ComfyUI 未起） |
| `CodeTeamAdapter` | 运行时自动 | live |
| `ContentDirector` | 运行时自动 | live |
| `codebase-memory-mcp` | `_register_env_codebase_mcp` | live |
| `desktop-touch` | `DESKTOP_TOUCH_MCP_ENABLED=1` | live |
| `omni-video` | `OMNI_VIDEO_MCP_ENABLED=1` | live |
| `video-use` | `VIDEO_USE_MCP_ENABLED=1` | live |
| `weknora` | `register_weknora_mcp` | live |
| `ida-pro` | `register_ida_pro_mcp` | live |
| （内容飞轮 cast/echo/refine/refinery 已计入基础 26） | — | — |

### 3.3 ViMax — 未登记的孤儿 vendored 项目（⚠ §8 接入铁律违反）

- `ViMax/` 完整 vendored 了 saturndec/vi... 短剧生产项目（22KB+17KB README，100+ 文件）
- `AGENTS.md` / `SHANCHUANG_OS_PRODUCT_VISION.md` / `references/ecosystem/INTEGRATIONS.md` / `src/` 全部 **0 命中 vimax**
- 既没登记、也没集成、也没引用 — 纯孤儿 vendored，违反 §8「能用完整开源就用完整的，全部经 references/ 真实源逐字对照」铁律
- **状态**：已在 `INTEGRATIONS.md` §6 加孤儿登记（2026-07-25），后续待用户决策「删除 / 接入 / 改派别」

> 说明：早期版本写"29 适配器类 / 30 文件"为基线未扩、未跑 health_report 时的快照；以 2026-07-25
> `python tools/baseline_snapshot.py` + `hub.health_report()` 实测为唯一真相源。

---

## 4. 内核结构（`src/kernel/`）

**11 个子包：**
| 子包 | 职责 |
|---|---|
| `plugins/` | FabricHub 主路由 + content_flywheel 编排 + 插件登记 |
| `studio/` | 工作流编辑器与模板市场（无代码工作流引擎） |
| `hub/` | 智能体商店（发现/分发） |
| `pulse/` | 使用数据采集与分析 |
| `evolve/` | 智能体自动进化引擎 |
| `layers/` | v1.0 四层结构落地（ModelGateway/AgentRuntime/UI/FallbackChain） |
| `isolation/` | 子进程隔离（B 路线 PoC） |
| `approval/` | Human-in-the-Loop 审批存储与状态机（`/api/approvals` 后端） |
| `context/` | 运行时上下文工程（`/api/context` 后端） |
| `eval/` | 评估框架（`/api/eval` 后端，Task 3） |
| `kernel`根 | 内核顶层 35 个 .py（不在子包内） |

**35 个顶层模块（节选关键）：**
- 物种动能：`evolution.py` / `immunity.py` / `ecology.py` / `live.py`
- 可信记忆：`hippo_scroll.py` / `memory_compression.py` / `memory_distiller.py`（常驻提炼 Agent）
- 横切：`compliance.py`（ContentGuard/PolicyEngine）/ `events.py` / `auth_bridge.py` / `hotswap.py` / `versioning.py` / `skills_bridge.py`
- 装配：`kernel.py` / `aos.py` / `system.py` / `wiring.py` / `interfaces.py` / `types.py`
- 桥接：`v5_bridge.py`（接 legacy brain.py）/ `autopilot.py`
- 其他：`learning_loop.py` / `semantic_state.py` / `run_state_store.py` / `skill_registry.py` / `workflow_engine.py` / `video_maker.py` / `future.py`

---

## 5. API 路由（`src/api/`）

| 文件 | 路由前缀 | 职责 |
|---|---|---|
| `main.py` | 主应用（含 `/api/chat`、`/api/sandbox/exec`、`/api/skills`，挂载 `/studio` 静态前端） | FastAPI 入口，挂载所有子路由 |
| `chat_routing.py` | 直挂 app（与 `/api/chat` 同前缀） | Chat 后端路由决策（单基座第一性，与 `main.py` 协同实现智能切流） |
| `security.py` | 无（中间件，非 router） | `APISecurityMiddleware` 统一鉴权，无凭证→401；`create_access_token(subject, expires_min=None)`，**无 scopes 参数** |
| `gateway.py` | 无（网关装配） | AOS 统一网关（Unified Gateway）装配 |
| `product_flywheel_api.py` | `/api/studio`、`/api/hub`、`/api/pulse`、`/api/evolve`、`/api/proposals` | 内容飞轮平台路由（单文件五 prefix） |
| `autoskill_api.py` | `/api/autoskill` | AutoSkill 全自动技能发现与使用 |
| `review_api.py` | `/api/review` | 步骤级审核控制面 API（三省六部制式「封驳」闭环） |
| `approval_api.py` | `/api/approvals` | Human-in-the-Loop 审批 API（Task 4） |
| `eval_api.py` | `/api/eval` | Eval Framework 评估框架 HTTP 接口（Task 3） |
| `replay_api.py` | `/api/replay` | Replay & Debug 失败回放与单步调试（Task 5） |
| `context_api.py` | `/api/context` | Context Engineering 运行时上下文管理 |
| `kanban_api.py` | 直挂 app（看板道面） | 编排运行可视化看板（任务 ①） |
| `memory_control_api.py` | 直挂 app（记忆控制面） | 可干预记忆控制面 API（任务 ②） |
| `video_api.py` | `/api/video/remotion` | Remotion 视频渲染对外 API（`video.remotion` 能力） |
| `vlm_api.py` | 直挂 app（`/api/multimodal/*`） | 多模态视觉理解 API（暴露 VLMAdapter 端点） |
| `self_harness_api.py` | 直挂 app（`/api/self-harness/run`） | Self-Harness 自测闭环端点 |

> `/api/sandbox/exec` 调 `brain.deerflow.create_sandbox(thread_id=)`，鉴权委托中间件；注入检测在 `_is_command_allowed`（检测到 `; | & && || > >> < \` $()` 即拒，返回 `200 + success=False`，非 4xx）。

---

## 6. 内容飞轮平台（a13c489 新增，已真跑通）

- **5 新适配器**：`content_marketer`/`cast`/`echo`/`refine`/`video_maker`
- **4 内核子包**：`studio`（工作流引擎/模板市场）、`hub`（智能体商店）、`pulse`（使用分析）、`evolve`（自动进化引擎）
- **编排**：`src/kernel/plugins/content_flywheel.py`
- **外部生态**：`src/skills/skillhub_integration.py`（接 SkillHub 外部 7.9 万技能，`AOS_SKILLHUB=1` 启用）、`src/skills/autoskill_agent.py` + `autoskill_engine.py`
- **前端+路由**：`web/studio/index.html` + `product_flywheel_api` + `autoskill_api`
- **验证**：`scripts/test_content_marketer_light.py` 离线真实生成 27.43s mp4（0.38MB），MVP 通过。

---

## 7. 文档都在哪

| 文件 | 讲什么 | 何时看 |
|---|---|---|
| `AGENTS.md` | **项目宪法**（九大核心理念 + 七级决策阶梯 + 基线快照真实规模） | 任何改动前先读 |
| `docs/` | 各专项文档（CAPABILITY_AUDIT / OPEN_FABRIC / GLOBAL_REVIEW / WAIC2026_AOS_MAPPING 等） | 想看专项论证 |
| `AOS_CURRENT_STATE_SNAPSHOT.md` / `AOS_V5_COMPLETION_SUMMARY.md` | v5 时代旧文档，**仍在根目录（18.3KB / 18.9KB，mtime 07-15/07-11，未被真删）**——STATUS.md 此前误报"已删"，2026-07-19 explore 真机核验纠偏 | 待删除（破坏性，需用户点头） |
| `docs/retro/` | 历史审计 / 反思复盘归档目录（含 `RETRO-2026-07-19_audit-p0p1p2.md` + `README.md` 索引）。**非真相源**，仅供回溯 | 看历史决策时翻，数字不视为现状 |

---

## 8. 代码都在哪（关键目录）

```
src\
  core\fabric\           接线板：capability/registry/protocols + adapters/(29)
  kernel\                v1.0 内核：11 子包 + 35 顶层模块
  api\                   16 路由文件（main/security/gateway/chat_routing/product_flywheel/autoskill/review/approval/eval/replay/context/kanban/memory_control/video/vlm/self_harness）
  skills\                manifest.json(33技能) + autoskill + skillhub_integration
  hermes\                LLM 桥（AOS_FABRIC_LLM=1 走 FabricHub）
  subagents\             IMA 等子智能体
  aos_mcp\               对外 MCP server（B 路线；2026-07 从 `mcp/` 重命名以避官方 mcp SDK 命名遮蔽）
web\studio\index.html    内容飞轮前端
tests\                   139 测试文件 / 955 测试函数
scripts\                 74 个验证脚本（test_* 手动跑，非 pytest 套件）
```

---

## 9. 怎么跑（验证）

```bat
:: 跑测试（系统 Python 3.14，PYTHONPATH=src）
set PYTHONPATH=src
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/ -q

:: 单文件（内容飞轮离线验证，真生成视频）
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe scripts/test_content_marketer_light.py

:: 编译检查未提交 py
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m py_compile <file>
```

- 测试基线（2026-07-25 真机实测）：`tests/` 共 **178 文件 / 1139 个 test_ 函数**
  （2026-07-19 旧基线 139/955 已过期）。
  近端绿绿回归套（沙箱 30s timeout 实跑）：`test_causal.py + test_mcp_fabric_exposure.py + test_approvals_routes.py` **17/17 PASS（3.33s）**
  （旧记录 10/6/1 = 17 个，已收敛在 17/17 PASS）。
  全量套需在主机以 `pytest tests/ -q --timeout=60` 跑（沙箱 120s 超时能力不足以跑全量，部分子进程 prewarm 仍会卡死）。
- **反思闭环 mock 端到端首验 PASS**（2026-07-25）：`scripts/self_evo_loop_verify.py` 实跑通过，
  6 阶段按序推进 + 教训自动注入下一轮 analyze，**但仍只是机制层级**（真 LLM 端到端未验）。
- FabricHub 空构造较重（~分钟级），测试用 module 级 fixture 复用。

---

## 10. 工作区状态（2026-07-19 真机核验）

工作区 clean，分支与 `origin/feature/infra-setup` 已同步至 `3dafee2`（远端已 push）。仅 3 项 untracked：
- `RETRO-2026-07-19_audit-p0p1p2.md`（10 KB，上轮 P0/P1/P2 修复的反思复盘草稿，待归档）
- `AOS_VS_WAIC2026_对比分析报告.docx`（23 KB，外部对比研究产物）
- `.scratch/`（空目录，无内容）

> 上一轮提到的 5 个根目录开发垃圾（`debug_pulse.py` / `debug_templates.py` / `honest_check.py` / `test_autoskill.py` / `test_autoskill_e2e.py`）均已从工作区清理。

---

## 11. 风险与下一步

1. **双轨未合流**：FabricHub 与 brain.py legacy 并存；`/api/chat` 灰度兜底，目标 FabricHub 唯一运行时。
2. **QQ 脱敏不一致**：`ContentGuard.check()` 能检测 QQ 号但 `_redact()` 替换表不含 QQ（phone/id_card/bank_card/email/api_key 才遮），属设计缺口非 bug，留待后续补。
3. **2026-07-19 全量审计跟进**：P0/P1/P2/P3 + TD-3/TD-7/TD-8/TD-9/TD-10 已在 `feature/infra-setup` 分支完成（审计报告 `AOS_CODE_AUDIT_REPORT.docx`）。TD-1（brain.py 2091 行单体）/ TD-2（web/app.py 4299 行）属大工程，未在本轮处理；TD-5（导入风格不统一，≥12 文件用绝对导入）改可能触发 import 紊乱，暂跳过；TD-6（system.py 占位）核实后仅 `_heal_isolate` 返 True 算 stub，不阻塞。
4. **全量 pytest 从未单轮跑完**（新增）：`tests/` 955 个 test_ 函数从未在本会话做过单轮全绿验证（沙箱 120s 超时不足以跑全量），需在主机以 `pytest tests/ -q --timeout=60` 首次诚实确认全盘绿/红。

## 12. 诚实校准：已真验 / 待端到端验证（2026-07-24 补）

> 本节是**诚实纪律（§0.7.1）**的落地：把「代码改动真 / 芯粒真跑 / 端到端真验」三层
> 显式分开，杜绝把「接线就绪」说成「跑通」。凡标注「待验证」的，沙箱与当前会话
> 均未端到端跑过，需真 LLM + 主机方能确认。

**✅ 已真验（可命令复现）：**
- 芯粒层：`agnes` / `ag2` / `OpenClaw` 真实跑通（非 mock）；验证见各自适配器单测。
- BYOK：`Fernet` 加密 + 租户隔离存储层真写真读；租户模型配置 API + UI 页已编译验证。
- 聊天主干「炼化为一体」：默认走 `litellm` 统一平面（commit `060eb13`），智谱 3 圈真跑通。
- 内容飞轮：搜索 → LLM 写脚本 → 本地 `ffmpeg`+`edge-tts` 真生成视频（27.43s mp4 离线验证）。
- 诚实自进化三 MVP（白皮书 + `270` 诚实自进化闭环 + `271` 抗复合失败 + `272` 白盒蒸馏引擎）均真跑验证并 push。

**⏳ 待端到端验证（需真 LLM + 主机，沙箱重型链跑不动，当前会话未验）：**
- **自进化闭环「跑一轮 → 反思 → 下一轮变好」**：
  - ✅ **机制已验（mock 模式，2026-07-25）**：`scripts/self_evo_loop_verify.py` 实跑 PASS——
    6 阶段按序推进 `[analyze, promote, acquire, deliver, evolve, maintain]` + 教训自动注入下一轮 analyze
    （首轮 acquire 失败后，下一轮 analyze 已携带历史教训片段）。证明控制流与教训反馈闭环真实可用。
  - ⏳ **真 LLM 端到端仍未验（这是用户核心痛点）**：`--real` 模式需主机 + 真 LLM key，
    沙箱无 key 故阻塞。主机命令：`python scripts/self_evo_loop_verify.py --real`。
  - 不谎报：上面只是机制/控制流验证，非真 LLM 跑通。
- 全量 `pytest` 从未单轮全绿（需主机 `pytest tests/ -q --timeout=60` 首次诚实确认）。

**📁 配置拓扑澄清（回应「双配置并存」疑点）：**
- `config/` 与 `configs/` 是历史遗留的**孤立配置目录**，**AOS Python 包不 import 它们**
  （真实配置模块是 `src/utils/config.py`，从 `.env`/env 加载）。
- 二者命名相近但职责不同：`configs/` = 基础设施/部署配置（docker-compose / postgres /
  temporal 消费）；`config/hermes/` = Hermes 子系统配置 + 运行时产物。
- **结论：不盲合**（盲合会破坏外部工具引用）；已分别加 `README.md` 厘清。详见各目录 README。

> AI生成