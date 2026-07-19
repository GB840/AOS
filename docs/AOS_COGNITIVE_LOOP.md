# AOS 认知闭环架构：感知-理解-规划-控制-反馈
## AOS Cognitive Loop Architecture

> 本文档定义 AOS 自主执行的认知闭环，是系统从"输入"到"输出"再到"自我优化"的权威流程描述。
> 所有节点均经真实代码核实（2026-07-20，见第 2 节代码行号证据）；外部愿景组件诚实标注为"未集成"。
> 本文档替代一切"愿景地图"式的 AOS 架构描述——以代码为准，不以想象为准。

---

## 0. 一句话定位

AOS 的认知闭环不是一个理论模型，而是 `kernel/autopilot.py` 里真实运行的 `run()` 主循环：
**规划 → 执行 → 硬闸门 → (完成 | 反思重设计 → 回执行) → 诚实报 exhausted**。
每一步都有代码行号证据，每个"已落地"断言都可复核。

---

## 1. 核验后的完整流程图

```
目标输入
  │
  ▼
规划（ag2 / heuristic，可产 parallel_groups）
  │  ← 首轮可并发（AOS_AUTOPILOT_PARALLEL=1）；反思轮保持串行
  ▼
执行（FabricHub.route → 适配器，首轮可并发）
  │  ← 默认经 FabricHub 统一路由（AOS_AUTOPILOT_USE_FABRICHUB 默认1）
  ▼
硬闸门（real_metrics.is_real：这步算不算数？）
  │  ← 每个能力执行后产 real_metrics，判定 is_real（非"自称成功"）
  │
  ├─ 全通过 → 交付物验证（_verify_deliverable）→ 完成 ✅
  │           ← 检查 wrote_file 匹配 target + wrote_bytes>0
  │
  └─ 有失败 → 反思（四块齐上）：
                ① 因果模型（_compute_causal_hints：白盒蒸馏器选"换引擎"建议）
                ② 历史教训（Meta-Trace _load_lessons：跨任务失败→修正经验）
                ③ 上轮成功产出（prior_success 注入：供剩余步引用）
                ④ LLM 诊断（三后端降级：ag2 → ollama → heuristic）
                │
                ├─ 反思无效/三后端全挂 → 停止避免空转 ⏹
                │                       （记 no_redesign，不继续重试，防死循环）
                │
                ▼
              重设计（全新计划，提示词强制"只产剩余步骤，已成功步不重做"）
                │
                ▼
              回到执行（新计划天然只含剩余步 + seed_context 注入上轮产出）
                │  ← 机制：非"执行时跳过已成功步"，是"新计划本身不含已成功步"
                │
                └─ 达上限仍未达成 → 诚实报 exhausted ❌
                                   （exhausted=True，不伪造成功）
```

---

## 2. 逐节点代码行号证据

| 流程图节点 | 真实代码位置 | 核验结论 |
|---|---|---|
| 目标 → 规划 | `run()` `autopilot.py:1637` → `_plan()` `:1015` | ✅ ag2/heuristic 双路径 |
| 规划可产 parallel_groups | `_plan()` `:1015` + `plan_bridge.plan_with_parallelism` | ✅ 首轮可并发，反思轮串行 |
| 执行经 FabricHub | `_execute()` `:1074` → `_dispatch()` `:101` → 默认经 FabricHub | ✅ `AOS_AUTOPILOT_USE_FABRICHUB` 默认1（commit 652a69c） |
| 硬闸门 real_metrics | `_route()` `:609` 产 `real_metrics.is_real` | ✅ 三能力各有闸门：`_search_real_metrics:875` / `_code_exec_real_metrics:889` / `_inference_real_metrics:907` |
| 交付物验证 | `_assemble()` `:1476` → `_verdict()` `:1834` → `_verify_deliverable()` `:917` | ✅ 检查 `wrote_file` 匹配 target + `wrote_bytes>0` |
| 失败判定 | `_needs_reflection()` `:1150` | ✅ verdict.status 非"完成"且未"产物落盘"→ 需反思 |
| 反思四块 | `_reflect_and_redesign()` `:1305` | ✅ 因果`:1333` + 教训`:1348` + prior`:1336` + LLM`:1362` |
| 因果模型 | `_compute_causal_hints()` `:234` + `_get_causal_distiller()` `:145` | ✅ 白盒蒸馏器选换引擎建议 |
| 历史教训 | `_load_lessons()` `:1178` + `_save_lesson()` `:1234` | ✅ Meta-Trace JSONL 持久化，TTL 7/90 天 |
| LLM 三后端降级 | `_reflect_and_redesign()` `:1376-1406` | ✅ ag2 → ollama → heuristic 重试 |
| 反思无效停止 | `_advance_cycle()` `:1615-1620` | ✅ `not refl or not refl.get("steps")` → 记 no_redesign → 停 |
| 重设计全新计划 | `parse_plan_to_steps()` `:1384` → `s.steps=refl["steps"]` `:1632` | ✅ 整体替换，非微调 |
| 只跑剩余步 | 提示词 `:1370` + `seed_context` `:1596-1602` | 🔶 机制：新计划本身只含剩余步 + seed 注入上轮产出 |
| 达上限 exhausted | `cycle>=max_reflect` `:1611` → `exhausted=_needs_reflection(s.last)` `:1670` | ✅ 诚实报，不伪造 |

---

## 3. 三个精确化说明（流程图没画全的）

### 3.1「只跑剩余步」的机制

**效果**：重设计后不重做已成功步。
**机制**：不是"执行时遍历跳过已成功步"，而是：
1. 反思提示词（`:1370`）明确要求："只产出从失败处继续、直到完成原始目标所需的剩余步骤——已经成功的步不要重做"
2. 所以反思产出的新计划**本身就不含已成功步**
3. 加上 `seed_context`（`:1596-1602`）把上轮已成功产出注入，让剩余步能通过 `in_from:initial` 引用

效果与"跳过已成功步"相同，但机制更干净——新计划天然只含剩余步。

### 3.2 反思无效 → 停止（防死循环护盾）

流程图主链画了"反思 → 重设计 → 回执行"，但遗漏了**反思无效的分支**：
- `_advance_cycle()` `:1615-1620`：若反思未产出有效修正计划（`not refl or not refl.get("steps")`）
- → 记 `no_redesign`（reason: "反思未产出有效修正计划，停止避免空转"）
- → **返回 False，停止循环**

这是防死循环的护盾——反思三后端全挂或 LLM 产不出有效计划时，系统会诚实停止，而不是无限重试。

### 3.3 反思 LLM 三后端降级链

流程图画了"LLM 诊断"一个块，实际反思 LLM 有**三后端降级**（`:1376-1406`）：
```
ag2（首选，质量最高）→ ollama（本地，ag2 dead 时）→ heuristic 重试（兜底）
```
- heuristic 兜底只重发失败能力，不编造新计划（`:1401-1406`）
- 三后端全不可用才返回 None（触发 3.2 的"反思无效停止"）

这保证"反思"不会因单点 LLM 故障就罢工。

---

## 4. 真实组件映射表（五阶段认知）

外部论述常把一堆产品名塞进"感知-理解-规划-控制-反馈"五阶段，造成虚假完整性。下表是**经代码核实的真实映射**：

| 认知阶段 | AOS 真实落点 | 状态 | 代码证据 |
|---|---|---|---|
| **感知** | faster-whisper（语音 ASR） | ✅ 真实 | MEMORY 已核实，ASR 管线 |
|  | browser-use（网页） | ✅ 真实 | `src/core/fabric/adapters/aci_browser_adapter.py` |
|  | UITARS（屏幕视觉） | ✅ 真实 | `src/subagents/uitars_agent.py` + `src/skills/uitars.py` |
|  | web.search（数据采集） | ✅ 真实 | 六级检索兜底（AnySearch→百度/Bing→DDG→Jina→智谱GLM） |
| **理解** | inference.llm（语义推理） | ✅ 真实 | deepseek/scnet/siliconflow/zhipu（15/16 provider 可用） |
|  | 因果反思（决策论层） | ✅ 自研 | `_compute_causal_hints()` `:234`（非外部"中数睿智因果模型"） |
|  | mem0 记忆召回 | ✅ 真实 | `src/core/memory/mem0_store.py` + chromadb 向量库 |
| **规划** | plan_bridge（heuristic + 并行分组） | ✅ 真实 | `src/kernel/plugins/plan_bridge.py`（`plan_with_parallelism`） |
|  | ag2_adapter（LLM 规划） | ✅ 真实 | `src/core/fabric/adapters/ag2_adapter.py` |
| **控制** | OrchestrationChiplet（逐跳执行） | ✅ 真实 | `src/kernel/plugins/orchestration_chiplet.py` |
|  | OpenClaw（键鼠控制） | ✅ 真实 | `src/core/fabric/adapters/openclaw_adapter.py` |
|  | Desktop-Touch-MCP（Windows UIA） | 🟡 默认关 | `fabric_hub.py:752`，需用户主机装 Node + 授权 |
|  | action.code_exec（代码执行） | ✅ 真实 | 沙箱隔离 + 拒绝危险代码 |
| **反馈** | autopilot 反思闭环 | ✅ 真实 | 本文全文所述 |
|  | Meta-Trace（跨任务记忆） | ✅ 真实 | `_save_lesson:1234` / `_load_lessons:1178`，JSONL 持久化 |
|  | OPC 飞轮回流 | ✅ 真实 | `src/kernel/opc_loop.py`（业务层反馈闭环） |
|  | IMA 知识库（知识沉淀） | ✅ 真实 | 真跑打通，`store_handoff`/`get_handoff` |

---

## 5. 与外部愿景论述的诚实对照

外部论述常列的组件，经 grep 核实大多无代码证据：

| 外部论述组件 | 真实状态 | 说明 |
|---|---|---|
| 商汤 SenseNova-Vision | ❌ 无代码证据 | grep 零命中 |
| SenseVoice | ❌ 无代码证据 | ASR 走 faster-whisper |
| Firecrawl | ❌ 仅注释 | `sandbox.py:7` 注释提及，无真实集成 |
| MediaCrawler | ❌ 无代码证据 | grep 零命中 |
| Kimi K3 | ❌ 无代码证据 | LLM 走 deepseek/scnet/siliconflow/zhipu |
| Grok / AgentLoop(Grok Build) | ❌ 无代码证据 | grep 零命中 |
| AgentScope / AgentTeams | ❌ 无代码证据 | grep 零命中 |
| Hermes Studio | ❌ 无代码证据 | grep 零命中 |
| TRAE IDE Goal模式 | ❌ 无代码证据 | grep 零命中 |
| 阿里云 Agentic Computer | ❌ 无代码证据 | grep 零命中 |
| 中数睿智因果模型 | 🔶 自研替代 | AOS 自研 `_compute_causal_hints`，非接外部模型 |

**纪律**：禁止为外部愿景凭空造组件（AGENTS.md §1 第4条"万物为我所用"+ 第5条"能力即路由"）。
凡引入外部依赖，先全网搜索核实真实性、当前状态、许可证、可替代项（用户铁律）。

---

## 6. 结论

AOS 的认知闭环**不是理论模型，是真实运行的主循环**。本文档的每个节点都带代码行号，每个"已落地"断言都可复核。

**与普通 RPA/自动化的本质区别**：别人只执行不反思，AOS 执行完会质疑自己——硬闸门拦假成功，反思四块诊断根因，重设计全新计划，Meta-Trace 跨任务沉淀教训。这正是"智能体操作系统"区别于普通工具的核心。

**与外部愿景论述的区别**：本文档不含任何未经验证的组件映射。真实能力映射见第 4 节，愿景组件诚实标注见第 5 节。
