# AOS 3D / 短剧生成芯粒 — 可行性 & 接入架构（接地气版）

> 定位：把外部资料里"Omma / 短剧编导插件"的方案，**重映射到 AOS 真实代码**。
> 原方案哲学（Chiplet 积木化 + MCP 通信 + 内核极简）与 AOS 实际架构 100% 同构；
> 但原方案把多个**外部产品愿景 / 尚未接入的工具**当成了现成组件。本文逐条纠正，并给出可落地的接入契约与分阶段计划。
>
> 参考现实：Phase 1a（`c864a39`）已给 FabricHub 加上 HTTP 服务模式（`src/core/fabric/http_server.py`，端口 8123），Phase 2（收敛 legacy 双轨）待启动。

---

## 1. 原方案里"对"的部分（保留，不要动）

| 原方案设计 | 为什么对 | AOS 真实对应 |
|---|---|---|
| Chiplet 积木化、4 个子Agent 独立 | 单一职责、可单独替换升级 | AOS 已是"单基座 + Skill 芯粒"：agnes/ag2 经子进程隔离成 chiplet，崩溃不传染宿主，热备切换 |
| 子Agent 经 MCP 协议通信 | 不绑定调度框架 | `src/mcp/protocol.py` 已实现 `MCPProtocol`（`aos_list_engines/aos_route/aos_invoke_engine/aos_run_task`）+ Phase1a 的 HTTP MCP |
| 内核极简、插件全可替换 | 架构第一性 | FabricHub 单一内核统一持有路由/记忆/上下文主权（`src/kernel/plugins/fabric_hub.py`），适配器可插拔 |
| 无限演化 / 零第三方限制 / 低配适配 | AOS 第一性 | 万物为我所用、端云合作、不绑定（SearchAdapter 多源兜底即范例） |

**结论**：方向对，不用推翻，只需把"假想组件"替换成"真实引擎"。

---

## 2. 原方案里"错位"的部分（必须纠正）

| 原方案说法 | 真实情况（基于本仓库代码） | 纠正 |
|---|---|---|
| "OpenClaw 调度框架注册 4 个 Agent" | OpenClaw 是**已注册的 web 自动化引擎**（`openclaw` 在 `_ADAPTERS` 中），不是调度框架 | 真实调度/规划 = `ag2`(planner) + `OrchestrationChiplet`（确定性多步流水线，已真跑验证 `d974553`+`8af5d90`） |
| "IMA 知识库" | IMA 是**外部产品愿景，非当前注册名**（见项目记忆） | 真实长期记忆 = `mem0`（已接，本地零成本） |
| "Mistralrs 本地模型" | mistralrs 同样**未注册成引擎** | 真实 LLM 推理 = `litellm` 适配器（接 ag2 规划）；要用本地模型得先真注册 mistralrs 引擎 |
| "SadTalker / Wav2Lip / Three.js" | 全是**未接入的外部工具**，仓库里没有 | 落地需新建适配器/skill（像我们给 `web_fetch/code_exec/file` 做的那样），不是"配置即用" |
| `aos_plugins.toml [plugins.short_drama]` | AOS 当前**没有**这个插件 TOML 机制 | 真实接入点 = FabricHub `register_*` + `MCPProtocol` + `scripts/aos.py` 子命令 |

---

## 3. 重映射：每个子Agent → 真实 AOS 部件

| 原方案子Agent | 真实 AOS 落地 | 现状 |
|---|---|---|
| 需求解析器 | `ag2` planner（产出带 `[AOS能力]` 标签的步骤）+ `parse_plan_to_steps`；或 `heuristic` 降级 | ✅ 已有（think→do 闭环已收口） |
| 分镜/剧本生成 | `OrchestrationChiplet` 一步调 `litellm`(`inference.llm`) 产出结构化分镜 | ✅ 已有（OrchestrationChiplet + litellm） |
| 提示词生成 | `litellm`(`inference.llm`)，提示词模板化 | ✅ 已有 |
| 渲染调度 | `OrchestrationChiplet` 编排：调 `agnes`(`media.image` 出关键帧) + **【待建】`threejs`/`video` 适配器** | ⚠️ 渲染部分待建 |
| 人物一致性锁 | `mem0` 存 character baseline（特征向量/结构化描述），每段提示词生成后做相似度校验 | ⚠️ 需建索引/校验逻辑（mem0 已可用） |
| Web / 预览面板 | 复用 Phase1a HTTP 服务模式（`/api/chat`、`/api/run_task`、`/api/mcp`） | ✅ 已有 |
| 与外部工具通信 | 复用 `MCPProtocol` / `http_server.py`，暴露为 `aos_*` 工具或自定义 MCP tool | ✅ 已有 |

> 关键发现：**文本链路（需求→分镜→提示词→一致性校验）100% 可用现有引擎跑通**，只有"渲染/视频合成"这一步需要新建适配器。所以第一阶段根本不用碰重型外部工具。

---

## 4. 需要新建的适配器（诚实清单）

全部为**纯增量**，不动现有逻辑，注册进 FabricHub 即可：

1. **`src/core/fabric/adapters/threejs_adapter.py`**【待建】
   - 职责：调本地 Three.js / 导出 GLB-GLTF（Omma 导出标准格式，可复用）。
   - 依赖：本机需有 Node.js（已装 v24）+ Three.js；或走 headless 渲染。
   - 能力标签建议：`media.3d`。

2. **`src/core/fabric/adapters/video_synth_adapter.py`**【待建】
   - 职责：封装 FFmpeg（合成）+ SadTalker / Wav2Lip（口播数字人）。
   - **8G CPU 硬约束**（原方案也承认）：SadTalker 官方偏 GPU，纯 CPU 渲染极慢。
     - 阶段原型用 **Wav2Lip + 关键帧** 验证链路，不追求画质；
     - 两级渲染：本地草稿（CPU 量化）→ 高质量再切云端（D-ID/Seedance 等，走"云端用不了就本地"哲学）。
   - 能力标签建议：`video.synth`。

3. **人物一致性校验逻辑**（非独立适配器，是 `mem0` 上的应用层）
   - 在 `mem0` 存 character baseline；提示词 Agent 输出后计算与 baseline 相似度，低于阈值自动修正/拒绝下发。

---

## 5. 接入契约（怎么挂进 FabricHub，零破坏）

遵循现有模式（参考 `web_fetch/code_exec/file` 三个零依赖适配器，提交 `10aca91`）：

```
新适配器继承现有 Adapter 基类
  → FabricHub.register_* 注册（或进 _ADAPTERS 列表）
  → 经 MCPProtocol 暴露为 mcp tool（或复用 http_server 加 /api/short_drama 端点）
  → OrchestrationChiplet 用 route_fn 把它编排进多步流水线
```

- **不删改** `brain.py` / `deerflow` / v5 `api/main.py` / `web/app.py`（与 consolidation 同一铁律：先增量、后退役）。
- 回滚安全网：新能力默认走 FabricHub 内核，v5 路径不变；可通过 `AOS_RUNTIME` 类开关切回。

---

## 6. 分阶段落地（增量优先，同 consolidation 打法）

| 阶段 | 内容 | 碰重型工具？ | 风险 |
|---|---|---|---|
| **Phase A（验证文本链路）** | `ag2`+`OrchestrationChiplet`+`litellm` 跑通"需求→分镜→提示词"，结果存 `mem0`；加人物一致性校验雏形 | ❌ 不碰 | 低（全用现有引擎） |
| **Phase B（3D 链路）** | 新建 `threejs_adapter`，生成 Three.js 场景/GLB，经 chiplet 编排 | 仅 Node/Three.js | 中（需本机 Node 环境） |
| **Phase C（视频合成）** | 新建 `video_synth_adapter`，封装 FFmpeg/Wav2Lip，8G CPU 降级策略 | 是（FFmpeg/Wav2Lip） | 高（硬件/质量） |
| **Phase D（UI/模板市场）** | 复用 Phase1a HTTP 服务模式做预览面板 + 风格模板导出/导入 | ❌ | 低 |

**建议从 Phase A 动手**：它证明"完整系统"的调度/规划/记忆闭环在 AOS 上成立，且零新依赖、零破坏、可立即真跑验证。渲染是后续叠加，不是前置阻塞。

---

## 7. 真实风险（不掩盖）

1. **8G CPU 跑视频生成慢**：SadTalker 数小时/分钟视频 → 两级渲染 + 云端降级（已在 Phase C 设计）。
2. **本地小模型分镜质量**：依赖 `litellm` 接的模型能力 → 阶段 A 先用**结构化模板填充**验证链路，阶段 B/C 再换专门微调模型。
3. **外部工具需安装**：Node/FFmpeg/SadTalker/Wav2Lip 本机是否齐备需先确认（沙箱无外网，装包得在用户主机）。
4. **与 consolidation 的关系**：本芯粒是**新增能力**，不依赖 legacy 双轨收敛；但 Phase 2 把 v5 入口切到 FabricHub 后，芯粒自然成为"唯一运行时"下的一个 skill，长期更干净。

---

## 8. 结论

- 原方案是**合格的目标架构**，哲学与 AOS 原生 100% 对齐。
- 但它假设了一堆"要么是外部愿景、要么还没造"的部件（IMA/mistralrs/OpenClaw 调度/SadTalker/TOML 机制）。
- 真实落地路径：**文本链路现在就能跑**（ag2+OrchestrationChiplet+litellm+mem0），渲染部分按 Phase B/C 逐步补适配器。
- 下一步建议启动 **Phase A**（纯逻辑、零新依赖、可立即真跑），与 consolidation 同一"先有完整系统再动手"的打法。

> 本文件为规划文档，未改动任何运行代码。落地时按 Phase A→D 增量提交，每步 `git log -1` 核验 hash。
