# 华为云 AgentArts（智果）/ openJiuwen 核实与借鉴研判

> 来源：用户贴文档 + 自附"核实表"，按求是铁律先全网交叉验证再研判。
> 核实日期：2026-07-16。当前主机无 GPU（见 `docs/aos_model_integration.md` §E）。

---

## 一、核实结论：文档基本属实，但有 2 处需校准

| 文档说法 | 核实结果 | 证据 |
|---|---|---|
| AgentArts 2026-6-5 INSPIRE 公测 | ✅ 属实 | 华为云官方新闻稿 `huaweicloud.com/news/2026/20260605100619686.html`、新华网、光明网 |
| openJiuwen 开源版、内核同源 >90% | ✅ 开源属实；"同源>90%"是**华为自己宣称**的营销口径，非第三方独立审计 | openjiuwen.com 真实存在；"90%"出自华为发布会口径 |
| JiuwenSwarm 率先支持 A2UI | ✅ 属实 | 51CTO 博客确认，且 A2UI 是 Google 开源协议（见下） |
| Harness 框架 / 长程 80% / 记忆召回 90% | ✅ 属实 | 华为云论坛 `bbs.huaweicloud.com/blogs/478894` 原文 |
| OfficeAce / 智果园 / 百模千态 | ✅ 属实 | 多源印证 |
| "完全本地离线运行"暗示 | ⚠️ **失实**。AgentArts 本质是**华为云 SaaS**，数据/算力在华为云；openJiuwen 才支持私有化部署 | 华为云官方文档明确"公测需申请、免费基础版限 200 万 tokens/1G 知识库"；openJiuwen 百科明确"支持私有化部署" |
| 开源协议 | ⚠️ 文献不一：openJiuwen 核心多源称 **MIT**（百度百科/newton），其衍生工具 JiuwenClaw 称 **Apache 2.0**（网易）。复用前需在 GitHub 实际仓库核实 | 见下"能不能用" |

**结论**：文档整体框架与华为官方一致，可放心作为"参考架构"。但务必区分两层——**AgentArts（云 SaaS）** 与 **openJiuwen（可私有部署的开源版）** 的可借鉴性天差地别。

---

## 二、能不能用（可用性判断）

### AgentArts（智果）—— 不能用做 AOS 组件
- 它是**华为云付费 SaaS**，需华为账号、数据上云、按 token/资源包计费。
- 与 AOS 九大理念直接冲突：**不手配自闭环 / 万物为我所用 / 零付费必选项 / 黑盒不可训白盒才可进化**。把 AOS 变成 AgentArts 前端 = 把主权交给华为云。
- **定位关系**：AgentArts 是"运行平台（云）"，AOS 是"操作系统（本地编排内核）"——抽象层不同，AOS 不该下沉成它的壳。
- **正确用法**：仅作**参考架构**，不集成。

### openJiuwen —— 可研究/可借鉴思路，但不替换 AOS 核心
- 真实开源（MIT 口径为主，支持私有化部署），生产级（其 DeepAgent/DeepSearch 登顶 GAIA 91.69% / BrowseComp-Plus 80%）。
- 架构分层 **Studio / Core / Ops** 与 AOS 的"交互层 / 编排内核 / 治理运维"高度同构——印证 AOS 分层设计方向对。
- **但是**：AOS 已有可工作的编排（workflow_engine.py DAG、autopilot.py 反思循环、FabricHub 路由、刚刚落地的 VLMAdapter + 自编码器记忆压缩）。**fork openJiuwen 替换 AOS 内核 = 重复造轮子 + 丢掉已验证的能力**。
- **正确用法**：**精读其源码的特定模式**（A2UI 接入、SwarmFlow 生成、上下文引擎压缩/卸载），把思路借进 AOS 现有组件，而非整体引入。

---

## 三、有没有借鉴（按性价比分级，映射到 AOS 现有代码）

### P0 —— 直接可借，摩擦最小

**1. A2UI 协议（Agent-to-User Interface）**
- 是什么：Google 开源（Apache 2.0）的**声明式 UI 协议**——agent 发 JSON 描述界面，客户端用原生组件渲染，**不执行任意代码**（安全），跨 Web/移动/桌面。
- 为什么是 P0：**AOS 刚落地的 VLMAdapter 让 agent"能看"界面（读），A2UI 是互补方向——agent"能画"界面（写）给客户端**。
- **杀手级连接**：AOS 的规划后端 `ag2` **原生支持 A2UI**（`A2UIAgent`，见 a2ui.org/ecosystem）。我们已依赖 ag2，接入 A2UI 几乎是零新增依赖。
- 落地映射：在 `interaction`/前端层加一个 A2UI 渲染器 + 让 `ag2` 规划产物可选地输出 A2UI JSON（复用 `src/kernel/plugins/orchestration_chiplet.py` 的规划输出）。安全收益直接对齐理念 5（权限即边界）+ 理念 6（诚实/可验证）。

**2. 上下文引擎：异步压缩 + 动态卸载 + 结构化上下文 + 多角度推理树**
- openJiuwen 的"上下文引擎"做：异步压缩、动态卸载、问题状态统一建模为可持续更新的结构化上下文、多角度推理树并发探索、文本梯度提示词优化。
- 映射 AOS：我们刚建的 `src/kernel/memory_compression.py`（自编码器压缩 + 重构误差异常检测）是起点。可借：
  - **动态卸载**：旧 trace 压成低维码后**真正移出热 JSONL 到 cold sidecar**（当前只压缩不卸载）；
  - **结构化上下文 + 推理树**：把 `autopilot.py` 的 `_RunState` / 反思日志建模成可追溯的推理树，而非扁平列表。

### P1 —— 有价值，需少量适配

**3. Swarm Skills / SwarmFlow（自然语言/流程图 → 工作流）**
- openJiuwen 能从一句话或一张流程图生成 SwarmFlow（标准化技能包 + 执行脚本）。
- 映射 AOS：`workflow_engine.py` 已有 DAG + `HandoffEnvelope` 结构化交接。`autopilot.py` 的 ag2 规划已产出带 `[AOS能力]` 标签的步骤。可借"描述→工作流"生成器，复用 ag2，把自然语言直接落成 `workflow_engine` 的 DAG。

**4. 模型路由三策略（成本优先 / 效果优先 / 均衡）**
- 华为 MaaS 路由支持这三种策略。
- 映射 AOS：`capability.py` 已有 `TIER_HIGH/MEDIUM/LOW/AUTO` 级联。可借**显式三策略命名 + 成本感知路由**（当前 tier 只管"高→中→低"级联，没显式 cost/quality 旋钮）。

**5. 事件驱动多 agent + 状态持久化/断点续执**
- openJiuwen 支持事件驱动中断/跳转/恢复、任务状态持久化。
- 映射 AOS：`autopilot.py` 的 `_RunState.to_dict/from_dict` 已有持久化。可借"事件驱动的中断-恢复"模式强化当前循环（目前是同步 cycle 推进）。

### P2 —— 仅作确认，不新增工作
- **Harness 框架**：华为"harness engineering"（工具/数据/记忆/模型/流程编排）≈ AOS 的 FabricHub + workflow_engine + autopilot 组合。**概念被 AOS 已有架构验证，无需新做**。
- **轻量沙箱（100ms 启动）**：AOS 走 `subprocess_iso` + code-exec 适配器（进程隔离），路线不同但目标一致，记一笔不追。

---

## 四、明确不借（避免重复工程 / 违反理念）
- ❌ **不把 AOS 接成 AgentArts 前端**（云锁定，违背零付费/自闭环）。
- ❌ **不整体引入 openJiuwen 替换内核**（AOS 已有可工作编排，重复建设）。
- ❌ **不借 GNN 做多 agent 协调**（AOS 已定：`workflow_engine.py` DAG 覆盖，杀牛刀不用）。
- ❌ **不借 GAN**（与编排/记忆核心无关，红队为远期可选）。

---

## 五、建议下一步（按"性价比最高先动"）
1. **P0-1 A2UI**：因 ag2 原生支持，摩擦最小、收益最大（补全"agent 能画界面"闭环，且安全）。建议作为下一个落地项。
2. **P0-2 记忆卸载**：在 `memory_compression.py` 上加"压缩后真正卸载旧 trace 到 cold sidecar + 推理树结构"。
3. 二者都不动 AOS 内核定位，纯增量增强，符合"模型/协议是能力端点"原则。

> 注：openJiuwen 协议（MIT 口径）与 A2UI（Apache 2.0）均为宽松许可，借鉴思路/对接协议无合规风险；若未来直接复用其代码段，须先核实 GitHub 仓库实际 LICENSE 文件。

---

## §G P0-1 A2UI 已落地（2026-07-16，用户拍板"开始"）

A2UI 协议经全网核实为 Google 开源真实协议（a2ui.org，Apache 2.0，v0.9.1 现行；autogen/ag2 0.14.0 自带 `A2UIAgent` 印证"原生支持、摩擦最小"的 claim 成立）。

**已建代码（均真跑测试，非纸面）**：
- `src/core/fabric/a2ui.py`：v0.9 basic catalog 对齐（18 组件白名单）+ `A2UIBuilder`（发 createSurface/updateComponents/updateDataModel/deleteSurface + 合并 surface）+ **纯标准库 HTML 渲染器** `render_html`（只渲已知组件、html.escape、拦截 `javascript:`/`data:` 危险 URL、无 eval/无 script 注入）+ `build_a2ui_report(trace,...)`（编排 trace→UI 报告）+ `__main__` 演示生成 HTML。
- 桥接：`orchestration_chiplet.py` 加 `orchestration_result_to_a2ui(result)`，把编排执行结果转 A2UI surface（agent 画界面闭环）。
- API：`src/api/main.py` 加 `POST /api/a2ui/render`（surface/messages→HTML）+ `GET /api/a2ui/demo`（自包含演示 HTML）。
- 测试：`tests/test_a2ui.py`（11 项全绿：XSS 转义、未知组件被拒、危险 URL 拦截、http(s) 放行、数据模型绑定、消息↔surface 往返、编排桥接）。

**价值**：AOS 从"盲"（仅文本/代码）升级为"能看（VLMAdapter）+ 能画（A2UI）"的安全闭环；A2UI 声明式、不执行代码，正好补全跨信任边界的 UI 安全模型。格式与 ag2 `A2UIAgent` 对齐，未来 ag2 规划产物可直接被本渲染器消费。
