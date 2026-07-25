---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'a58cdff1-ac33-4b62-afa4-8dcf27bcd48e'
  PropagateID: 'a58cdff1-ac33-4b62-afa4-8dcf27bcd48e'
  ReservedCode1: 'e4a64989-c774-4aa5-aedb-8d6cf5194cef'
  ReservedCode2: 'e4a64989-c774-4aa5-aedb-8d6cf5194cef'
---

# AGENTS.md — AOS 宪法（Single Source of Truth）

> 本文件是 AOS 项目对所有 AI 编码工具（Claude Code / Cursor / Codex / Windsurf / Aider / Gemini CLI…）的
> **唯一权威规则源**。格式遵循 [agents.md](https://agents.md) 开放标准（纯 Markdown、无强制 schema，
> 推荐含 Dev tips / Testing / PR 三段；本文件以中文同类项承载）。
> IDE 专用规则（`.cursor/rules/*.mdc`、`.windsurfrules`）与 `CLAUDE.md` 均**引用**本文件，冲突以本文件为准。

## 开源标准依据（逐字对照见 `references/standards/`）

本项目的规则**不是凭空写的**，而是锚定以下三个行业开放标准的**真实完整源文件**
（已于 2026-07-13 从上游克隆，可逐字复核；克隆基准 commit 见 `references/standards/CONTRAST.md`）：

| 标准 | 本地完整源路径 | 上游 | 授权真实状态 |
|------|----------------|------|--------------|
| AGENTS.md 开放标准 | `references/standards/agents-md/` | github.com/agentsmd/agents.md | ✅ MIT（含 LICENSE 文件） |
| Qoder-Rules 规范库 | `references/standards/qoder-rules/` | github.com/lvzhaobo/qoder-rules | ⚠️ 仓库未随附 LICENSE 文件 |
| Karpathy 四原则 | `references/standards/andrej-karpathy-skills/` | github.com/multica-ai/andrej-karpathy-skills | ⚠️ SKILL.md 声明 MIT，仓库根无 LICENSE 文件 |

逐条映射见 **`references/standards/CONTRAST.md`**。本目录的开放标准原文是"对照基准"，本 AGENTS.md 是
"本项目唯一执行规则源"；运行时代码事实 > 本文件 > 开源原文。

---

## 0. 一句话定位

**AOS = 一个「单内核 + 多芯粒」的 agent 运行时。**
不是"更聪明的模型"，而是把 模型 + 工具 包成**可隔离、可编排、不绑定厂商**的流水线基础设施。
它的价值不在模型多聪明，而在：**自主闭环 + 失败学习 + 故障隔离 + 统一路由 + 人机协作**。

---

<!-- BASELINE_START -->
## 0.5 基线快照（2026-07-25 06:10 UTC，手动生成(轻量)）

> 任何 AI / 用户进场第一秒应读到"现在到底行不行"，而非手写叙事。
> 本表由 `tools/baseline_snapshot.py` 真实测算后写入；轻量模式测适配器/测试数，
> `AOS_BASELINE_HEAVY=1` 额外测 live/dead 与覆盖率。

| 项 | 数值 | 备注 |
|----|------|------|
| 适配器总数 | 27 | kernel FabricHub `_ADAPTERS`(26) + orchestrator(自动注册) |
| live | ? | 重跑需 `AOS_BASELINE_HEAVY=1` |
| dead | ? | 典型无 key 环境见 §7（openclaw/ag2/litellm/mem0/lfm2） |
| 测试 | 1139 collected | `pytest --co -q` |
| 覆盖率 | ?% | 轻量模式未测；HEAVY 模式实测见 §5 质量门下限 |
| brain.fabric | 优雅降级 None | `core/brain.py:_init_fabric`(875) import 失败即 `fabric=None`，双轨未合 |
| 生成时间 | 2026-07-25 06:10 UTC | `python tools/baseline_snapshot.py` |
<!-- BASELINE_END -->

### 0.6 双轨融合进度（2026-07-20 更新）

> 方向：FabricHub（新栈）收口 legacy（brain.py/deerflow/swarm/lemon）。不是替代，是桥接——让所有组件经统一路由调度。

| 桥接 | 状态 | 说明 |
|------|------|------|
| FabricHub.chat() | ✅ 已通 | 复用 inference.llm 芯粒做 LLM 对话，`AOS_FABRIC_CHAT=1` 启用 |
| /api/chat → FabricHub | ✅ 可切 | `AOS_FABRIC_CHAT=1` 时优先走 FabricHub，失败回退 kernel/brain |
| Hermes LLM → FabricHub | ✅ 可切 | `AOS_FABRIC_LLM=1` 时 brain.py LLM 对话走 FabricHub 统一路由 |
| 搜索 → FabricHub | ✅ 已统一 | DuckDuckGoSearchSkill → FabricHub SearchAdapter（多源 fallback） |
| Skill 生态 → FabricHub | ✅ 已接 | `skills/manifest.json` + `skill_registry` + `skill_discover()` |
| 白盒进化闭环 | ✅ 已闭环 | trace 生产者 → 蒸馏器 → Registry 回读沉底不可靠引擎 |
| Autopilot → FabricHub | ✅ 已统一 | 默认路由经 FabricHub（`AOS_AUTOPILOT_USE_FABRICHUB=1`），含方向验证/出门检/假反思拦截/成本硬停 |
| run_task(reflect=True) | ✅ 已通 | 统一入口委托 autopilot 完整反思闭环（规划→执行→反思→重设计） |
| 记忆 → FabricHub | ❌ 未桥接 | brain.py 仍直连 `memory/memory.py`，FabricHub 有独立的 `memory_recall/store` |
| DeerFlow → FabricHub | ❌ 未桥接 | DeerFlow 仍独立运行，与 FabricHub run_task 互不感知 |
| 双轨全收口 | ❌ 6月工程 | brain.py 含 30+ 组件，FabricHub 缺意图分类/技能/合规等 20+ 能力 |

## 0.7 产品定位（2026-07-23 战略升级，用户明示）

> AOS 不止是自用 agent 运行时，已升级为 **单创OS**：一套代码、双模式（自用创业执行 + 多租户商用 SaaS）。
> 完整产品定义、融合架构、盈利模式、分阶段落地路线见 **`docs/SHANCHUANG_OS_PRODUCT_VISION.md`**（product source of truth）。

- **OPC 数字组织内核**（5 岗位智能体：产品研发/市场调研/内容营销/客户服务/财务核算）提供「组织能力」；
- **创业目标调度引擎**（autopilot + opc_loop）提供「执行能力」；
- 二者融合成可售卖、可复制的标准化产品。四层架构：多租户隔离底座 / OPC 5 岗位内核 / 调度引擎 / 双模式前端。
- 代码内部仍称 AOS，对外品牌「单创OS」。
- ⚠️ **模型依赖冲突（待用户决策）**：方案目标"底层只用开源 Qwen/DeepSeek、无第三方 API 分成"，
  但项目实际运行依赖 **智谱 ZHIPU_API_KEY（闭源付费 API）**（见 §7）。兑现"无 API 分成"需支持开源默认路径。
- 多租户隔离 / 计费 / 支付 / 商户后台为**新建层**（现状 ZERO），详见该文档 §七差距地图。

### 0.7.1 诚实可验证宪法承诺（邓煜三问对齐，2026-07-24）

> 数学家的三问（涌现算力阈值 / 智能内在机制 / 严谨风控框架）直击 AI"工程狂飙、理论真空"。
> 完整对齐分析见 `docs/research/dengyu_ai_theory_alignment.md`。AOS 在此立下**对外诚实底线**：

- **不宣称解决理论真空**：单创OS 绝不对外吹嘘"破解了 AI 数学根基 / 解决了幻觉与失控"。
  我们对黑箱模型的能力边界保持清醒——§0.7 自曝的"智谱闭源依赖"正是这种诚实的具象。
- **用工程层逼近严谨性**：邓煜呼唤的"可验证"，由九大理念「白盒才可进化 / 可验证即真理 / 失败即训练 / 能力即路由」
  在**系统编排层**落地，而非押注单一模型的闭式公理。具体机制：
  1. **可验证闭环**：autopilot / opc 每步带"成没成"硬判定（真实 stdout / 非空落盘 / 非拒答），不谎报成功；
  2. **芯粒隔离 = 物理熔断**：agnes/ag2 子进程 crash boundary 把不可解释模型包进可解释编排，失控不蔓延；
  3. **失败即训练**：真实错误驱动反思重设计，而非统计模仿生成的假象；
  4. **三级动态路由**：按任务选对的中小模型 + 工具调用，规避"堆算力等涌现"的浪费与焦虑。
- **接受不完备性**：认同"数学约束 + 统计边界 + 物理熔断"三体平衡，不追求纯公理完美闭环。
  任何对外材料（白皮书 / 文档 / 演示）不得出现"根治幻觉""绝对安全""已解决 AI 理论难题"等夸大表述。

## 1. 九大核心理念（AOS 宪法序言）

以下九条是 AOS 存在的理由。任何改动若违背，无论技术多漂亮，都是错的。

### 1. 不手配，自闭环

AOS 不是需要人工填充配置的系统。输入自然语言目标，系统自动完成检索、依赖判断、
环境部署并返回完整结果——不做配置保姆，只造自主执行的机器人。

> 冷启动不依赖历史记忆，记忆是加速器而非运行前提。空记忆库下，「搜索→判断→执行」
> 核心链路必须端到端跑通。

### 2. 失败即训练数据，记忆有生有灭

执行失败不止抛错误：根因自动分类（缺依赖/权限不足/超时/语法错误…），修复方案持久化，
实现「不重复踩同类坑」的机制化能力。

> 记忆附加时间戳与热度权重，配置 TTL 生命周期。长期未被命中的自动分层降级
> （完整记录 → 精简摘要 → 永久删除），平衡检索速度、知识时效性与磁盘占用。
> 区分**短期故障记忆**（快速淘汰）与**长期环境偏好**（长周期保留），
> 避免误删用户固定环境配置。

### 2.5 目标驱动 · 长程自主 · 反思闭环（运行纪律，用户明示铁律）

> **哲学溯源（ID 经 arXiv 核对，2026-07-16）**：反思闭环的工程实践综合自
> **Reflexion**（Shinn et al., 2023, arXiv:2303.11366）+ **ReAct**（Yao et al., 2022, arXiv:2210.03629）
> 及其后续工作；本仓库 `kernel/autopilot.py` 把"目标驱动 + 长程自主 + 每步硬判定 + 反思重设计"
> 落地为可执行实现。近期浙大"求是引擎"（Qiushi Discovery Engine，杨怡豪团队，2026，arXiv:2604.27092，
> 真实存在、同行评审）在真实光学平台上端到端验证了该范式，并提出了 **Meta-Trace 记忆**机制
> （见本条第 8 点）——本仓库的反思记忆即受此启发。
> 用户原话："以后的 ai 智能体 模型 都很多，我不想它像你一样搞个事情 老是失败 还不知道反思。"

这条是 AOS 自主环（autopilot）的**运行纪律**，不是可选增强。违反即错，无论技术多漂亮：

1. **目标驱动，长程自主**：输入一个目标，系统自主推进到真正达成，不是"跑几步交差"。
   没有"差不多了"——交付物（文件/结果）必须真实落盘且非空才算完成。
2. **每步有"成没成"的硬判定（真实闸门）**：搜索步必须有真实返回条数、代码执行步必须有 stdout
   或真写进非空文件、推理步必须非拒答话术且够长——空转/敷衍一律判失败，**不谎报成功**。
   （实现：`autopilot.py` 的 `_*_real_metrics` + `_verdict`）
3. **质疑/风险检查 agent（反思）**：任一步失败或空转，不得直接结束——必须触发"质疑 agent"
   用 trace 里的**真实错误**诊断根因，产出**修正后的下一步计划**，再执行一轮。
   （实现：`autopilot.py` 的 `_reflect_and_redesign`）
4. **失败即重设计，不原地重试**：反思产出的是"换了做法的新计划"，不是把同一条命令再跑一遍。
5. **绝不伪造发现**：反思/规划/执行全链路只用真实证据；反思解析不出有效计划就**停止**（不再硬凑），
   避免"反思→失败→再反思"的虚假循环。
6. **反思有上限**：单任务最多 `MAX_REFLECT`（=2）轮额外反思（总计 ≤3 次执行），防无限循环。
7. **上下文续接：只重设计"下一步"，不重跑已成功的步**（求是引擎原话"重新设计**下一步**"）。
   反思轮必须把上轮已成功步的**真实产出**作为起点续接（`seed_context`），重设计计划只产出
   "从失败处继续的剩余步骤"，不再重做已成功的步——既省步数、又杜绝"重搜导致结果不同"的回归。
   （实现：`autopilot.py` 的 `_execute` 记录成功产出 → `run()` 跨轮 `prior_success` 续接；
   `OrchestrationChiplet` 的 `seed_context`）
8. **反思记忆（Meta-Trace）：失败教训跨任务沉淀**。
   每轮反思把"失败根因→修正"提炼成教训持久化（有界 JSONL，仅留最近 N 条），后续相似任务的
   质疑 agent 自动注入这些历史教训，避免重复已知失败做法。（求是引擎核心贡献即 Meta-Trace memory；
   Reflexion 实证：显式反思文本比"只重放失败轨迹"多 +8% 成功率。）
   （实现：`autopilot.py` 的 `_load_lessons` / `_save_lesson` → `_REFLECTION_MEMORY_PATH`）

> 自检：`python -m kernel.autopilot "<任务>"` 跑完，打印应出现「反思: ...（共执行 N 轮）」一行，
> 且 `reflection` 字段记录 `attempts` / `exhausted` / `log`。若某步失败却只见「未完成 ❌」直接结束、
> 没有反思记录，即违反本条。反思记忆文件 `_traces/reflection_memory.jsonl` 应随失败任务增长。

### 3. 芯粒隔离 ≠ 多 Agent 分解

ag2 / agnes 等重型引擎以独立子进程运行，目的是**故障熔断隔离**（crash boundary），
不是让它们自治协商。内核 FabricHub 独占全局路由、记忆调度、上下文主权——
隔离为了容错，不为拆分。

### 4. 万物为我所用，不为任何一物所绑定

全链路组件多后端级联故障转移：检索六级源兜底（AnySearch → 百度 → Bing → DDG → Jina → 智谱）；
记忆本地 Chroma / 云端 mem0 自由切换；推理可对接三方大模型或本地 ollama。
**无一付费必选项**，全部组件可开源离线运行。

### 5. 能力即路由，权限即边界

适配器通过 `advertise_capabilities` 声明能力，内核路由层按能力标签调度——
这是不变的。但**能做什么 ≠ 谁都能调**。

> 系统内置轻量化运行时权限边界，无需静态 TOML 配置文件，策略动态生效无需重启内核：
> - **本地进程** — 全量放行
> - **HTTP 远程入口** — 强制 Token 身份校验
> - **沙箱命令执行** — 操作白名单 + 资源限额（CPU / 内存 / 超时）
>
> 不是推翻极简设计，是在"能力路由"上补一层"入口鉴权"的安全底线。

### 6. 诚实比聪明重要，输出自带量化置信

底线：绝不伪造成功——搜索无结果、命令执行失败均如实返回，完整附带原始 stdout /
stderr / exit code。对应 AIDE² 奖励黑客防御：系统不能欺骗评估体系。

> 高阶：输出附带结构化原始指标作为置信参考——检索结果条数、进程退出码、
> 记忆召回相似度、组件健康状态——以量化数据替代二元成败判断，让上层决策有据可依。
>
> | 置信级别 | 判定标准 | 示例 |
> |---------|---------|------|
> | 🔴 低置信 | 0 条搜索结果 / exit_code ≠ 0 | 搜索无结果、命令报错 |
> | 🟡 中置信 | 1-4 条结果 / 部分依赖缺失 | 搜到了但不够多、工具缺了但能装 |
> | 🟢 高置信 | ≥5 条结果 / 全链路成功 | 全链跑通，输出可信 |

### 7. 千人千面

AOS 不是通用标准化智能，而是贴合使用者本地环境的专属智能。持续学习个人失败案例、
系统环境偏好（Windows / cmd / winget / bash / choco…），长期使用后适配专属工作流。

### 8. 黑盒不可训，白盒才可进化

全链路执行 Trace 以结构化 JSON 默认落盘（限最大存储条数防磁盘打满），
单条 Trace 最低包含：

```json
{
  "task_id": "uuid",
  "input": {"task": "...", "plan": "..."},
  "steps": [{"capability": "web.search", "engine": "anysearch", "ok": true, "output": "..."}],
  "memory_recall": {"query": "...", "similarity": 0.85},
  "output": {"final": "...", "ok_steps": 3, "failed_steps": 0},
  "metrics": {"latency_ms": 1200, "exit_code": 0}
}
```

> 记忆系统从标准化 Trace 中自动提炼经验——Trace 是记忆库的原始数据源，
> 自主学习无需人肉复盘。可观测性不是锦上添花，是「失败即训练数据」（第 2 条）
> 能够成立的基础设施。

### 9. 可验证即真理

所有声明必须可被复核——不是"我觉得"，是"这是证据"。

> - 引擎状态：`health()` 返回 `True` 必须基于真实连通性探测，不能硬编码
> - 搜索结果：必须附带来源 URL，条数可计数
> - 命令执行：必须附带原始 stdout / stderr / exit code
> - 记忆召回：必须附带相似度分数
> - 拒绝模糊描述（"大概"、"可能"、"应该是"）——没有证据就不下结论
>
> 对应 §4 诚实纪律：真跑、贴可复核原始证据、不罗列结论蒙混。

### 本质一句话

> AOS = 冷启动即可独立运行、自主完成检索部署执行、**目标驱动长程推进、每步有真实闸门、
> 失败必反思重设计直至达成**、失败自动沉淀并按需遗忘、
> 带分层安全边界、全链路可观测、贴合本地环境、组件无绑定、内核统一调度的
> 自主闭环系统。用户仅需提出目标，全流程自动处理，且每一步都真实可复核。

### 理念联动关系

| 理念 A | 理念 B | 关系 |
|--------|--------|------|
| 8 可观测性 | 2 失败训练 | Trace 是记忆训练的原始数据源 |
| 5 权限边界 | 1 自闭环 | 自动化不能以无边界权限为代价 |
| 2 记忆淘汰 | 7 千人千面 | 只保留高价值个性化环境数据 |
| 6 置信量化 | 8 可观测 Trace | 置信指标全部存入执行链路日志 |
| 2.5 反思闭环 | 2 失败训练 | 反思把"单任务失败"转成"重设计后的新计划"，是失败训练在运行期的落地 |
| 2.5 反思闭环 | 6 诚实纪律 | 反思只用真实错误诊断，绝不伪造"已修复"的假象 |
| 4 万物为我所用 | 5 权限边界 | 多源故障转移不能绕过权限——每个备选源都遵守相同 Token 验证 |

> 原五条"命门哲学"（万物为我所用 / 端云合作 / 不绑定零成本可跑 / 极简优先…）已吸收
> 为上述九条的子句或扩展到更高层次，不再独立存在。冲突以本九条为准。

### 1.10 原因与影响驱动（Why + What-Changes-After）—— 系统本能

任何产出（代码 / 文档 / 决策 / 架构）都必须回答三层，只答"是什么"算**未完成**：

1. **为什么（Why）**：它解决什么真实问题？不解决的代价是什么？为什么是这个方法而非别的？
2. **改变之后会怎样（What-changes-after）**：改动落地后系统 / 用户 / 风险会怎样变化？成功路径
   是什么、失败路径是什么、能否回退、副作用能否追责？
3. **证据在哪（Evidence）**：结论是否可复核（呼应理念 9 可验证即真理）。

> 这是"诚实可验证"在**思考层面**的延伸：不只是输出要带证据，连**思考过程**都要显式给出
> Why 与 What-changes-after，否则只是"描述现象"而非"理解系统"。它是 AOS 的**本能**——
> 写到代码里、写进文档里、落到每次决策里，不靠临时提醒。

#### 交付前五缺陷自检清单（强制，落实 Why / What-changes-after）

每次交付前，逐项对着五个高频缺陷自检；任意一项答不出"为什么 / 改变之后会怎样"就退回补：

| # | 缺陷 | 自检问题 |
|---|------|----------|
| 1 | **只验表面、不验真实影响**（如：复验只看版本号，不问漏洞是否真修好） | 我的验证真的测到了"改变"吗？还是只测了"看起来变了"？ |
| 2 | **无副作用审计 / 不可回退**（如：自动改环境却不留痕） | 改动万一出错，能不能追责、能不能撤销？留痕了吗？ |
| 3 | **红线只在一点检查，调用时不复核**（如：注册时校验、invoke 时不校验） | 攻击面会不会绕过点检查？每次边界决策都在入口复检吗？ |
| 4 | **把观测相关当因果、无置信区间**（如：路由成败直接当干预效应） | 我报的是"观测相关"还是"已证因果"？带置信区间了吗？样本够吗？ |
| 5 | **只比单一指标、缺决策论层**（如：只比成功率不比成本/时延） | 在约束下（钱/时延/层级），真的最优吗？有没有更值但次优指标的选项？ |

> 这五条是"Why + What-changes-after"落地的具体抓手；与 §10 极简阶梯、§4 诚实纪律互补：
> 阶梯管"写不写 / 写多简"，本条规定"写之前必须想清为什么与改变之后会怎样"。

---

## 2. 真架构（当前唯一运行时，勿再按 legacy 理解）

- **FabricHub 是唯一内核**，统一持有并调度：**路由 / 记忆 / 上下文主权**。谁都别自己乱管。
  - 代码：`src/kernel/plugins/fabric_hub.py`
  - ⚠️ 当前 `UnifiedBrain()` 的 fabric 组件 init 失败（`'NoneType' object has no attribute '__name__'`）——
    kernel 层 FabricHub 干净，但 brain 层 fabric 链路断。双轨未合，方向是统一到 FabricHub。
- **Chiplet（芯粒）= 被调度的隔离计算单元**。重型/多模态引擎（agnes/ag2）默认跑在**独立子进程**，
  崩溃不传染宿主，可热备切换。这是"故障隔离（crash boundary）"，**不是**自治多 Agent 分解。
- **按能力（Capability）发现引擎，不按名字**。换任何引擎都不碰核心逻辑。
  - 代码：`src/core/fabric/capability.py`、`src/core/fabric/registry.py`
- **引擎无关契约**：所有适配器实现 `BaseAgentAdapter`（`src/core/fabric/adapter.py`）。
- **新增适配器/引擎/芯粒前必须先跑 §10 Ponytail 七级阶梯**，把每级答案贴在 PR 描述中。
- **对外出口 = 标准 MCP server**（`src/aos_mcp/protocol.py`）：`aos_list_engines / aos_route / aos_invoke_engine`。
- **编排器**：`OrchestrationChiplet`（`src/kernel/plugins/orchestration_chiplet.py`）真流水线执行器，
  `steps[]` 逐跳经 hub 路由，上一步输出喂下一步；支持 `parallel_groups` 组内并发。
- **think→do 闭环已收口**：`run_task(planner='ag2')` — ag2 规划文本 → 解析成带 `[AOS能力]` 标签的 steps → 逐跳执行。

**实际注册引擎名（**38 个**，2026-07-25 真机 health_report() 数据：基础 27 + 动态 11）**：

基础 `_ADAPTERS`(26) + orchestrator(自动) = **27 个**：
openclaw / ag2 / litellm / mem0 / browser-use / langfuse / web-search / web-fetch /
web-crawl (crawl4ai) / agnes / vlm / code-exec / file-io / threejs / stt / tts / lnn /
lfm2 / scripts / mediakit / img2threejs / media-gen / miniCPM-o / video-maker /
remotion / security-audit / orchestrator。

动态注册（11 个，env / register_* 触发）：
codebase-memory-mcp / desktop-touch / omni-video / video-use / weknora / ida-pro /
code-team / comfyui / content-director / content-marketer / cast / echo / refine
（与 orchestrator 重合一处，**总计 38 个**）。

> 注：早期文档写"20 / 29" 均为基线未扩 + 未跑 health_report 时的快照；以 2026-07-25 实测
> baseline_snapshot.py + `hub.health_report()` 为唯一真相源。CodeWhale / IMA / mistralrs /
> Page-Agent 是外部愿景，非当前注册名，不要在代码里当真实引擎引用。

---

## 3. 反模式（血训，见到就改，别再犯）

以下每条❌附修复证据（file:line），保证读 AGENTS.md 的 AI 可 grep 验证：

- ❌ **路由只取 `providers[0]` 就停** — 必须遍历所有 live 供给方做故障转移。
  - 修复：`fabric_hub.py:306-368` `route()` 遍历 `providers_for()` 结果 + 单芯粒异常隔离(`continue`) + 合并 `attempts`
- ❌ **把能力焊死在付费远程 key 上** — 见理念第 4 条。mem0 默认 `AOS_MEM0_LOCAL=1` 走本地。
- ❌ **虚报能力** — 适配器 `advertise_capabilities()` 只声明它**真能干**的（如 openclaw 只 `CHANNEL_ACCESS`）。
- ❌ **喂 legacy 双轨** — brain.py / deerflow / swarm_flow / hermes / lemon_orchestrator 是待退役老栈，
  与 FabricHub 互不打通。**新功能一律进 FabricHub**，不要往 legacy 加料。
  当前 `brain.fabric`（`core/brain.py:_init_fabric`，line 875）为**优雅降级**：import 失败即 `self.fabric=None`、
  不抛异常、不影响其余组件——即双轨未合的证据（kernel 层 FabricHub 26 适配器是干净单一运行时）。
- ❌ **故障转移丢上游 data** — 全部失败时返回最后一个供给方的真实结果（保留 trace/ok_steps），不能合成 `data=None`。
  - 修复：`fabric_hub.py:350-356` `last_res is not None` 时保留 `data=last_res.data`；
    全 raise（`last_res is None`）分支 `357-367` 也已返回诊断字典 `{"capability","attempts","engine_errors"}` 而非 `None`。
- ❌ **async handler 内调同步阻塞代码** — 违反「禁止 async 里阻塞」（§5）。历史 5 处（`main.py:722-744` 等）
  已在先前重构中**全部用 `asyncio.to_thread(...)` 包裹移出事件循环**（如 `list_knowledge` 的 SQLite 查询
  line 760-765 整体包进线程池）；当前 `main.py` 同步调用均在线程池内执行。新增 async 路由须延续此模式，
  不得再在 `async def` 顶层直接做 I/O / DB / 子进程调用。
- ❌ **反思 / 记忆 IO 无超时** — 自主环里调任何外部引擎（ag2 / ollama / mem0）都必须带超时守护：
  外部引擎挂死**不会抛异常，只阻塞**，裸 `try/except` 拦不住，整条 `run()` 会被拖死、降级链永远触发不了。
  - 修复：`autopilot.py:74` `_call_with_timeout()`（守护线程 + `join(timeout)`，超时作废粘死实例并降级）。
    反思三后端 `ag2 → ollama → heuristic`（`_reflect_and_redesign`）与规划路径（`_plan`）均已套此守卫。
- ❌ **共享记忆文件读写无锁** — `_traces/semantic_memory.jsonl` 被 autopilot（写侧）与
  fabric_hub（读 / 回退写侧）**并发**访问，必须共用同一把 `kernel.semantic_state.SEMANTIC_LOCK`，
  否则写侧读-改-写-追加中途被另一写打断会写坏 JSONL，读侧可能读到半行致 `json.loads` 失败漏条。
  - 修复：锁统一在 `kernel/semantic_state.py`；写侧 `autopilot.py:973`、读侧 `fabric_hub.py:965`、
    回退写侧 `fabric_hub.py:1045`，三处指向**同一把锁对象**。

---

## 4. 诚实纪律（不可协商，用户会亲自复核）

1. **不弄虚作假**。真跑、贴可复核的原始证据（真实 stdout / 测试耗时 / git hash），不罗列结论蒙混。
   > 对照：Karpathy 原则4 Goal-Driven Execution（用可验证结果说话，而非描述意图）
2. **提交必当场核验**：`git commit` 后立刻 `git log -1 --format="%H %s"` 确认 hash 真进 git，再向用户报告。
   （曾虚报未落地的 hash，血训。）
   > 对照：Karpathy 原则4「定义成功标准，循环直到验证通过」
3. **回应"虚"质疑铁律**：绝不辩解，直接真跑贴原始证据。常见误判根因＝**用户主机代码未同步**，须点出并给主机复现命令。
4. **先思考再编码**（Karpathy 原则1 Think Before Coding）：先说假设、亮取舍、给最简方案，再动手。
   思考必须显式覆盖"为什么"与"改变之后会怎样"（见 §1.10 原因与影响驱动本能）。
   > 原文见 `references/standards/andrej-karpathy-skills/CLAUDE.md` §1 / `SKILL.md` §1
5. **改动最小化（Surgical）**：只碰该改的，不顺手"美化"无关代码，不重构没坏的东西。每一行 diff 都能追溯到需求。
   > 对照：Karpathy 原则3 Surgical Changes + Qoder 规则5「仅修改请求的内容」
   > （`references/standards/andrej-karpathy-skills/CLAUDE.md` §3；
   > `references/standards/qoder-rules/core/requirements-spec.zh-CN.md` 规则5）
6. **全盘思维优先**：修 bug 前先推完整链路（输入→每一步→传递→输出）。不逐行盲调，不盯着一个函数改而忽略上下游断裂。理解根因再动手，不是看到报错就补。
   > `references/standards/qoder-rules/core/requirements-spec.zh-CN.md` 规则5）

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
- 禁止：`exec/eval` 用户输入、硬编码密钥、async 里阻塞（已知违规 5 处，见 §3 反模式）、`print` 当日志、可变默认参数、`__init__.py` 里 import src。

**质量门（提交前自检）：**
- `ruff check src/ tests/` → 0 error
- `mypy src/ --ignore-missing-imports` → 0 error
- 相关子集 `pytest tests/<相关文件>` 全绿；不确定回归时跑更大范围。
  > 对照：Qoder testing 规则1「测试完整性」、规则3「测试分层」
  > （`references/standards/qoder-rules/quality/testing-spec.zh-CN.md` 规则1 / 3）
  > 覆盖率基线不倒退：`kernel/` ≥ 80%，`core/fabric/` ≥ 60%，总覆盖率 ≥ 50%（当前 ~41%，差 9pp）。
  > ↔ Qoder testing 规则2「覆盖率目标」
- 真实可跑不弄虚 ↔ Qoder 规则10「确保代码成功编译」、规则6「验证 API 存在」、规则13「只用真实库」
  （`references/standards/qoder-rules/core/requirements-spec.zh-CN.md` 规则10 / 6 / 13）
- 已知 legacy 债勿误修：`test_database::test_persistence_bridge_on_unified_db`、`test_memory`
  （no such table）——不 import fabric_hub，与新栈无关。

### 5.1 借鉴 moai-adk：SPEC-First 与 TRUST 5 质量门（2026-07-24 引入）

> 来源：`modu-ai/moai-adk`（Go / Apache-2.0，真实仓库已核实）。**只借鉴方法论，不引入 Go 代码/依赖**。
> 外部项目处置铁律与全文见 `docs/research/open_source_tools_2026.md`。

- **SPEC-First（编码前先定义完成标准）**：任何非 trivial 改动，先写清「验收标准 + 证据形式」再动手——
  与 §4 诚实纪律「提交必当场核验 hash」、§6「可验证目标」一脉相承。复杂任务先用 1-2 句 SPEC 说清
  「改完后怎么算成功、拿什么证据」，再进入实现，避免「跑几步交差」。
- **TRUST 5 质量维度（每个 PR 自检）**：
  - **T**ested：有真实复现测试，不靠手测；覆盖率基线（见上）不倒退。
  - **R**eadable：命名清晰、ruff 0 error、注释说「为什么」而非「是什么」。
  - **U**nified：格式 / import 顺序 / 目录结构一致，不顺手"美化"无关代码（§4.5 改动最小化）。
  - **S**ecured：无硬编码密钥、输入校验、OWASP 常识过关（呼应 §0.7.1 诚实可验证）。
  - **T**rackable：约定式提交、关联需求、结构化日志；每行 diff 能追溯到需求。
- **TDD/DDD 选择**：新模块或覆盖率 ≥10% 走 RED→GREEN→REFACTOR；存量低覆盖代码走 ANALYZE→PRESERVE→IMPROVE，
  不盲目重写（呼应 §4.6 全盘思维、先理解根因）。
- **规划与审计分离**：重大重构先独立审视方案再执行，不自审（参考 moai-adk 的 plan-auditor 思路）。

### 5.2 借鉴 OpenWorker：本地优先 / BYOK / 审批门控 / 连接器 / 统一层（2026-07-24 引入）

> 来源：`andrewyng/openworker`（MIT，桌面 AI 同事，本地已下载 `D:\OpenWorker1\openworker-main`，
> README 核实）。**技术栈（Rust Tauri 桌面壳 + Python + React）与 AOS 不兼容，只借鉴范式，不引代码**。
> 全文与逐条映射见 `docs/research/openworker_borrowing.md`。处置定级：MEMORY § XII「能商用但技术栈不兼容 → 借鉴优化」。

OpenWorker 是"消费级桌面 agent 应用"，AOS 是"agent OS 后端内核"——层级不同，但它**验证了 AOS 架构选择的正确性**：
本地优先 / BYOK / 审批门控 / MCP 连接器 / 统一模型层，AOS 均已具备且多租户 BYOK、capability 级路由更统一。可借 3 个缺口补齐：

- **[A] 无人值守 → park 到审核收件箱**：自主环（autopilot/opc_loop）遇"有后果动作 + 当前无人审核"时，
  持久化待审项到审核收件箱，等人在环再决策；绝不"假装执行"或"静默跳过"（补 §0.7 诚实纪律边界）。
- **[B] 岗位级定时任务原语**：在 OPC 飞轮上补"按 cron 调度某岗位做周期产出并留痕"（复用 opc_loop + TaskTraceStore），
  对应 OpenWorker 的 automations / standing watch。
- **[C] aisuite 作 inference.llm 网关对照项**：OpenWorker 用 aisuite 统一 chat-completions + agents(tools/MCP)；
  AOS 用 LiteLLM 网关已够用，aisuite（MIT）列为可选统一层评估项，**不紧急、不锁死**。

### 5.3 借鉴 waoowaoo：分阶段可干预管线 / 一致性锚点 / 短剧子能力 opt-in（2026-07-25 引入）

> 来源：`saturndec/waoowaoo`（约 11K–13K Star，AI 短剧/漫剧一站式生成平台，2026-07-25 WebFetch 核实）。
> **许可证 = CC BY-NC-SA 4.0**（raw LICENSE 确认，原文 "not a software license... protect the commercial rights"），
> 明确禁商用，与单创OS 商业 SaaS 冲突；技术栈 Next.js15+React19+MySQL/Prisma+Redis/BullMQ+MinIO 亦不兼容、非 CLI 形态。
> 全文与逐条映射见 `docs/research/waoowaoo_borrowing.md`。处置定级：MEMORY § XII「不能商用 → 只借鉴，不引代码/不 subprocess 接入/不 vendored」。

waoowaoo 是"消费级 AI 短剧生产"产品，与 AOS 不在同一层，但它**验证了 AOS 内容营销岗「编排+审核」路线的正确方向**，可借 4 点与 OpenWorker 形成互补：

- **[A] 分阶段可干预管线**：把内容营销岗工作流从单步 `promote` 扩为「选题 → 素材 → 分镜 → 配音 → 成片 → 分发」多阶段，每阶段过 §0.7 白盒审核闸门（补缺口：当前 AOS 内容生产是单步黑箱，无人工干预点）。
- **[B] 角色/场景一致性锚点**：`media.image` / `media.video` 加 `identity_anchors` 一等约束（角色脸/场景色板一旦锁定，后续镜头强制对齐），补 AOS 跨镜头一致缺口（OpenWorker/img2threejs 均未覆盖此点）。
- **[C] 短剧/漫剧子能力 opt-in**：内容营销岗加 `short_drama` 标签，只做编排+审核、底层走已接入商用引擎（Mediakit/Remotion 等）不自建——与 Mediakit 借鉴（视频后期）、img2threejs（3D）形成内容生产三件套。
- **[D] 数据自控 + 分阶段审核哲学**：waoowaoo 的"每环节可人工干预、数据本地可控"强化单创OS 差异化卖点（呼应 OpenWorker 审批门控缺口 + §0.7.1 诚实纪律），属叙事级借鉴，不改架构。

---

## 6. 工作法（Agentic Engineering，Karpathy「后 Vibe Coding」范式）

开发者是**编排者 + 审核者**，AI 代理负责具体实现。每个任务走四步协作闭环：

```
架构设计 → 任务拆解 → 代理执行 → 人工审查
   ↑                                      │
   └──────────── 不通过则回炉 ────────────┘
```

- **先思考再编码**（Karpathy 原则1）：动手前先扒真实代码确认现状，别凭记忆写（记忆会骗人）；
  且思考必须显式给出"为什么"与"改变之后会怎样"（§1.10 系统本能，交付前五缺陷自检必过）。
- **追求简单**（Karpathy 原则2 Simplicity First）：能 50 行别写 200 行；不做没要求的抽象/配置/防御。
- **可验证目标**（Karpathy 原则4）：把"修 bug"翻译成"先写复现测试→让它过"；强成功标准才能独立循环。
- **中文直白沟通**：给具体文件路径、可执行命令、真机验证结果，别堆术语长文档；能自己合理决定的先做。

> 四原则完整原文见 `references/standards/andrej-karpathy-skills/CLAUDE.md` 与 `SKILL.md`，
> 本节的精炼版逐条对应其 §1–§4。

---

## 7. 环境两座山（本地零成本启用，全免费）

- **记忆**：`ollama serve` + `ollama pull qwen2.5:7b nomic-embed-text`（或 `AOS_MEM0_EMBEDDER=huggingface` 走已装的
  sentence-transformers）。本机 sentence_transformers / ollama / chromadb 已装齐。
- **推理本地**：mistralrs / ollama 已在 wiring 设计好，启用即用。
- **绘图**：openclaw 是**本地自托管网关**（127.0.0.1:18789，MIT 免费）。`openclaw gateway run` 或 adapter 的
  `ensure_gateway()` 自起。当前 dead 引擎 **7 个**（2026-07-25 probe_dead.py 真跑 8s 探活）：
  - **openclaw** — port_down 127.0.0.1:18789（网关没跑）
  - **stt** — health() 8s TIMEOUT（whisper.cpp 二进制/模型未装）
  - **lfm2** — health() 8s TIMEOUT（HF 权重探测慢，`AOS_LFM_ASSUME_READY=1` 可绕）
  - **minicpm_o** — health() 8s TIMEOUT（本地 omni 服务 10 次重试都连不上）
  - **vlm** — health()=False（无 tier resolve，需配 ZHIPU_API_KEY 或本地推理后端）
  - **mediakit** — health()=False（`AOS_MEDIAKIT_ENABLED=1` 未开，opt-in 关闭）
  - **comfyui** — health()=False（`http://127.0.0.1:8188/system_info` 探活失败，本地 ComfyUI 未起）

  > 注：早期文档说"5 大 dead 引擎"漏算了 stt / vlm（已修）。ag2 / litellm / mem0 实际
  > probe 时**已 live**（依赖 autogen / litellm / mem0 已安装，且 health() 不再卡死），
  > 不再列入 dead 表。
- **搜索**：AnySearch（免 key）+ 百度/Bing HTML（国内最稳）已多源兜底，不花钱。

## 8. 生态集成（万物为我所用 —— 5 款真实产品经 MCP 接入）

AOS 不重造轮子：任何支持 **MCP** 的真实产品都能经**通用 MCP 客户端芯粒**
（`src/core/fabric/adapters/mcp_client_adapter.py`）成为 AOS 供给方，其 tools 经
`capability_map` 映射成 AOS 能力，由 registry 统一路由与故障转移。已核实真实存在、
均支持 MCP 的 5 款产品接入方案见 **`references/ecosystem/INTEGRATIONS.md`**（含真实仓库
路径、LICENSE 核验状态、env 一键接入清单）。要点：

- **AnySearch**（搜索层）：✅ 已真接（SearchAdapter 第 0 源 + 可经 MCP 注册）。
- **ExploreYC**（数据层，MIT）：📚 完整源码已入仓 `references/ecosystem/exploreyc/`；
  AOS 已加 `DATA_QUERY` 能力，经其 API/导出数据接成 `data.query` 芯粒。
- **Sim**（构建层，Apache-2.0）：📚 源码已入仓；其可视化 DAG 与 AOS `OrchestrationChiplet.steps[]`
  同构，可作 AOS 流水线的可视化构建/审查工作台。
- **Auriko**（成本层）：⚠️ SDK 开源（Apache-2.0，PyPI `auriko`）但套利网关算法未公开——
  **其策略内核已原生借进 AOS**（registry `ROUTE_STRATEGY=cost|latency|quality` + 故障转移），
  不依赖其托管服务，零绑定。
- **Timbal**（生产层，Apache-2.0）：📚 源码已入仓；AOS 原型可经其 Python 框架上线生产，两端 MCP 互通。

> 接入铁律：能用完整开源就用完整的（如 Sim/Timbal/ExploreYC 全量仓库入仓对照）；
> 只开源 SDK 不公开核心的（Auriko），借其*架构*而非*依赖*。全部经 `references/`
> 真实源逐字对照，不凭记忆编述。

## 9. 用 codebase-memory-mcp 审视整个 AOS（代码理解能力）

**目标**：把真实开源工具 codebase-memory-mcp（DeusData，纯 C / 零依赖 / MIT，158 种
语言 tree-sitter）**弄进 AOS 仓库**，让任何人 clone 本项目后都能用它直接审视整个代码库——
这是「万物为我所用 / 把真实开源工具弄进来」的范例。完整 how-to 见
**`third_party/codebase-memory-mcp/README.md`**。

- **能力**：`code.understanding`（`src/core/fabric/capability.py`），由 stdio MCP 客户端
  （`src/core/fabric/adapters/mcp_stdio_adapter.py`）接真实二进制，经
  `src/core/fabric/adapters/codebase_memory_mcp_adapter.py` 把其 8 个真实 MCP 工具统一映射
  （另有 6 个工具仅作 `cli` 子命令提供，不进 MCP server）。
- **即插即用**：`FabricHub` 构建时自动探测并注册（`register_codebase_mcp` +
  `_register_env_codebase_mcp`）——装好二进制（`third_party/codebase-memory-mcp/install.ps1`）
  即通电；二进制缺失时**优雅跳过，绝不谎报 live**。
- **别人怎么审视 AOS**：
  1. `powershell -ExecutionPolicy Bypass -File third_party/codebase-memory-mcp/install.ps1`
     （装二进制到 `bin/`，或改用手动 scoop/winget/npm，`AOS_CODEBASE_MCP_BIN` 指向它）
  2. `powershell -ExecutionPolicy Bypass -File scripts/index_aos_codebase.ps1`
     （索引整个 AOS，产物 `.codebase-memory/graph.db.zst` 可提交、别人 clone 后直接加载）
  3. 直接 CLI 查：`codebase-memory-mcp cli get_architecture '{"project":"AOS"}'`
     或经 AOS 运行时：`hub.route(Capability.CODE_UNDERSTANDING, {"tool":"get_architecture",...})`
- **诚实注记**：AOS 早期有两个**冒用 codebase-memory-mcp 之名**的 legacy skill
  （`src/skills/codebase_memory.py`、`src/skills/codebase_memory_mcp.py`），实为自研正则
  玩具索引器、从未调用真工具。现已将 `codebase_memory_mcp.py` 改为真实后端薄代理（可用走真
  工具、不可用诚实报错，不再造假），`codebase_memory.py` 也已纠正冒充声明。真正的集成在
  本节所述的新栈——以 stdio MCP 接原版二进制。

---

## 10. 极简决策阶梯（Ponytail 范式，全局铁律）

> **溯源（已按铁律搜证核实）**：[Ponytail](https://github.com/DietrichGebert/ponytail) 是真实开源项目
> （MIT，作者 Dietrich Gebert），官方标语 *"Makes your AI agent think like the laziest senior dev in the room.
> The best code is the code you never wrote."* **不是 120 行规则、也不是 8.2 万 Star**（那些是中文博客夸大）；
> 核心是 **7 级决策阶梯**。官方基准（12 个真实任务 / Haiku 4.5 / Claude Code 在 FastAPI+React 真库）：
> 代码量 **-54%**（最高 -94%）、Token **-22%**、成本 **-20%**、速度 **-27%**、安全性 **100%** 保持。
> 本规则**直接采纳其阶梯方法论**，作为 AOS 全局极简纪律，并经 §1 命门哲学第 5 条赋予最高优先级。

### 10.1 七级决策阶梯（写/改任何东西之前先跑，停在第一个成立的台阶）

1. **这东西需要存在吗？** → 不需要就跳过（YAGNI）。
2. **代码库里已经有了？** → 复用，不重写。
3. **标准库能实现？** → 用它（零依赖优先）。
4. **平台原生功能支持？** → 用它（浏览器原生 / 语言内建 / 框架原生）。
5. **已安装的依赖能用？** → 用它，不新装包。
6. **能一行解决？** → 一行搞定。
7. **以上都不行** → 才写**满足需求的最小实现**。

> 阶梯在**理解问题之后**运行，不取代理解：先读要改的代码、追踪真实数据流，再选台阶。
> **懒，但不渎职（Lazy, not negligent）**：信任边界校验、数据丢失处理、安全、可访问性 永远不在砍价之列。

### 10.2 映射全局（不止代码）

这条铁律适用于**所有产出**，不只写代码：

- **架构**：能用单内核+芯粒编排解决的，不另起自治多 Agent 微服务；能按 Capability 发现的，不焊死引擎名字。
- **依赖**：能零成本开源/本地的（ollama / sentence-transformers / chroma / 百度·Bing HTML / AnySearch），不绑付费 key。
- **文档**：能一张表/一段说清的，不写长篇；能引用本 AGENTS.md 的，不重复造规则文件。
- **流程**：能一步验证的，不绕多步；能自测的，不强依赖用户主机复跑。
- **我的推理**：能简单、高效、高质量、安全搞定的方案，绝不为了"显得周全"而搞复杂。

### 10.3 AI 代理（我）也严格遵循

- 每次产出前先在心里跑一遍阶梯；若我本可一行/复用/用标准库却写了重的，用户有权直接打回。
- 不主动"加戏"：未要求的抽象、配置、防御性分支、额外依赖，一律不写。
- 当 10.2 与"看起来更稳妥"冲突时，选更简单但安全达标那侧；确需复杂时，先说清为什么简单方案不行。

> AI生成