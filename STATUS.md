# AOS 项目状态总地图（STATUS）

> 这是一份**导航索引**，不是技术文档。每次大状态变动更新这里。
> 最后更新：**2026-07-18**（取代 2026-07-10 的 v5→v1.0 旧文，旧文已严重失实，本次整体重写）。

---

## 0. 一句话现状（2026-07-18）

AOS 已完成"融为一体"重构：以 **FabricHub（单基座能力路由器）** 为干净运行时，统一持有路由/记忆/上下文主权并调度各芯粒适配器；legacy 的 `brain.py` 仍作 `/api/chat` 灰度兜底（双轨尚未合流）。在此之上新增了**内容飞轮平台**（Studio/Hub/Pulse/Evolve + 5 适配器 + SkillHub/AutoSkill 集成），端到端已真跑通（搜索→LLM 写脚本→本地 ffmpeg+edge-tts 生成视频）。

**规模（实测，非记忆）：26 适配器类 / 27 文件 · 702 测试函数 / 109 文件 · 33 技能（manifest）· 7 内核子包 + 31 内核顶层模块 · 5 个 API 路由文件。**

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
        26 芯粒适配器   内核子包(7)      内容飞轮平台      外部生态
        (adapters/)  (kernel/*/)   (studio/hub/pulse/   (SkillHub 7.9万
                                  evolve + 5适配器)      技能 / IMA / WeKnora)
```

**双轨未灭**：FabricHub 新栈 与 legacy（`core/brain.py` + `deerflow`/`swarm_flow`/`lemon_orchestrator`）并存互不打通；`/api/chat` 仍灰度调 brain.py 兜底。**目标 FabricHub 为唯一运行时**（尚未合流）。

---

## 3. 26 个 FabricHub 适配器（`src/core/fabric/adapters/`）

按"真实开源绑定 vs AOS 自研"分类（核实结论，不编造）：

**真实开源薄适配层（接已验证的开源项目）：**
| 适配器 | 绑定开源 | 角色 |
|---|---|---|
| `OpenClawAdapter` | OpenClaw 网关（嘴耳/接入） | 多通道接入 |
| `LiteLLMAdapter` | LiteLLM | 统一 100+ LLM 推理网关 |
| `Mem0Adapter` | Mem0 | Graph-RAG 长期记忆 |
| `LangfuseAdapter` | Langfuse | tracing/eval/观测 |
| `BrowserUseAdapter` | browser-use | 浏览器动手/ACI |
| `AG2Adapter` | AG2（AutoGen 社区分叉, MIT） | 群聊编排 |
| `MCPClientAdapter` / `MCPStdioAdapter` | MCP 协议 | 接任意外部 MCP Server |
| `MiniCPMOAdapter` | MiniCPM-o（OpenBMB, 全双工语音） | 语音/全模态 |

**AOS 自研/自包含功能适配器：**
| 适配器 | 做什么 |
|---|---|
| `AgnesAdapter` | 多模态平面 |
| `ContentMarketerAdapter` / `CastAdapter` / `EchoAdapter` / `RefineAdapter` / `VideoMakerAdapter` | 内容飞轮：搜索→写脚本→生成视频→分发→回声→优化（ffmpeg+edge-tts 本地生成） |
| `CodeExecutionAdapter` / `FileAdapter` / `ScriptsAdapter` | 本地代码/文件/脚本执行 |
| `SearchAdapter` / `WebFetchAdapter` | 多源联网搜索/抓取 |
| `LFMAdapter` / `LNNAdapter` / `VLMAdapter` / `STTAdapter` / `TTSAdapter` / `ThreejsAdapter` | 模型/模态能力（本地或外部模型） |

> 说明：`LFM`/`LNN`/`VLM` 等适配器的具体后端在文档化时未逐一核实，此处只描述功能，避免编数据。

---

## 4. 内核结构（`src/kernel/`）

**7 个子包：**
| 子包 | 职责 |
|---|---|
| `plugins/` | FabricHub 主路由 + content_flywheel 编排 + 插件登记 |
| `studio/` | 工作流编辑器与模板市场（无代码工作流引擎） |
| `hub/` | 智能体商店（发现/分发） |
| `pulse/` | 使用数据采集与分析 |
| `evolve/` | 智能体自动进化引擎 |
| `layers/` | v1.0 四层结构落地（ModelGateway/AgentRuntime/UI/FallbackChain） |
| `isolation/` | 子进程隔离（B 路线 PoC） |

**31 个顶层模块（节选关键）：**
- 物种动能：`evolution.py` / `immunity.py` / `ecology.py` / `live.py`
- 可信记忆：`hippo_scroll.py` / `memory_compression.py` / `memory_distiller.py`（常驻提炼 Agent）
- 横切：`compliance.py`（ContentGuard/PolicyEngine）/ `events.py` / `auth_bridge.py` / `hotswap.py` / `versioning.py` / `skills_bridge.py`
- 装配：`kernel.py` / `aos.py` / `system.py` / `wiring.py` / `interfaces.py` / `types.py`
- 桥接：`v5_bridge.py`（接 legacy brain.py）/ `autopilot.py`
- 其他：`learning_loop.py` / `semantic_state.py` / `run_state_store.py` / `skill_registry.py` / `workflow_engine.py` / `video_maker.py` / `future.py`

---

## 5. API 路由（`src/api/`）

| 文件 | 路由 |
|---|---|
| `main.py` | 主应用：`/api/chat`、`/api/sandbox/exec`、`/api/skills`、挂载 `/studio` 静态前端 |
| `security.py` | `APISecurityMiddleware`（统一鉴权，无凭证→401；含 `create_access_token(subject, expires_min=None)`，**无 scopes 参数**） |
| `gateway.py` | 网关装配 |
| `product_flywheel_api.py` | 内容飞轮平台路由 |
| `autoskill_api.py` | AutoSkill 路由 |

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
| `AOS_CURRENT_STATE_SNAPSHOT.md` / `AOS_V5_COMPLETION_SUMMARY.md` | 旧时代（v5）文档，**已失实，待清理** | 不建议参考 |

---

## 8. 代码都在哪（关键目录）

```
src\
  core\fabric\           接线板：capability/registry/protocols + adapters/(26)
  kernel\                v1.0 内核：7 子包 + 31 顶层模块
  api\                   5 路由文件（main/security/gateway/product_flywheel/autoskill）
  skills\                manifest.json(33技能) + autoskill + skillhub_integration
  hermes\                LLM 桥（AOS_FABRIC_LLM=1 走 FabricHub）
  subagents\             IMA 等子智能体
  mcp\                   对外 MCP server（B 路线）
web\studio\index.html    内容飞轮前端
tests\                   109 测试文件 / 702 测试函数
scripts\                 15 个验证脚本（test_* 手动跑，非 pytest 套件）
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

- 测试全绿基线：本批次 47 飞轮相关用例 + 既有 655 → 合计 **702 函数** 全绿。
- FabricHub 空构造较重（~分钟级），测试用 module 级 fixture 复用。

---

## 10. 工作区未提交项（5 个，刻意不进库）

以下 5 个根目录调试/草稿脚本**未提交**（纯开发垃圾，留在工作区不丢，不污染正式历史）：
- `debug_pulse.py` / `debug_templates.py`（子包调试）
- `honest_check.py`（495 行诚实自检）
- `test_autoskill.py` / `test_autoskill_e2e.py`（AutoSkill 验证草稿）

> 若日后要保留，建议挪进 `scripts/` 或单独归档，再从根目录删除。

---

## 11. 风险与下一步

1. **双轨未合流**：FabricHub 与 brain.py legacy 并存；`/api/chat` 灰度兜底，目标 FabricHub 唯一运行时。
2. **文档滞后**：`AOS_CURRENT_STATE_SNAPSHOT.md` / `AOS_V5_COMPLETION_SUMMARY.md` 仍 v5 时代，建议整体重写或删除（本次已重写 STATUS.md 与 AGENTS.md）。
3. **未 push**：`a13c489`/`5e889c3` 需 `git push origin feature/infra-setup`（沙箱已同步主机仓库，但远端要你手动推）。
4. **QQ 脱敏不一致**：`ContentGuard.check()` 能检测 QQ 号但 `_redact()` 替换表不含 QQ（phone/id_card/bank_card/email/api_key 才遮），属设计缺口非 bug，留待后续补。
