# AOS 决策记录 (Decision Log)

> 本文档沉淀 2026-07-09 ~ 07-10 多轮架构评审的结论。
> 性质:**工程判断与取舍记录**,不是需求文档。每条带裁决理由,便于日后复盘。
> 最后更新:2026-07-10。

---

## 0. 一句话现状

> AOS 的**判断力远超当前的工程纪律**。架构理念一流(开放能力总线 + 真实开源薄适配),
> 但系统处于"新旧架构未收敛"的中间态,且**当前环境连基础依赖都缺失、无法验证是否真能跑通**。

---

## 1. 根本诊断:灵魂与肉体不对齐

- **灵魂**(STATUS.md 宣称):开放能力总线,AOS 不重造大脑,只做接线板。
- **肉体**(实际代码):`brain.py` 2301 行 + 7 个大脑子模块 2299 行 ≈ **~4756 行自研编排决策逻辑**(2026-08 实测；07-10 二期核验的 1965/2237 为过期快照),且 fabric 是"嫁接"进 brain 而非取代它,**新旧两套架构并存**。
- **代价**:每加一个功能都要同时喂两套架构;提交历史里大量"死锁/撞包/三重失效"就是两套架构在同一进程里打架的症状(如 commit deb5082 跨-await 持锁死锁)。
- **结论**:收敛只有一条路——砍 brain.py 成纯胶水,让 fabric 当主干。详见 `docs/BRAIN_TRIAGE.md`。

---

## 2. 能不能打?

- **作为想法/技术探索:能打,高分。** fabric 能力总线、42 表五层数据库、统一网关、GB/Z 185 合规——这些选择说明做的人在想问题。
- **作为竞争/交付物:现在不能打。** 不是功能不够,是**自己还没决定好自己是谁**。

---

## 3. 已识别的核心问题(按严重度)

| # | 问题 | 严重度 | 备注 |
|---|---|---|---|
| 1 | 环境跑不起来:Python 3.14 但声明 3.10/3.11;sqlmodel/ag2/mem0 未装;pytest 无法 collect | ✅ 已解 | 2026-08 复核:pytest 正常 collect 并通过;Python 版本已统一为 3.11(pyproject/CI/README/`.python-version` 四方一致) |
| 2 | 新旧架构未收敛(brain.py 自研大脑 vs fabric) | 🔴 P0 | 根因,见 §1 |
| 3 | git 已 40 提交(原 23 为过期快照)、版本保护改善中 | 🔴 P0 | 高危(历史不足,继续补提交) |
| 4 | 硬编码密钥残留(brain.py:91-94 明文 admin/aos123456) | 🟠 P1 | 隐患 |
| 5 | 巨型文件违反自家规范(brain.py 实测 2301 行、src/web/app.py 实测 4769 行,均远超 AGENTS.md max 500 行;web/app.py 真实存在且为 start_all.sh 拉起的 Streamlit 入口) | 🟠 P1 | AGENTS.md 定 max 500 行;拆分 app.py 为持续项 |
| 6 | 重复/死代码:UITARS 注册块复制两遍、日期硬编码、死属性 | 🟡 P2 | 零风险可删 |
| 7 | 自研 OpenClaw 违反铁律(已标 DEPRECATED 但代码仍在) | 🟡 P2 | |
| 8 | fabric 6 adapter 仅 2 个 live(LiteLLM/Mem0/browser-use/Langfuse 均 health()=False) | 🟠 P1 | 不是缺能力,是没通电 |

---

## 4. 已否决/已澄清的外部建议

### 4.1 Raschka《LLMs-from-scratch》— ❌ 不接
- 教学项目,价值在"亲手敲",不是塞进生产系统。
- "自动训练微调"想多了:此库训 GPT-2 124M,不能产出有用模型。
- 真要训练/微调能力:**接 LLaMA-Factory**(YAML 配置式 LoRA,支持 Qwen/GLM/DeepSeek),做成 fabric adapter。符合铁律。

### 4.2 Open Science 科研智能体 — ⏸ 方向对,但排在收敛之后(P2)
- 科研能力是真实缺口,且符合铁律。
- 但现在接 = 给漏水的房子装第三套家具。先让 DeerFlow L6 稳定、先激活现有适配器。
- 接法:写**一个** `OpenScienceAdapter`,不是灌 250 个技能。

### 4.3 MCP Server 矩阵(trends-hub/Tavily/微博/抖音)— ❌ 现在不接
- "免费零配置"陷阱:稳定性/数据质量/反爬升级风险未验。
- 能力重叠:已有 duckduckgo/jina/searxng/cognee 四个搜索技能。
- 纪律:**加一个、删一个**。真要实时搜索,选 Tavily,同时砍掉重复搜索 skill。

---

## 5. 八条深度分析的逐条裁决(第二轮评审)

外部分析(指向 AOS)提出 8 条,裁决如下:

| # | 建议 | 裁决 | 理由 |
|---|---|---|---|
| 1 | 暴露 MCP Server | ✅ **强烈同意,P1** | 最大单点杠杆。但事实修正:你**已有** server 骨架(`mcp/protocol.py:129`),缺的是 transport 层。**别手撸,用官方 mcp/fastmcp SDK** 挂 stdio+SSE。 |
| 2 | A2A 协议 / Agent 发现 | ❌ **违反铁律,不自己写** | 建议自写"发现/协商/状态共享"= 重造 AG2+A2A。正确做法:接真实 A2A SDK 或让 AG2 adapter 暴露 Agent Card。处方比病重。 |
| 3 | Memory 太弱 | 🟡 **其实已做,需激活** | Mem0 已接(`mem0_store.py`),问题是 health()=False 没跑活。"ChromaDB 是 2023 方案"是时髦偏见。评估/遗忘曲线是 P3。 |
| 4 | Agent 评估框架 | ✅✅ **最值钱,P1** | 八条里唯一指向"能不能进化"。当前 STATUS.md 全在讲"接了什么",没有一个地方讲"效果如何、有没有变好"。最小实现:10-20 标准任务 + pass/fail + 耗时成本。 |
| 5 | 实时学习 | 🟡 **对,但依赖第4条** | 用户反馈→调 prompt/权重,必须建立在评估框架上。执行顺序 4→5。 |
| 6 | 流式优先 | ✅ **方向对,P2** | 体验差距,非可用性。地基稳了再做。 |
| 7 | 多模态原生 | ❌ **现在分心** | 文本链路都还在修死锁,谈"看屏幕主动帮忙"是奢侈。记 roadmap 不碰。 |
| 8 | Agent 安全框架 | ✅ **方向极对,且是你的护城河** | 与"合规 GB/Z 185 是唯一差异化"一致。你已有审计,缺"工具调用前授权"+"决策因果链"。能转成企业订单。 |

---

## 6. 统一优先级(P0 → P2)

> 贯穿所有讨论的执行顺序。原则:**先稳地基、再收敛、最后扩展**。

### P0(本周)— 让系统能跑、能验证
1. **环境跑通**:对齐 venv 到 3.10/3.11,装齐 sqlmodel/ag2/mem0 → pytest 能 collect → /health 返回 healthy。
2. **git 版本保护**:核心代码提交入仓(当前仅 23 提交)。
3. **brain.py 零风险清理**(BRAIN_TRIAGE 第1步):删死代码、删重复块、删明文口令兜底。不碰逻辑。

### P1(两周内)— 收敛 + 两个最大杠杆
4. **收敛 brain.py**:按 BRAIN_TRIAGE 逐个把 7 大脑模块迁给真实引擎(agent_card→LiteLLM,fingerprint→Mem0,debate→AG2,swarm/lemon→DeerFlow,classifier→fabric)。
5. **激活 fabric 现有适配器**:让 LiteLLM/Mem0 至少 health()=True,有一条真实 trace。
6. **暴露 MCP Server**(八条之 #1):用官方 SDK 挂 transport,Claude Code/Cursor 可直连。
7. **搭评估框架**(八条之 #4):标准任务集 + 体检表。让 AOS "看见自己"。

### P2(收敛之后)— 扩展
8. 流式优先(#6)、安全授权(#8,护城河)、Mem0 激活(#3)、Open Science 科研能力。
9. 训练/微调能力:接 LLaMA-Factory 成 fabric adapter。

### 别现在做
- 自写 A2A(#2,违规)、多模态(#7,分心)、灌外部 MCP server(§4.3,膨胀)。

---

## 7. 一个贯穿始终的判断

> 外部所有材料(三段营销稿 + 八条分析)的共同病:**平铺罗列、不分优先级,且绝大多数在"加东西"。**
> 但 AOS 此刻最缺的不是"更多能力",而是"**知道自己现在到底行不行**"。
> 评估框架(让系统看见自己)+ 环境跑通(让讨论有绿信号)是两件凌驾于一切之上的事。

---

## 8. "智能接线缺口"自查(2026-07-10 二次校正版)

> ⚠️ **本节为校正版。** 初版(07-10 早些时候)误将 `classify_with_llm` 描述为"内部直接
> return 本地、从不调 LLM",经用户复核 + 代码实测(task_classifier.py:124-139)证伪。
> 初版同时存在过期指标与误报,已在此整体重写。校正动因见 §8.4。

### 8.1 核实结论:缺陷是"接线缺口",不是"函数造假"

经逐行复核 `src/core/task_classifier.py`:

- `classify_with_llm()`(:124-139)**确实调用 LLM**——构建 `TASK_CLASSIFICATION_PROMPT`,
  调 `self.brain._route_l1(prompt)`(→ Hermes),仅在 `brain is None` / `confidence < 0.5` /
  `异常` 三种情况回退到 `_local_classify()`。**它是可用的 LLM 分类器,不是假函数。**
- 真实缺陷是**接线缺口**:路由入口 `classify()`(:103)在 :118 直接调 `_local_classify()`
  (关键字匹配),`classify_with_llm` 写好了但**从未被任何路由路径调用**,是死代码。

**正确的修法**:把已有的 `classify_with_llm` 接进 `classify()` 的主路径(本地规则降级为兜底),
而不是"删掉整个分类器、换外部引擎"。工作量从"重写"降到"接线"。

### 8.2 仍属实的"名实不符"项

| 位置 | 名字宣称 | 实际 | 严重度 |
|---|---|---|---|
| `task_classifier._local_classify` (:141) | 任务分级 | `simple_patterns` 关键字包含匹配 | 🟠 本地兜底,合理但被当主路径 |
| `task_classifier.classify_with_llm` (:124) | —— | **写了 LLM 分类却没接进路由**(死代码) | 🟠 接线缺口,非造假 |
| `meta_debate.run_self_pitch` (:148) | 元辩论 | 注释"使用本地规则避免递归",`_calculate_match_score` 关键字累加 | 🟠 真关键字模拟 |
| `swarm_flow.execute_parallel` (:254) | 并行执行 | `for step_id in group` 串行,无 ThreadPool/asyncio | 🟠 名实不符 |

### 8.3 已澄清的误报(初版制造的不必要恐慌)

- **`exec`/`eval` 执行用户代码:误报。** grep `src/core` 的 `exec(` 命中全部是
  SQLAlchemy `Session.exec()`(engine.py:88 / cold.py:68 / eventstore.py:38,72,97,127),
  无任何执行用户代码的 `exec()`/`eval()`。此担忧在 src/core 范围内可关闭。
- **明文口令 admin/aos123456:已治理。** brain.py:91-92 已改为从 config 读取,
  :86-87 仅存注释说明历史。不再是存活隐患。

### 8.4 初版为何出错(教训)

- 初版对 `classify_with_llm` **只看了方法签名和几行,没读全 :131 的 `brain._route_l1` 调用**,
  就下了"假函数"结论。这与上一轮"看路径就判错靶子"同病:**验证不充分就定性。**
- 已纳入铁律 §4.3,作为反复出现的反面案例。

### 8.5 仍待验证项

- [ ] router/角色匹配(`skill_registry.search`)是否真用 embedding,还是 Jaccard/子串
- [ ] 同步(requests)与异步(FastAPI)混用点全量排查(死锁温床,commit deb5082 已修一处)
- [ ] fabric 各 adapter 实时 health() 复测(OpenClaw 已真实部署 @18789,其余待验)

---

## 9. 关联文档

- `docs/BRAIN_TRIAGE.md` — brain.py 逐方法处置表(行号级)
- `STATUS.md` — 项目自省状态(诚实但需随收敛更新)
- 本文档 — 决策记录与外部建议裁决
