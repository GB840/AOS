# AOS 全方位分析：经验 × 逻辑 × 认知理念

> 分析时间：2026-07-19
> 立场：基于**可复核代码与真跑证据**（概念9），不凭记忆空谈。每条评级附证据与置信度。
> 证据底座：本次实跑 `89 + 80 + 14 + 23 = 206` 用例全过（见文末证据链）。
> 评级图例：✅ 已落地（有代码+可跑证据）｜🟡 部分落地（架构在/局部实现/有缺口）｜❌ 缺口（偏离或未实现）

---

## 一、认知理念透镜（宪法标尺）

以 AGENTS.md §1 的十条（九大理念 + 2.5 反思闭环铁律）为标尺逐条评级。

| # | 理念 | 评级 | 一句话 |
|---|------|------|--------|
| 1 | 不手配，自闭环 | 🟡 | 链路在，但冷启动 8–10min 重型 import + 部分能力需 env，非"秒级自闭环" |
| 2 | 失败即训练数据，记忆有生有灭 | ✅(侧车) | "失败→提炼"落地；TTL/热度/分层降级**已实现**（`memory_lifecycle.py`，收口 commit dcf598c），默认接入 `MemoryDistiller` 侧车 + `/api/memory/lifecycle`；**未**接入 legacy `memory.py` 主记忆通路（属双轨债收尾） |
| 3 | 芯粒隔离 ≠ 多 Agent 分解 | ✅ | 故障熔断隔离清晰，单内核独占主权 |
| 4 | 万物为我所用，无绑定 | ✅ | 六级检索源、本地/云端记忆、多后端，零付费必选项 |
| 5 | 能力即路由，权限即边界 | ✅ | `advertise_capabilities` + `security.py` 三层入口鉴权真落地 |
| 6 | 诚实 + 量化置信 | ✅ | RepairReport、真实 health 探测、三级置信表，纪律最强 |
| 7 | 千人千面 | 🟡 | 框架在、样本少，环境适配未全量实测 |
| 8 | 黑盒不可训，白盒可进化 | ✅ | `trace_store.py` + `memory_distiller.py` 真有 |
| 9 | 可验证即真理 | ✅ | 本次分析全程贴证据，虚假记忆四连被纠 |
| 2.5 | 目标驱动·长程自主·反思闭环 | 🟡 | `autopilot.py` 实现完整；与 FabricHub 新栈融合深度待查 |

### 1. 不手配，自闭环 — 🟡 部分
- **证据**：自然语言目标→路由→执行链路存在（`OrchestrationChiplet`、`autopilot.py`）；冷启动空记忆库设计上有"搜索→判断→执行"核心链路。
- **缺口**：重型模块首次冷导入实测 **8–10 分钟**（`pytest` 全量套件、verify 脚本均如此）；部分能力需 env（API key）才激活。
- **置信**：高（冷导入耗时实测；`.env` 有真实 key 依赖）。

### 2. 失败即训练数据，记忆有生有灭 — ✅ 已落地（侧车默认启用，主通路待接）
> **【更正 · 2026-07-19 收口后】** 本节原写"TTL/分层降级零实现"，**已过时**。收口阶段已实现 `src/kernel/memory_lifecycle.py`（`MemoryLifecycleManager`：TTL 过期 + 访问热度延缓 + 四档分层降级 ETERNAL/IMPORTANT/NORMAL/ARCHIVED + 偏好永生 + 量化报告），并接入 `MemoryDistiller` 常驻循环（`scan_once`→register+prune）与 `/api/memory/lifecycle` 端点；`get_distiller()` 默认推导生命周期路径**默认启用**。测试：`test_memory_lifecycle.py`（9 passed）+ `verify_memory_lifecycle.py`（32/32）。见收口 commit `dcf598c`。**残留缺口**：该循环目前只覆盖 `distilled_memory.jsonl` 蒸馏侧车，尚未接入 legacy `src/memory/memory.py` / `brain.py` 主记忆读写通路——记忆"有生有灭"在生产主路径上仍不生效，属双轨债收尾项。

- **证据（落地侧）**：`memory_distiller.py` 常驻提炼；`memory_lifecycle.py` 完整生命周期；`autopilot.py` 的 Meta-Trace `reflection_memory.jsonl`（双层 TTL 淘汰）；`tool_call_repair.py` + `RepairReport`。
- **证据（主通路缺口）**：`src/memory/memory.py` 自建 raw-SQLite 记忆库，不调用 `memory_lifecycle`；`grep memory_lifecycle` 在 `fabric_hub.py`/`main.py`/`memory.py` 全空——蒸馏侧车已闭环，主记忆通路未接。
- **结论**："失败即训练数据"成立；"记忆有生有灭"**在蒸馏侧车已落地且默认启用**，主记忆通路待接（双轨债收尾）。

### 3. 芯粒隔离 ≠ 多 Agent 分解 — ✅ 已落地
- **证据**：`ag2`/`agnes` 子进程隔离 = crash boundary；`FabricHub` 单例独占全局路由/记忆/上下文主权；memory 明确"隔离为容错不为拆分"。
- **置信**：高。

### 4. 万物为我所用，无绑定 — ✅ 已落地（最强项）
- **证据**：`web.search` 六级源级联（AnySearch→百度→Bing→DDG→Jina→智谱）；mem0 本地 Chroma / 云端自由切换（`AOS_MEM0_LOCAL=1`）；推理本地 ollama / 云端；WeKnora / IMA / 多 MCP 后端；无一付费必选项。
- **置信**：高。

### 5. 能力即路由，权限即边界 — ✅ 已落地（原低估，已修正）
- **证据（能力路由）**：适配器 `advertise_capabilities()` + `FabricHub.route()` 按能力调度；`fabric_hub.py` 中 ~27 引擎经 `self._registry.register(adapter, route_fn=self.route)` 接线。
- **证据（权限边界，代码实锤）**：`src/api/security.py` 的 `APISecurityMiddleware` 实现 **Bearer JWT / 静态 API-Key / 上游令牌** 三层入口鉴权；`main.py:642 issue_token` 发 JWT 端点；`gateway.py` 上游调用自动带 `Authorization: Bearer`。
- **缺口**：沙箱命令执行的"白名单 + 资源限额（CPU/内存/超时）"层未在本次检索中确认，但"能力路由 + HTTP 入口鉴权"主体已闭环。
- **置信**：高（鉴权代码真实存在且可读）。

### 6. 诚实 + 量化置信 — ✅ 已落地（纪律最强）
- **证据**：`tool_call_repair` 量化 `RepairReport`；`health()` 真实探测（Remotion 探 `npx`、agnes 探 URL `<500` 判 live）；三级置信表（低0/中1-4/高≥5）；本次分析全程贴可复核证据。
- **置信**：高。

### 7. 千人千面 — 🟡 部分
- **证据**：IMA 结构化交接、环境偏好长周期保留框架在；memory 区分"短期故障记忆 vs 长期环境偏好"。
- **缺口**：系统年轻，实际个性化沉淀样本少；`winget`/`choco` 等环境适配未全量实测。
- **置信**：中。

### 8. 黑盒不可训，白盒可进化 — ✅ 已落地
- **证据**：`src/core/fabric/trace_store.py` 结构化 JSON Trace 落盘；`src/kernel/memory_distiller.py` 从 trace 自动提炼；`autopilot.py` 反思记忆。最小 Trace schema 与 AGENTS.md 对齐。
- **置信**：高。

### 9. 可验证即真理 — ✅ 已落地（本次即范例）
- **证据**：所有声明附证据链（URL/stdout/相似度）；本次验证 206 用例全贴；**虚假记忆四连被纠**（IMA 初记错 / meetily 无实体 / Moshi.cpp 假 / mistralrs·CodeWhale 未注册）。
- **置信**：高。

### 2.5 目标驱动·长程自主·反思闭环 — 🟡 部分
- **证据**：`autopilot.py` 目标驱动 + 每步硬判定（`_*_real_metrics` + `_verdict`）+ 反思重设计（`_reflect_and_redesign`）+ Meta-Trace；`OrchestrationChiplet.seed_context` 跨轮续接。
- **缺口**：`MAX_REFLECT≤2` 上限、质疑 agent 真实诊断能力未端到端实测跑通证据；`autopilot` 与 FabricHub 新栈融合深度待查（可能仍走 legacy）。
- **置信**：中。

---

## 二、逻辑透镜（架构自洽性）

### 2.1 第一性守恒：单基座 + Skill 芯粒 — ✅
`FabricHub` 单例（`get_fabric_hub()`）统一持有路由/记忆/上下文；`agnes`/`ag2` 是被调度的隔离计算单元，非自治多 Agent。逻辑自洽，memory 明确"勿把隔离当多 Agent"。

### 2.2 故障隔离 vs 自治分解边界 — ✅ 清晰
chiplet = crash boundary，配 `subprocess_iso` 传输退避（Named Pipe→tcp）。隔离目的明确，无"自治协商"歧义。

### 2.3 能力路由 = 权限边界 — ✅（原疑点已消）
适配器只 advertise 能力，hub 只按能力调——能力边界即权限边界（无需 TOML）；"谁都能调"靠 `security.py` 三层入口鉴权补。逻辑闭环成立。

### 2.4 双轨债（最大逻辑破口）— ❌
`FabricHub` 新栈 与 legacy（`core/brain.py` / `deerflow` / `swarm_flow` / `lemon_orchestrator`）**并存互不打通**；`/api/chat` 仍灰度调 `brain.py` 兜底。
- **逻辑风险**：两套路由/记忆/上下文主权，直接违反"单基座"第一性（2.1）；维护双倍、易漂移、难审计。
- **置信**：高（memory + `main.py` 灰度代码证实）。

### 2.5 三级档位路由 — 🟡
`capability.py` 的 `TIER_HIGH/MED/LOW/AUTO` + 全局级联（高→中→低）；`MiniCPMOAdapter` 参与。逻辑闭环成立，但"本地用不了就云端"的逆兜底需实测。

### 2.6 结构化交接信封缺口 — ❌
`OrchestrationChiplet` 当前传递**原始数据**，而非带 `facts/assumptions/risks` 的结构化信封（`handoff.py` 已建 `HandoffEnvelope` 但未全量接进编排链）。逻辑上"白盒进化"的 trace 数据源有，但跨步语义信封是缺口。

---

## 三、经验透镜（构建历程复盘）

### 3.1 四连虚假记忆（最贵教训）
| 误记 | 真相（核实后） | 处置 |
|------|----------------|------|
| IMA 是空想产品 | IMA = 腾讯真实产品 + OpenAPI + 开源 MCP | 已真打通 OpenAPI 读写（返回 note_id） |
| meetily 有真实 subagent | 无真实 subagent，仅 `agency_roles/` 角色 skill | 按铁律**不伪造接入** |
| Moshi.cpp 存在 | 无 C++ 版（Kyutai 为 Rust/MLX） | 记忆剔除 |
| mistralrs / CodeWhale 已注册 | 仅外部愿景，非注册引擎名 | 不凭空造组件 |

**教训**：凡外部依赖先全网核实（用户铁律），不凭记忆或想象下结论。

### 3.2 诚实化修复（落地不谎报）
- IMA 同形接法集成（subagent + skill + 4 个 `/api/ima/*` + 结构化交接存→取闭环真跑）。
- WeKnora 真实核实（腾讯开源 MIT）走 `MCPClientAdapter` + `register_weknora_mcp` 接入，不可达静默跳过不谎报。
- Remotion 真实 CLI 降级（缺 project/未装 CLI → `ok=False` 不谎报）。

### 3.3 验证纪律（本次）
- 单测 `monkeypatch` mock 网络零联网（`test_vlm_adapter.py` 37 用例等）。
- `py_compile` 全改动文件语法校验通过。
- 真跑证据：89 + 80 + 14 + 23 = **206 用例 passed**。

### 3.4 当前收口状态
- **Tier1 四块全落地**：① 看板 ② 记忆 ③ Remotion 质量视频 ④ 步骤级审核封驳。
- 草稿清入 `.scratch/`（同盘可恢复），仓库仅留合法文件。
- **28 条文件已精确暂存**，仅 `.scratch/` 与 `.docx` 排除，待 commit + push。

---

## 四、全方位综合

### 4.1 完成度矩阵
| 维度 | 状态 |
|------|------|
| 核心理念（10 条） | 6✅ / 4🟡 / 0❌ |
| Tier1 功能 | 4/4 全落地 |
| 子系统 | eval / evolve / studio / approval / replay 已建 |
| 验证 | 206 用例 passed |
| 双轨债 | ❌ 未清（最大风险） |
| 提交 | 暂存完成，未 push |

### 4.2 残存风险清单（诚实，带置信+证据）
1. **双轨并存** ❌ 高 — 单基座第一性被破坏风险（`main.py` 灰度 `brain.py` 证实）。
2. **brain.py 仍兜底** ⚠️ 高 — `/api/chat` 未切 FabricHub，两套主权漂移。
3. **概念2 主通路未接** 🟡 中 — `memory_lifecycle` 已实现+默认启用（收口 dcf598c），但仅覆盖蒸馏侧车 `distilled_memory.jsonl`，未接入 legacy `memory.py` 主记忆通路（双轨债收尾项）。
4. **legacy 测试失败** ⚠️ 中 — `test_database`/`test_memory` no such table（勿误修）。
5. **agnes health 探测弱** 🟡 中 — 探配置 URL `<500` 即 live，未探真实能力。
6. **vef 日志不完整** 🟡 中 — 本次 `verify_eval_framework.py` 未产出可读总结（但 eval 已被 89 套件 `test_eval_harness` 覆盖，**非盲区**，不谎称通过）。
7. **冷导入 8–10min** ⚠️ 中 — 首次重型 import 慢，CI/体验风险。
8. **概念2.5 与 FabricHub 融合** 🟡 中 — `autopilot` 是否走新栈未端到端证实。

### 4.3 优先级路线图
- **P0（立即）**：提交 push 当前 28 条（已暂存、已验证）→ 启动清双轨（brain.py 灰度切 FabricHub）→ 单轨验证。
- **P1（部分已完成）**：概念2 记忆 TTL/分层降级**已实现**（dcf598c，侧车默认启用）；剩余=接入 legacy 主记忆通路 + agnes health 真探测 + vef 补可读输出。
- **P2**：结构化交接信封接进 `OrchestrationChiplet`；千人千面样本积累；冷导入优化（懒加载/预编译）。

---

## 五、结论

**AOS 当前是「理念骨架完整、运行时强项突出、双轨债与记忆降级待补」的自主闭环系统：**

- **认知理念 10 条**：6 条扎实落地（隔离 / 无绑定 / 诚实 / 白盒 / 可验证 / 权限边界），4 条部分（自闭环速度 / 记忆降级 / 千人千面 / 反思闭环深度）。
- **逻辑**：单基座第一性守恒、故障隔离清晰、能力=权限闭环；但**双轨并存 + 记忆降级缺失**是两个自洽性破口。
- **经验**：爬出过"四连虚假记忆"，已建立"先核实再落地 + 真跑证据链"的纪律，本次 206 用例全过。

**最关键下一步**：清双轨统一运行时（brain.py 灰度切 FabricHub、legacy `memory.py` 主通路接入 `memory_lifecycle`）——概念2 已在侧车落地（dcf598c），下一步是把它从"侧车"升到"主记忆通路"，消除两套记忆主权的漂移。

---

## 附：验证证据链（概念9 自证）

| 验证 | 命令/脚本 | 结果 |
|------|-----------|------|
| 单元套件 A（4 文件） | `pytest test_approval_store/test_eval_harness/test_evolve_engine/test_replay_debug` | **89 passed** |
| 单元套件 B（3 文件） | `pytest test_context_manager/test_self_harness/test_vlm_adapter` | **80 passed** |
| Remotion 适配器 | `verify_remotion.py` | **14/14 通过** |
| 路线图端到端 | `verify_roadmap_features.py` | **23 passed, 0 failed**（Eval/Replay/HITL/内容回写） |
| 语法校验 | `python -m py_compile` 全改动文件 | COMPILE_ALL_OK |
| eval 框架（诚实标注） | `verify_eval_framework.py` | 日志仅留环境提示、无可读总结；eval 已被 89 套件覆盖，非盲区 |

**总用例：206 passed。** 所有结论均附代码路径或真跑结果，拒绝模糊描述。
