# AOS × 因果世界模型（Causal World Model）

> 外部素材：`中数睿智` 在 WAIC 2026（2026-07-17）发布《因果世界模型技术体系蓝皮书》，
> 提出「元因果」认知理论与动态因果构建引擎，落地 35 家央国企、800+ 零容错场景、
> 累计运行 15000+ 小时。本文件经新华网 / 新浪财经 / 央视等多源交叉核实，**素材真实无编撰**。
> 本文不是复述蓝皮书，而是把它的「三层因果阶梯」**落地为 AOS 已有的可运行能力**，
> 证明 AOS 的范式与本田（中数睿智）在同一方向上，但 AOS 把它做成**本地优先、开源、零锁定的
> 自进化 agent OS**——而中数睿智聚焦工业零容错决策。

## 一、三层因果阶梯 ↔ AOS 映射

珀尔（Judea Pearl）因果之梯本是「关联 → 干预 → 反事实」。蓝皮书把它对应到 AI 从
「描述世界」到「理解世界如何运转」的跃迁。AOS 早已在架构里埋好这三层：

| 因果层级 | 蓝皮书含义 | AOS 既有对应 | 新落地模块 |
|---|---|---|---|
| **关联认知** (association) | 识别「什么与什么同时出现」 | Trace 全链路观测（理念8 白盒 Trace）、`assess` 三级量化置信（理念6） | 已有 |
| **干预认知** (intervention) | 回答「如果这样做会怎样」 | autopilot 反思闭环：失败→假设「换做法 Y」→重设计计划→执行→量测（理念2.5） | `kernel/causal.py: CausalModel.effect_of` |
| **反事实认知** (counterfactual) | 回答「如果当初换种做法会如何」 | Meta-Trace 反思记忆：失败教训跨任务注入（求是引擎启发） | `kernel/causal.py: CausalModel.counterfactual` |
| **事前可验证** (verifiable) | 结果发生前即可评估对错 | 诚实闸门 `_verdict` / `_needs_reflection`：无真实证据不报成功（理念9） | `CausalModel` 样本不足即 `unknown` |

关键洞察：**AOS 的反思闭环本质上就是「干预认知」的运行态**，Meta-Trace 就是
「反事实认知」的持久化。我们缺的只是把这两层**显式建模成可查询的因果结构**——
`kernel/causal.py` 补上这一环。

## 二、蓝皮书五大短板 ↔ AOS 的回答

| 短板 | 蓝皮书描述 | AOS 现状 / 解法 |
|---|---|---|
| 事实幻觉 | 生成看似合理却违背事实 | 全链路真实闸门 + 白盒 Trace，谎报成功即判失败（诚实可验证 OS） |
| 重描述、轻推演 | 只能刻画现状 | `CausalModel.effect_of` 估计「换做法成功率」，把推演变成可计数估计 |
| 缺乏时序维度 | 无法判断「一秒后还是一年后」 | 记忆 TTL / 分层降级（理念2）：带时间戳与热度，长期未命中的自动遗忘 |
| 事前不可验证 | 结果显现时损失已无法挽回 | 路由/反思级真实闸门，每一步带可复核证据；因果估计样本不足即 `unknown` |
| 规则堆叠难以为继 | 人工拼规则越补越脆弱 | 动态路由 + 白盒蒸馏（`evolution_distiller`）：不可靠引擎自动沉底，**不写死规则** |

## 三、元因果 / 动态本体 ↔ AOS 的「神经+符号」架构

蓝皮书核心工程思路：**「神经网络拓展认知边界，符号逻辑坚守安全底线」**——
LLM（神经侧）发散提候选，动态本体（符号侧）刚性校验、不通过即退回重做。

这**恰恰就是 AOS 已落地的架构**：
- 神经侧：LLM 经 `inference.llm` 芯粒自由推理、生成计划；
- 符号侧：`PolicyEngine`（`kernel/compliance.py`）+ 权限边界（理念5）+ 诚实闸门，
  任何越界/虚假产出被**符号层硬拒**（参考 T3 抗复合失败闸门）；
- 动态演化：记忆生命周期桥接层（`memory/lifecycle.py`）按热度/TTL 自动演化，
  不是静态写死的知识图谱。

> 一句话：中数睿智用「动态本体」做工业零容错，AOS 用「统一内核 + 符号边界 + 白盒蒸馏」
> 做 agent 自进化——**同一套「神经发散、符号守底」哲学，不同主场**。

## 四、具体落地（已交付代码）

`src/kernel/causal.py` —— 轻量经验因果模型，仅标准库、可单测、白盒可审计：

- `Intervention(context, action, outcome)`：白盒 Trace 的最小因果单元，每样本都是
  一次**真实闸门**的成败判定（非模型臆测），保证因果估计可复核。
- `CausalModel.effect_of(ctx, action)`：干预认知——估计「在 ctx 下采取 action 的
  预期成功率」。**D4 深化**：显式标注 `inference_type=observational_association`
  （这是珀尔之梯**第一层关联**，不是 do-intervention 已证因果——路由成败吸收了大量
  未控混淆变量）；输出 **Wilson 95% 置信区间**与置信级别 `low/medium/high`，
  样本不足（`MIN_SAMPLES=5`）诚实返回 `unknown`（事前不可验证）。绝不 5 样本就报确定比率。
- `CausalModel.counterfactual(ctx, actual, alt, costs)`：反事实认知——估计「若当初换
  alt 是否更优」。**D5 深化**：除成功率差 `delta` 外，额外给出**效用差** `utility_delta`
  （注入各动作成本后，「成功率更高」未必「更值」），直接喂给 autopilot 反思做「换做法」决策。
- `CausalModel.best_action(ctx, actions, weights, costs, latencies)`：**D5 决策论层**——
  默认退化为「比成功率」，支持带权决策 `utility = 成功率·rate − 成本·cost − 时延·latency`，
  在约束下挑真最优（而非单指标次优）。
- `CausalModel.from_distiller(distiller)`：复用 `EvolutionDistiller` 已在路由热路径
  收集的 (能力,引擎)→成败，把**白盒蒸馏直接上升为因果干预效应**，零重复采集。

测试：`tests/test_causal.py`（10 passed）——覆盖 unknown 下限、Wilson 区间边界、
观测相关标注、反事实效用反转、带权 best_action 选更便宜动作、`from_distiller` 复用蒸馏统计。

## 五、与中数睿智的差异化（诚实定位）

| 维度 | 中数睿智 因果世界模型 | AOS |
|---|---|---|
| 主场 | 工业零容错决策（油气/电网/制造） | 本地优先的自进化 agent OS |
| 形态 | 闭源企业产品 / 行业方案 | 开源、零锁定、可审计 |
| 因果数据来源 | 行业业务规则 + 动态本体 | 白盒 Trace + 真实闸门 + 蒸馏统计 |
| 递归自进化 | 动态因果图自演化 | 反思闭环 + Meta-Trace + 白盒蒸馏沉底 |

AOS 不复制工业因果产品，而是把「因果之梯」变成**自进化 agent 的内建推理层**——
让 agent 在每一步都知道「换做法会怎样、当初换做法是否更好」，且全部可复核。

## 六、下一步（可选）

1. 把 `CausalModel` 接进 autopilot 反思：反思时调用 `counterfactual` 选最优「换做法」。
2. 在 Trace 写入结构化 `intervention`（planned action + observed effect），使反事实
   查询贯穿全链路，而非仅统计层。
3. 路由决策复用 `effect_of`：在 `evolution_distiller` 沉底之外，增加「因果优先选引擎」。
