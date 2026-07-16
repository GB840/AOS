# AOS 模型能力接入与借鉴可行性设计说明

> 目的：回答两个问题
> 1. **A**（怎么接）：模型能力如何真正接入 AOS —— 映射现有 FabricHub 适配器，而非新造 TOML 注册表。
> 2. **C**（借不借）：十大深度学习模型技术，哪些真能借鉴进 AOS、怎么借、哪些不借（避免过度工程）。
> 附带 **B**：capability → adapter 落地对照表。
>
> 定位前提（已核实）：AOS 是**编排内核**（FabricHub 单内核 + 芯粒隔离 + 能力路由），模型对它而言是「能力端点 / 被调度的外部服务」，不是它自己加载的进程。推理运行时（加载/卸载/互斥）属于 Ollama / llama.cpp / 云端，AOS 只负责「路由到能力」。

---

## §A 模型能力如何真正接入 AOS（不新造组件）

### A.1 现有扩展点（复用，不新建）

| 扩展点 | 文件 | 作用 |
|---|---|---|
| `MCPClientAdapter` | `src/kernel/plugins/mcp_client_adapter.py` | 连任意外部 MCP Server（JSON-RPC2.0 HTTP，stdlib only） |
| `FabricHub.register_mcp_server` | `src/kernel/.../fabric_hub.py` | 注册 MCP server，`AOS_MCP_SERVERS` 即接 |
| `brain_registration.py` | `src/core/brain_registration.py` | 注册引擎（已注册 openclaw/litellm/mem0/weknora/ima 等） |
| 能力广告机制 | 各 adapter `advertise()` | 适配器只声明自身 capabilities，FabricHub 只按能力调它 → **能力边界即权限边界** |
| 三级路由 | `capability.py` (`TIER_HIGH/MEDIUM/LOW/AUTO`) | 按 tier 优先 + 向低档级联（云端用不了就本地） |

### A.2 「模型即芯粒」的正确落地方式

不要写 `aos_model_registry.toml`。正确做法：

1. **每个模型包成一个 adapter / MCP server**，在其 `advertise()` 里声明它能提供哪些 `capability`（如 `screenshot_understanding`、`ui_element_detection`、`task_classify`）。
2. **注册进 FabricHub**：本地模型经 `MCPClientAdapter`（起一个本地推理 MCP server，如 llama.cpp / Ollama 的 MCP 接口）；云端模型经现有 `brain_registration` 或 HTTP adapter。
3. **FabricHub 按 capability 路由 + 三级 tier 级联**：`capability=screenshot_understanding, tier=AUTO` → 先试本地 VLM（LOW），失败/超时升云端（HIGH）。这与 AOS 已落地的 ag2→ollama→heuristic 三后端降级链是同一套机制，无需新写。
4. **推理运行时职责外置**：模型权重加载/卸载/互斥锁归 Ollama / 云端负责；AOS 内核只持有「能力→端点」映射与路由策略。文档里那套「5 秒卸载 + 互斥锁 + 冷启动不加载」是 Ollama 的事，不是 FabricHub 的事。

### A.3 两层边界（务必分清）

```
┌─────────────────────────────────────────────┐
│ AOS 内核（FabricHub）                         │
│   路由 / 芯粒隔离(crash boundary) / 鉴权      │
│   能力注册 / 三级 tier 级联 / 结构化 Trace    │
└───────────────┬─────────────────────────────┘
                │ 按 capability 路由
┌───────────────┴─────────────────────────────┐
│ 推理运行时（Ollama / llama.cpp / 云端 API）   │
│   权重加载 / 卸载 / 互斥锁 / 显存管理         │
│   负责「模型进程」的生命周期                  │
└─────────────────────────────────────────────┘
```

---

## §B Capability → Adapter 落地对照表

| AOS 用例 | 模型技术 | 具体模型（已核实体量） | 部署层 | AOS 接入方式 | 状态 |
|---|---|---|---|---|---|
| 自然语言理解 / 工具调用生成 | LLM (Transformer) | ag2(云端) / Qwen2.5-1.5B Q4(~1.5G) | 云端 + 本地 ollama | `ag2_adapter` + ollama 兜底 | ✅ 已落地 |
| 自主反思 / 任务规划 | LLM | ag2 → ollama → heuristic | 同上 | `autopilot.py` 三后端降级 | ✅ 已落地 |
| 全双工语音（看/听/说） | VLM | MiniCPM-o 4.5 (9B, INT4~12GB显存) | 需 GPU / host | `MiniCPMOAdapter` VOICE_OMNI | 🔧 TODO(host, 需GPU) |
| 截图 / 文档理解 | VLM | MiniCPM-V-2 (Q4 ~1.8–2.0G) | 本地 ollama | 新增 `VLMAdapter`（MCP） | 📋 待建 |
| 视觉 UI 元素定位 | 轻量 CNN / VLM | MobileNetV3-small(2.54M) / VLM | 本地 | 区域二分类器 或 VLM | 📋 待建 |
| 记忆压缩 / trace 异常检测 | 自编码器 / VAE | 浅层 AE（CPU） | 本地 | `semantic_state.py` 增强 | 💡 建议 |
| 路由预测 / 置信估计 | DNN / MLP | 2–3 层 MLP（CPU） | 本地 | `router_predictor`（新模块） | 💡 建议 |
| 快速意图预判（重 LLM 前） | 轻量模型 | TinyLlama-1.1B / 单层 GRU | 本地 ollama | 前置分类器 | 💡 建议 |
| 任务依赖建模 | GNN | （不需） | — | `workflow_engine.py` DAG 已覆盖 | ❌ 不需 |
| 数据增强 / 对抗训练 | GAN | （暂不） | — | — | ❌ 暂不 |

---

## §C 十大模型技术「借鉴可行性研判」（核心）

逐条判定：已借用 / 建议借鉴 / 不借鉴。依据 AOS 现有子系统与九大理念，避免为外部愿景凭空造组件。

| 模型技术 | 判定 | 在 AOS 的真实落点 | 诚实理由 |
|---|---|---|---|
| **CNN** | 折叠进 VLM | 不单独引入 | 原始 CNN 做 UI 检测被 VLM 全覆盖；单独跑 CNN 是杀鸡用牛刀。需要「看图」时直接走 VLM 能力。 |
| **RNN / LSTM** | 暂不需要 | `_RunState` 状态机已覆盖 | 任务状态跟踪用确定性状态机（`autopilot.py:_RunState`）更可靠、可审计；仅在 trace 异常需序列建模时才考虑 LSTM。 |
| **Transformer** | 已借用 | LLM 核心（ag2 / ollama） | 已落地，无需新动作。可补：轻量 encoder 做任务分类辅助路由。 |
| **GAN** | 不借鉴 | — | 与 AOS 当前 scope 最不相关。仅未来做「对抗性红队测试 agent 策略」时可能用，非核心。 |
| **自编码器 / VAE** | **强烈建议** | `semantic_memory.jsonl` 压缩 + trace 异常检测 | 直接解 AOS「记忆无限增长」痛点；服务理念 2「失败即训练数据」的提炼环节。当前 `semantic_state.py` 只管锁，没管压缩。 |
| **GNN** | 不借鉴 | `workflow_engine.py` DAG 已覆盖 | 任务依赖用 DAG 拓扑排序足够；100 节点 GNN 是过度工程。多智能体规模上来后再评估。 |
| **LLM** | 已借用 | 核心能力 | 已落地（三级路由 + 三后端降级）。 |
| **VLM** | **建议扩展** | 截图 / 文档理解（不止语音） | 补 AOS「看不见」的短板。MiniCPM-o 已开语音通道，缺的是「图像输入 → 路由到 VLM」这条。 |
| **轻量模型** | **建议** | 重 LLM 前的快速预判 / 便宜路径 | 服务理念 5「能力即路由」——能用小模型/规则判断就不调大模型，省算力省延迟。 |
| **DNN / MLP** | **建议** | 路由预测器 + 置信估计 | 直接服务理念 6「量化置信」与「能力即路由」：从历史成功/失败 trace 学「哪条路对该任务成功率高」，并给输出打置信分。 |

### C.1 最该借的 3 个（按性价比排序）

1. **自编码器 → 记忆压缩 + 异常检测**：AOS 的 `semantic_memory.jsonl` 只增不减（理念 2 有 TTL 但无语义压缩）。用浅层 AE 把旧 trace 压成低维特征、丢弃噪声，既控体积又留可检索摘要；同时用重构误差做异常检测（某次执行偏离历史模式 → 触发审计）。纯 CPU、无外部依赖，契合 AOS 现状。
2. **DNN/MLP → 路由预测器 + 置信估计**：把历史 trace（任务特征 → 哪条 capability/engine 成功）训成小 MLP，替代当前「三级 tier 固定级联」的盲路由；并给 agent 输出打量化置信（理念 6 要求）。这是把「失败即训练数据」从口号变成可学习的路由策略。
3. **VLM（图像）→ 截图/文档理解**：AOS 当前完全「盲」——只能处理文本/代码。接 MiniCPM-V-2（本地 ollama，~2G）做截图理解，让工作流能读界面、读图片输入。MiniCPM-o 已铺好 VLM 适配器骨架，复用即可。

### C.2 明确不借的（避免过度工程）

- **GNN**：`workflow_engine.py` 的 DAG 依赖已够；GNN 在 <100 节点场景是杀牛刀。
- **GAN**：与 AOS 编排/记忆核心无关；红队测试是远期可选，不是现在。
- **原始 CNN / 独立 RNN**：分别被 VLM、确定性状态机覆盖，单独引入是重复建设。

---

## §D 落地优先级建议

| 优先级 | 动作 | 对应章节 | 依赖 |
|---|---|---|---|
| P0 | 接 VLM 图像输入（MiniCPM-V-2 via 新增 VLMAdapter/MCP） | §B / §C.1-3 | 本地 ollama 或 GPU |
| P1 | 自编码器压缩 `semantic_memory` + 异常检测 | §C.1-1 | `semantic_state.py` 增强，纯 CPU |
| P1 | DNN/MLP 路由预测器 + 置信估计 | §C.1-2 | 需先有足量历史 trace（当前已在落） |
| P2 | 轻量模型前置分类器（重 LLM 前预判） | §C.1-3 | 本地 ollama 小模型 |
| 不排期 | GNN / GAN / 原始 CNN / 独立 RNN | §C.2 | — |

> 前提待拍板：文档假设「8G 无 GPU 全本地」与 AOS 已定 MiniCPM-o 4.5（9B，需 GPU）语音后端矛盾。先确认部署机器有无 GPU、语音走本地还是云端，再定 P0 的 VLM 是本地还是云端 API。

---

## 附：已核实的模型体量（避免文档数字偏差）

- MiniCPM-V-2（~3B 参数，非 "2B"）：Q4_K_M ~1.96GB / Q4_0 ~1.77GB（HF gguf）。
- Phi-3-mini：3.8B（微软官方），Q4 ~2.2GB —— 非 1.5B 同档。
- SqueezeNet：float 4.73MB / TFLite 5.0MB（<5MB 属实）。
- MiniCPM-o 4.5：9B，INT4 需 ~12GB 显存（跨 GGUF ~8.3GB），官方「需 GPU」。
- MobileNetV3-small 2.54M；Qwen2-VL-2B 为正确命名（v1 的 Qwen-VL 是 7B）。

---

## §E 已落地记录（2026-07-16，用户确认「当前无 GPU」）

用户拍板：**P0（VLM 图像输入）+ P1（自编码器记忆压缩）都落地**；并确认**当前主机无 GPU**。

### E.1 无 GPU 决策的后果（明确写下，免得绕回老路）
- 文档原假设的「8G 无 GPU 全本地」对 VLM 成立 → **VLM 默认走云端视觉 API**（OpenAI 兼容 `/v1/chat/completions` 带 image_url），本地 ollama MiniCPM-V-2 留作未来有 GPU / CPU 慢速兜底。
- AOS 已定的全双工语音后端 **MiniCPM-o 4.5（9B，需 GPU）当前跑不了** → 该语音能力 `open_realtime_session` 仍为 TODO(host)，待有 GPU 或接云端 WS 再补。**不因此造本地推理运行时**。
- 这印证了 §A 的核心判断：AOS 是**编排内核**，模型是它的「能力端点」；模型加载/卸载/互斥属于 Ollama/云端，AOS 只负责路由到能力（复用现有 FabricHub 适配器契约，未新造 TOML 模型注册表）。

### E.2 已建代码（均已真跑测试，非纸面）
| 项 | 文件 | 状态 |
|---|---|---|
| VISION_UNDERSTAND 能力 | `src/core/fabric/capability.py` | 已加枚举 + `ENGINE_CAPABILITY_MAP`/`ENGINE_TIER` 加 `vlm` |
| VLMAdapter（云端优先 / 本地 ollama 兜底，三级诚实 health） | `src/core/fabric/adapters/vlm_adapter.py` | 新建，复用 MiniCPM-o 骨架 |
| 注册到 FabricHub | `src/core/fabric/adapters/__init__.py` + `src/kernel/plugins/fabric_hub.py` `_ADAPTERS` | 适配器总数 19→20，`vision.understand` 已 advertise |
| VLM 单元测试（mock transport，无网） | `tests/test_vlm_adapter.py` | 9 项全过 |
| 自编码器记忆压缩 + 异常检测 | `src/kernel/memory_compression.py`（TextVectorizer TF-IDF + Autoencoder numpy + MemoryCompressor 非破坏写 sidecar） | 新建，纯 CPU、仅依赖 numpy |
| 记忆压缩单元测试 | `tests/test_memory_compression.py` | 5 项全过（含离群 trace 被标记） |
| 调用入口 | `compress_semantic_memory()` + `python -m kernel.memory_compression --path ...` | 非破坏，原始 JSONL 不动 |

### E.3 验证结论（真跑，不编）
- `FabricHub.resolve_engine('vision.understand')` 在当前沙箱（无 key / 无视觉模型）诚实返回 `None`；配置 `VLM_API_KEY` 后走云端档、配本地 ollama 视觉模型走本地档。
- `MemoryCompressor` 在合成语料（25 条同质 trace + 1 条离群）上：AE 收敛（重构误差<0.05）、旧条目压成 8 维码、离群条被 95 分位阈值标记为异常。
- 两项共 13 个单测全绿。

### E.4 仍未排期（与 §C.2 一致，不过度工程）
- DNN/MLP 路由预测器：等历史 trace 更足再上（当前 `semantic_memory.jsonl` 已有结构化记录，是未来训练原料）。
- GNN / GAN / 原始 CNN / 独立 RNN：不借。
