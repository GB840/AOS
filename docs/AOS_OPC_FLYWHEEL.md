# AOS OPC 商业飞轮：一人公司通用价值链常驻环
## AOS OPC Business Flywheel

> 本文档定义 AOS 面向一人公司（OPC, One-Person Company）的产品化落地：把通用价值链
> 编排成常驻自主环，让 AOS 的基建能力（反思/Meta-Trace/并行/可验证）翻译成一人公司
> 真正愿意掏钱的东西——"一个会自己变好的生意"。
> 原型已落地（`src/kernel/opc_loop.py` + `examples/opc_cli.py`，2026-07-20），测试全绿。

---

## 0. 一句话定位

OPC 飞轮不是垂直行业模板，是**所有一人公司的通用价值链**：
**分析 → 宣传 → 获客 → 交付 → 维护/回流**，一个功能服务全部 OPC 类型。
它跑在 AOS autopilot 上，每轮失败教训经 Meta-Trace 自动喂回下轮分析——飞轮自改进。

---

## 1. 商业化判断（诚实）

### 谁会付、谁不会付

| 群体 | 愿意付吗 | 付多少（估） | 为什么 |
|------|---------|-------------|--------|
| 独立开发者 / indie hacker | ✅ 会 | $20–50/月 | 看中自托管、可控、白盒可验证 |
| AI 研究员 / 自动化重度玩家 | ✅ 会 | 一次性或小额 | 认失败学习、因果反思独门能力 |
| 真·一人公司（咨询/自媒体/电商） | ❌ 现在不会 | — | 要"开箱即用员工"，不是"配 FabricHub 路由" |
| 企业小团队 | 🟡 可能 | 按席 | 需权限/合规/托管，产品层还没 |

### 核心矛盾

AOS 的护城河全是**基建层**价值（芯粒隔离/白盒 Trace/因果反思/诚实可验证），OPC 用户**感知不到也验证不了**。
成功的 OPC AI 工具全是"垂直 SaaS + 零配置"卖**结果**（Lindy $49/月、Reclaim $8/月、Manus、Replit Agent）。
AOS 现在这形态更接近 Dify/n8n 的"自托管引擎"——买主是开发者，不是终端 OPC。

### 要让人愿意付费，差的三层

```
① 引擎层（已有，强）：FabricHub + 反思闭环 + 并行  ← 真实壁垒
② 产品层（缺）：      一键托管 / 账号 / 可视化搭流 / 模板市场  ← OPC 进不来的门
③ 价值层（缺）：      垂直场景模板（自媒体一人公司包 / 独立顾问获客包）← 第一天看到 ROI
```

**一句话**：技术是已经赢了的仗；商业化要赢的是"把引擎包成 OPC 敢点、点了就出活儿的产品"。引擎是壁垒，但壁垒不等于门票。

---

## 2. 五阶段价值链设计

### 为什么是这五阶段（不是垂直行业模板）

用户洞察：不管做什么一人公司，都得**分析（研报）→ 宣传（自媒体）→ 获客 → 交付 → 维护/回流**。
这抓的是**通用价值链**，不是某个行业的特殊流程——TAM 比垂直模板大一个量级。

### 设计决策（三个批判性修正）

| 原始构想 | 修正后 | 为什么 |
|---|---|---|
| 分析→宣传→获客→维护 | + **交付** | 获客只是拿到客户，交付（实际干活、出交付物）才是产生收入/口碑的环节。只有内容创作者"内容=产品"才宣传≈交付 |
| "宣传"="自媒体" | 扩成**多渠道分发** | B2B 顾问是 LinkedIn/私域/冷邮件；电商是货架+投流。只限自媒体会把高付费意愿 B2B solo 顾问挡在门外 |
| "回流"喂回啥 | 点明是**教训→分析** | 回流数据（好评/复购/互动/获客失败原因）经 AOS 反思引擎+Meta-Trace 提炼成教训，自动喂回下轮分析——这是 AOS 区别于普通 RPA 的最值钱一跃 |

### 五阶段定义（`opc_loop.py:build_default_stages`）

| 阶段 | 能力标签 | 副作用 | 并行安全 | 需确认 | 说明 |
|---|---|---|---|---|---|
| analyze 分析·研报 | web.search | 否 | ✅ | 否 | 市场/竞品/选题研报 |
| promote 宣传·多渠道 | media.image | 否 | ✅ | 否 | 多渠道分发文案+配图 |
| acquire 获客 | channel.access | **是** | ❌ | **是** | 发布/触达潜在客户 |
| deliver 交付 | action.code_exec | **是** | ❌ | **是** | 产出文件/执行代码/交付报告 |
| maintain 维护·回流 | inference.llm | 否 | ✅ | 否 | 汇总结果，提炼可复用经验 |

**安全纪律**（AGENTS.md §5/§2.5）：
- 副作用阶段（获客/交付）强制串行 + 确认门控，绝不并发、绝不默认越权
- 只读安全阶段（分析/宣传/维护）可并入并行组（`parallel_safe=True`）

---

## 3. OPC 飞轮与认知闭环的关系

两者是**不同抽象层**，不冲突：

| 维度 | 认知闭环（`AOS_COGNITIVE_LOOP.md`） | OPC 飞轮（本文档） |
|---|---|---|
| 抽象层 | 认知处理链 | 业务价值链 |
| 阶段 | 感知-理解-规划-控制-反馈 | 分析-宣传-获客-交付-维护/回流 |
| 落点 | `autopilot.py` 主循环 | `opc_loop.py` 常驻环 |
| 关系 | OPC 每个业务阶段**内部**跑认知闭环 | 认知闭环是 OPC 飞轮的执行引擎 |

**OPC 飞轮的每个业务阶段，内部都是一次完整的认知闭环**：
- analyze 阶段 = 感知(web.search) + 理解(inference.llm) + 反馈(教训写入 Meta-Trace)
- acquire 阶段 = 规划(怎么触达) + 控制(channel.access 执行) + 反馈(触达结果)
- maintain 阶段 = 感知(运行结果) + 理解(LLM 汇总) + 反馈(教训沉淀)

OPC 飞轮是"认知闭环的业务外壳"，认知闭环是"OPC 飞轮的执行内核"。

---

## 4. 原型现状

### 4.1 `src/kernel/opc_loop.py`（常驻环，可扩展四层）

| 扩展点 | 说明 | 用法 |
|---|---|---|
| Stage 注册表 | 加业务阶段 = `register_stage(Stage(...))` 一条 | 主循环不动 |
| OPCLoopConfig | 阶段开关/渠道/轮次/确认模式全可配 | `OPCLoopConfig(business=..., enabled_stage_ids=[...])` |
| 可插拔依赖 | executor/lesson_store/confirm_fn 均可注入 | 生产默认接 autopilot，测试注入 mock |
| 生命周期钩子 | on_stage_end/on_cycle_end 回调 | 供自定义观测或干预 |

**懒加载**：`import opc_loop` 不触发 autopilot 重导入（实测验证），测试轻量。

### 4.2 `examples/opc_cli.py`（开箱 CLI 入口）

四场景预设：
| 场景 | business 模板 | 阶段 |
|---|---|---|
| content-creator | 自媒体一人公司 | 全链路 |
| consultant | 独立顾问 | 全链路 |
| ecommerce | 一人电商 | 全链路 |
| research | 研报服务 | analyze+maintain（最小闭环） |

加场景 = 在 `SCENARIOS` 字典加一条，主程序不动。

### 4.3 测试

| 测试文件 | 项数 | 耗时 | 说明 |
|---|---|---|---|
| `tests/test_opc_loop.py` | 6 | 1s | mock 模式，无 LLM |
| `tests/test_opc_cli.py` | 8 | 0.58s | 含 --help / 场景 / dry-run / --yes |

---

## 5. 运行指南

### 5.1 dry-run（不调 LLM，看飞轮怎么转）

```powershell
cd D:\AOS
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe examples\opc_cli.py -s content-creator -c 1 --dry-run
```

### 5.2 真跑（需 .env 配好 LLM/搜索 key，副作用阶段逐一确认）

```powershell
cd D:\AOS
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe examples\opc_cli.py -s consultant -c 1
```

### 5.3 交互模式（无参数，提示选场景）

```powershell
cd D:\AOS
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe examples\opc_cli.py
```

### 5.4 参数全表

| 参数 | 说明 | 默认 |
|---|---|---|
| `-b/--business` | 业务描述（自然语言） | 无（用 -s 预设或交互输入） |
| `-s/--scenario` | 场景预设 | 无 |
| `-c/--cycles` | 飞轮轮次 | 1 |
| `--stages` | 指定阶段（逗号分隔） | 全部 |
| `--dry-run` | 只打印不真调 LLM | False |
| `--yes` | 跳过副作用确认（危险） | False |
| `--planner` | 规划器 heuristic/ag2 | heuristic |

### 5.5 真机彩蛋

dry-run 跑 research 场景时，分析阶段任务文本自动注入 Meta-Trace 真实历史教训
（`[历史教训-务必参考] 原失败：步骤1[action.code_exec]...`）——**证明反思记忆真接上**，
跨任务教训自动喂回分析阶段，飞轮自改进不是空话。

---

## 6. 下一步

| 方向 | 说明 | 优先级 |
|---|---|---|
| 真机端到端验证 | 接真实 autopilot.run 跑一轮完整飞轮，拿 Meta-Trace 跨轮沉淀硬证据 | 高 |
| 渠道适配器 | acquire 阶段的 channel.access 现在只是标签，真要发自媒体/私域得接对应适配器 | 中 |
| Web 入口 | 把 CLI 包成最小 Web UI，让非技术用户点按钮就能跑 | 中 |
| 产品层 | 一键托管/账号/可视化搭流/模板市场（补第 1 节的②③层） | 低（需大投入） |

**建议先做真机验证**：用最小代价拿到"飞轮真的自改进"的端到端证据——那个证据才是对外吹 AOS 时的硬通货。
