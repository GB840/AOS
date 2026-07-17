# WAIC 2026 × AOS 全局映射报告

> 生成时间：2026-07-18｜信息源：WAIC 官网 + 澎湃/腾讯/搜狐 2026-07-16~17 报道
> 目的：把「世界人工大会内容 + 用户工具栈 + TRAE 工作流 + AOS 现状」汇总，并从**全局→架构→模块→细微**四层映射到 AOS 项目。

---

## 〇、前言：为什么做这份映射

WAIC 2026 正在上海举办（7/17–20，主题「智能伙伴 共创未来」）。一个关键发现：**本届大会的主线程，几乎就是 AOS 正在构建的东西**——通用智能体操作系统、自主执行、智能体生产工厂、Skill 生态。本报告不是凑热点，而是用行业最新信号校准 AOS 的方向，确认「我们没走偏」，并指出 WAIC 产品普遍缺失、而 AOS 理念里自带的那块护城河。

---

## 一、世界人工大会（WAIC 2026）内容总结

### 1.1 基本盘
- **时间/地点**：2026-07-17 ~ 07-20，上海（世博 / 张江 / 西岸「三地四馆」）
- **主题**：智能伙伴，共创未来
- **规模**：展览面积首破 10 万㎡，1100+ 企业参展，3000+ 展品，300+ 款全球首发
- **学术**：9 位图灵奖 / 诺奖得主，姚期智领衔首届 WAIC Academic，162 亿意向合作签约

### 1.2 四大主线（本届核心）
| 主线 | 内核 | 代表展品 |
|---|---|---|
| **① 智算集群** | 从「堆卡」转向「造系统」：芯片/网络/液冷/存储/调度软件必须系统化 | 华为 Atlas 950 SuperPoD（单柜 64 卡、最大 8192 NPU 互联）、中科曙光 8000「登峰」十万卡超集群、新华三 UniPoD S80000、中兴 OEX 超节点 |
| **② 国产 AI 芯片生态闭环** | 从芯片→板卡→服务器→超节点→集群→行业客户，全链路自研 | 安谋（周易 NPU/星辰 CPU）、摩尔线程（三大 AI 工厂）、昆仑芯、沐曦、天数智芯、此芯 Agentic SoC P1（端侧多智能体并发） |
| **③ 具身智能量产元年** | 机器人从炫技走向「进厂打工」，2026 = 量产元年 | 智元远征 A3 Ultra（量产全尺寸人形、700TOPS）、宇树载人机甲 GD01、节卡工业具身平台、300+ 台机器人实景演示 |
| **④ Token 时代 / AI 工厂** | Token 成为 AI 生产力计量单位；推理成本与稳定性成核心竞争力 | 无问芯穹「Token 超级工厂」M×N 范式（M 模型×N 芯片，推理成本降 10×）、西门子 Eigen Engineering Agent、摩尔线程「模型训练/词元生产/智能体生产」三工厂 |

### 1.3 范式级判断（行业共识）
1. **从「被动应答」→「主动感知、自主执行、人机共生」**：技术重心从「会对话」转向「复杂任务自主拆解、全程自动落地」。
2. **通用智能体操作系统成为主线程**：阶跃星辰展示 Agent OS（智能体能力从单 App 上升到 OS 层，打通手机/工业设备/机器人）；百度「搭子」通用智能体听懂自然语言自主完成报告/PPT 工作流。
3. **AI 工厂范式**：模型训练工厂 / 词元生产工厂 / 智能体生产工厂——AI 商业化重心从「训练」转向「Token 生产」与「Agent 生产」。
4. **Skill 生态爆发**：小红书 RED Skill 全量上线，站内已发布 **3700+ 原创 Skill**，16 万活跃开发者，Vibe Coding 成发布能力。
5. **M×N 异构范式**：连接「M 种模型」与「N 种芯片」，软硬协同把算力变生产力。

---

## 二、全局内容汇总（WAIC + 工具栈 + TRAE + AOS）

### 2.1 用户工具栈速览（来自本消息）
| 工具 | 角色 | 与 AOS 的关系 |
|---|---|---|
| WorkBuddy | 桌面操控（键鼠模拟、跨应用） | AOS 的「物理世界 / 具身」执行入口候选 |
| Desktop-Touch-MCP / Omni-Video Studio MCP | 视觉执行 + 视频处理 | 视觉理解与 media.image/video 的本地执行层 |
| CodeArts / 码道 | AI 编码辅助 | 对标 AOS 的 code.generate（CodeTeamAdapter） |
| Jcode / Qwen Code | 多 Agent 协作 + 编码加速 | 对标 AOS 的 ag2 / agnes 子智能体协作 |
| Hermes Studio | 工作流编排 + 多模型协作 | 对标 AOS 的 OrchestrationChiplet / workflow_engine |
| 智果（AgentArts） | 企业级智能体编排 | 对标 AOS FabricHub 的企业级调度 |
| Desktop-Touch-MCP / VN Skill | Windows 桌面执行层 + 视频 | 桌面自动化与视频生成的落地层 |

### 2.2 TRAE `/goal` 工作流速览（来自本消息）
- **执行引擎**：Agent 的 Goal 模式；**配套机制**：Spec（系统级，产出 spec.md/tasks.md/checklist.md）与 Plan（模块级）。
- **核心方法**：`/goal` 指令内显式写「验收标准」，Agent 自动生成 checklist 逐项校验；支持子智能体（如安全审查）与中断恢复（`继续完成 {任务名}`）。
- **与 AOS 的对应**：这正是 AOS 的「五阶段人机协作工作流引擎（workflow_engine.py，理念 1/5/8 运行时）」+ content_director 的 human-in-the-loop（审核 approve 才发布）的同源模式。

### 2.3 AOS 现状速览（来自项目记忆与本会话核验）
- **宪法**：九大核心理念（自闭环 / 失败即训练 / 芯粒隔离≠多 Agent / 万物为我所用 / 能力即路由 / 诚实量化 / 千人千面 / 白盒进化 / 可验证真理）。
- **运行时**：FabricHub 单一内核（capability 优先 + tier 高→中→低级联 + 故障转移 + RoutePredictor 学习）。
- **资产**：23 适配器、270 agency_roles 角色库、content_director 七阶段流水线（已接 memory.knowledge / vision.understand / 角色库）、MemoryDistiller 常驻（但产出 `distilled_memory.jsonl` 当前只写不读——死路）。
- **缺口（上一轮已确认）**：① 白盒进化未闭环（蒸馏记忆无消费者）② brain.py 双轨未收口 ③ 知识引擎无统一入口 ④ 真实出图需 host GPU。

### 2.4 一句话总括
**WAIC 证明「自主执行 + 通用 Agent OS + 智能体工厂 + Skill 生态」是 2026 行业主航道；用户工具栈补齐了 AOS 缺的「桌面/视觉/视频/企业编排」执行层；TRAE 工作流佐证了 AOS 工作流引擎的设计；而 AOS 真正的差异化护城河，是 WAIC 展品普遍没有的「白盒可进化」闭环。**

---

## 三、映射到 AOS 项目（全局 → 细微）

### 3.1 全局层：WAIC 四大主线 × AOS 九大理念
| WAIC 主线 | AOS 对应理念 | AOS 对应物 | 吻合度 |
|---|---|---|---|
| 通用智能体操作系统 | 理念 5（能力即路由·权限即边界） | FabricHub 单一内核 + chiplet 隔离 | ★★★★★ 直接同构 |
| 自主执行 / 全程自动落地 | 理念 1（不手配自闭环）· 理念 8 | content_director 七阶段 · OrchestrationChiplet | ★★★★★ |
| AI 工厂（智能体生产工厂） | 理念 4（万物为我所用）· 理念 9 | 流水线即「智能体工厂」· 量化置信 | ★★★★☆ |
| M×N 异构（M 模型×N 芯片） | 理念 5 + tier 路由 | inference.llm 三提供者 / media 双提供者级联 | ★★★★☆ |
| Skill 生态爆发 | 理念 7（千人千面） | 270 agency_roles + skills 体系 | ★★★☆☆ 待生态化 |
| 具身 / 物理世界 AI | 理念 4（万物为我所用） | WorkBuddy + Desktop-Touch-MCP（待接入） | ★★★☆☆ 未接 |
| Token 生产效率 | 理念 6（诚实+量化） | route_outcomes 量化延迟/成败 | ★★★★☆ |

### 3.2 架构层：行业 Agent OS 趋势 × FabricHub 单一内核
- **行业信号**：阶跃星辰 Agent OS 把智能体能力「从单 App 上升到 OS 层」。AOS 的 FabricHub 正是这一思路的工程实现——**不在 App 里堆功能，而在内核做统一路由 + 隔离计算单元**。
- **「造系统」vs「堆卡」**：WAIC 共识「AI 基础设施从堆卡转向造系统」，与用户反复强调的「有效组建、别留孤岛」完全同构。AOS 的上一轮修复（content_director 接 memory.knowledge/vision/角色库）就是一次「造系统」实践。
- **M×N 范式 ↔ tier×capability 矩阵**：WAIC 的「M 模型 × N 芯片极致效率」= AOS 的「capability 维度 × tier 维度」路由矩阵，二者数学同构。AOS 已具备，可明确对外表述为「AOS 的 M×N 是模型/引擎×档位」。

### 3.3 模块层：WAIC 能力 × AOS 适配器 / 芯粒
| WAIC 能力信号 | AOS capability | 适配器 / 芯粒 | 现状 |
|---|---|---|---|
| 通用 Agent OS | system.workflow | OrchestrationChiplet + workflow_engine | ✅ 真跑 |
| 大模型自主思考 | inference.llm | litellm / lfm / agnes（三提供者 tier 级联） | ✅ |
| 视觉理解 / 多模态 | vision.understand | vlm_adapter | ✅ 已接 content_director |
| 图像 / 视频生成 | media.image / media.video | comfyui（HIGH）/ agnes（MEDIUM） | ⚠️ sandbox 降级占位，host GPU 才真出图 |
| 知识 / 记忆底座 | memory.knowledge | cognee / lightrag / zvec（**无统一入口**） | ⚠️ 半通电 |
| 检索 | web.search | search_adapter（多源级联） | ✅ |
| 编码加速 | code.generate | codeteam | ✅ |
| 多 Agent 协作 | agnes / ag2（隔离计算单元） | 子进程隔离 | ✅ |
| 桌面 / 物理世界执行 | （新增候选）desktop.automation | WorkBuddy + Desktop-Touch-MCP | ❌ 未接入 FabricHub |
| Skill 生态 | skills / agency_roles | 270 roles + skill 体系 | ⚠️ 未生态化分发 |

### 3.4 细微层：从 WAIC 洞察推出的 AOS 下一步（按杠杆排序）

**① 白盒进化闭环（AOS 独有护城河，WAIC 展品均无）**——最高优先。
WAIC 全场的「自主执行」产品，没有一款展示「执行后自我提炼、改进行为」的闭环。这正是 AOS 理念 8（白盒才可进化）+ 理念 2（失败即训练数据）的差异化。当前 `MemoryDistiller` 已在跑、已写 `distilled_memory.jsonl`，但**无人读它**。下一步：让 FabricRegistry 启动加载该文件作路由软偏好（失败率超阈值降级候选，置信门控 ≥5 样本才生效）+ OrchestrationChiplet/content_director 每步 emit `trace_*.json` 补齐生产者 + 回读测试。沙箱可全真验证。

**② Skill 生态化（对标 RED Skill 3700+）**。
WAIC 证明「Skill 是 AI 能力的基本单元」。AOS 已有 270 个 agency_roles + skills 体系，但仍是「内部库」而非「可分发生态」。机会：把角色库 / skill 标准化为可安装、可评分、可检索的市场形态，让 content_director 按任务动态装配——直接呼应理念 7（千人千面）。

**③ 桌面 / 物理世界执行层接入（具身智能主线的 AOS 落点）**。
WAIC 第三主线是具身智能量产。AOS 不必造机器人，但应把用户已有的 **WorkBuddy + Desktop-Touch-MCP** 接为 FabricHub 的 `desktop.automation` 能力——这等于给 AOS 一个「进入物理/桌面世界的手」，与大会「AI 从屏幕走进现实」同频。

**④ 双轨收口 / ⑤ 知识引擎统一入口 / ⑥ 真实出图**（上一轮已列，WAIC 未改变优先级，从略）。

**⑦ 哲学张力提示（需你拍板）**：WAIC 主推「多智能体并发」（此芯 Agentic SoC 端侧多 Agent 并发），而 AOS 刻意采用「单一内核 + chiplet 故障隔离（非多 Agent 分解）」。二者不矛盾——AOS 的隔离是熔断边界，WAIC 的并发是协作形态；但后续若要做「多 Agent 并行编排」，需明确是在 FabricHub 调度下派发隔离单元，而非退化为自治多 Agent。

---

## 四、结论与建议优先级（WAIC 视角加权）

| 优先级 | 动作 | WAIC 印证 | 沙箱可验 | 备注 |
|---|---|---|---|---|
| **P0** | ① 白盒进化闭环（蒸馏记忆回流） | 全场缺「自我进化」，AOS 独有 | ✅ | 上一轮已建议，WAIC 进一步佐证其战略价值 |
| **P1** | ③ 桌面执行层接入（WorkBuddy+MCP） | 具身/物理世界主线 | ⚠️ 需 host | 用户工具栈已备，接 FabricHub 即可 |
| **P1** | ② Skill 生态化 | RED Skill 3700+ 验证方向 | ✅ | 把已有 270 roles 升级为市场 |
| **P2** | ④ 双轨收口 / ⑤ 知识统一 / ⑥ 真实出图 | 通用 Agent OS 需单一干净内核 | ⚠️ 需 host | 上一轮已列 |

**一句话收口**：WAIC 2026 等于一份「行业帮 AOS 背书」的报告——自主执行、通用 Agent OS、智能体工厂、Skill 生态全中。AOS 现在最该做的，不是再追新芯粒，而是把已经建好却被闲置的**白盒进化闭环**接通，把用户已有的**桌面执行层**接进 FabricHub，并把 **270 角色库生态化**——这三刀都落在「有效组建」上，与用户一贯要求完全一致。
