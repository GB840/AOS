# AOS × Open Notebook × 短剧智能体 集成架构 Spec

> 目标：把「资料 → 60 秒科普视频 → 短剧素材」做成 AOS 插件总线上的全自动流水线。
> 本文是 **Phase 0 设计文档**，不含业务码；落地顺序见第九章。
> 事实基准：2026-07-14 WebSearch 核实（NotebookLM Short Video Overviews / Open Notebook API）。

---

## 一、事实基准（已核实，避免引用错模型）

| 外部能力 | 真实状态 | 备注 |
|---|---|---|
| NotebookLM Short Video Overviews | ✅ 2026-06-30 上线，~60s 竖版，Nano Banana 2 Lite（Gemini 3.1 Flash-Lite Image）驱动 | 仅英文 / 付费优先 |
| NotebookLM Cinematic 格式 | ✅ 用 Gemini 3 + **Nano Banana Pro** + **Veo 3** 三模型栈 | **Nano Banana Pro 真实存在**，只是服务于 Cinematic 而非 Short |
| Open Notebook (`lfnovo/open-notebook`) | ✅ MIT，最成熟开源替代，含完整 REST API（5055 端口）+ Swagger `/docs` | 16+ AI 提供商，可本地 Ollama |
| AOS 现有视频生成 | ✅ `vimax`(Gemini2.5+Veo+Seedance) / `pixelle` / `comfyui` / `open_montage` | 在 `src/skills/`（legacy 栈），需迁/挂到 FabricHub |

**结论**：AOS 不缺「视频渲染后端」，缺的是「资料→脚本」前端。Open Notebook 正好补这块，且完美契合 AOS「万物为我所用」的芯片粒接入模式。

---

## 二、AOS 现有底盘（已具备，直接复用）

| 模块 | 位置 | 在本流水线里的角色 |
|---|---|---|
| FabricHub 统一内核 | `kernel/wiring.build_fabric_hub` | 路由 / 调用 / 健康检查 / run_task |
| OrchestrationChiplet | `core/fabric/orchestration.py` | 多步流水线执行器（逐 step 上一步输出作下一步入参） |
| ag2 规划器 | `adapters/ag2_adapter.py` | 长任务分镜脚本规划（自动降级 heuristic） |
| 语音芯粒 | `voice_chiplet.py` / `tts_adapter.py` | 旁白 TTS + 可选语音交互 |
| 人设配置 | `persona.py` + Companion | 视频「 narrator / 伙伴人设」可配置 |
| MCP 客户端适配器 | `adapters/mcp_client_adapter.py` | 接入任意外部 MCP Server（参考范式） |
| 记忆 | `mem0_adapter.py` + Companion 双域 | 跨任务记忆素材/偏好 |
| HTTP 服务 | `http_server.py` | `/api/*` 暴露能力与流水线 |

---

## 三、外部拼图：Open Notebook（能力 + API 形态）

- **部署**：Docker `lfnovo/open-notebook:v1.3.1`（或 `v1-latest-single`），UI 8502 / API 5055。
- **认证**：所有请求 Header 带 `Authorization: Bearer <API_TOKEN>`（Settings → API Keys 生成）。
- **核心端点**（以运行实例 `/docs` Swagger 为最终准，不同版本路径略有差异）：

| 端点 | 用途 |
|---|---|
| `POST /api/notebooks` | 建笔记本 |
| `POST /api/sources`（或 `/api/notebooks/{id}/sources`、`/api/sources/upload`） | 摄取 PDF/视频/音频/网页/Office |
| `POST /api/chat/execute` | 上下文感知对话（带源引用） |
| `POST /api/search` | 全文 + 向量检索 |
| `POST /api/transformations` | 摘要 / 提取 / 结构化转换 |
| `POST /api/podcasts/generate` | 1–4 人播客生成（可先出脚本再出音频） |
| `POST /api/credentials` + `/discover` + `/register-models` | 配 AI 提供商（Ollama/DeepSeek/OpenAI…） |

---

## 四、集成架构（分层 + 数据流）

```
[用户 / 短剧编导智能体]
      │  上传资料(URL/PDF/视频) 或 输入主题
      ▼
[AOS 交互层]  companion / living-home / 短剧agent UI
      │  POST /api/pipeline/video-overview
      ▼
[AOS 插件总线 FabricHub]
      │  route → invoke_engine → run_task(planner=ag2)
      ▼
┌──────────────────────────────────────────────────────────┐
│ OrchestrationChiplet（多步流水线，逐跳故障隔离）          │
│  step1  doc.ingest      → Open Notebook 适配器            │
│  step2  doc.transform   → Open Notebook（摘要/大纲）      │
│  step3  media.script    → ag2 + inference.llm（分镜脚本） │
│  step4  media.image     → agnes / vimax / pixelle（逐镜） │
│  step5  media.video     → vimax(Veo) / comfyui / pixelle  │
│  step6  media.render    → ffmpeg 本地进程（竖版MP4+旁白） │
│  step7  agent.short_drama → 短剧编导智能体（下游消费）    │
└──────────────────────────────────────────────────────────┘
      │
      ▼
[资源驱动层]  Open Notebook + Ollama/DeepSeek + vimax/pixelle + FFmpeg
      │
      ▼
[存储层]  IMA知识库 / .companion / 本地资产目录(out/video/)
```

---

## 五、能力映射表（AOS capability ↔ 实现方）

| AOS capability | 实现方 | 说明 |
|---|---|---|
| `doc.ingest` | Open Notebook `/sources` | PDF/视频/音频/网页/Office 摄取 |
| `doc.chat` | Open Notebook `/chat/execute` | 上下文感知对话（带引用） |
| `doc.transform` | Open Notebook `/transformations` | 摘要 / 提取 / 大纲 |
| `doc.podcast` | Open Notebook `/podcasts` | 1–4 人播客（可先出脚本） |
| `media.script` | `ag2_adapter` + `inference.llm` | 60s 分镜脚本（场景+旁白） |
| `media.image` | `agnes` / `vimax` / `pixelle` | 逐镜视觉素材 |
| `media.video` | `vimax`(Veo) / `pixelle` / `comfyui` | 单镜头生成 |
| `media.render` | `ffmpeg`（新增本地进程适配器） | 合成竖版 MP4 + TTS 旁白音轨 |
| `agent.short_drama` | 短剧编导智能体（下游） | 消费脚本/分镜做后续短剧 |

新增 capability 枚举：`DOC_INGEST / DOC_CHAT / DOC_TRANSFORM / DOC_PODCAST / MEDIA_VIDEO / MEDIA_RENDER`（在 `core/fabric/capability.py` 增补）。

---

## 六、接线方案：直接 REST 适配器（非 MCP 桥）

Open Notebook 暴露的是 **REST**，不是 MCP。两种接法：

- **方案 A（推荐）**：写 `adapters/open_notebook_adapter.py` 直接 REST 客户端，注册为 AOS capability。简单、可控、易 mock 测试。`health()` 探 `GET /api/notebooks` 带 token 判定 live。
- **方案 B**：把 Open Notebook REST 包一层 MCP server，再用现有 `mcp_client_adapter` 接。多一层无谓转发，否决。

→ 选 **方案 A**。适配器遵循既有 `_ADAPTERS` 注册表 + `InvokeRequest/InvokeResult` 契约 + 诚实降级（服务不可达 `live=False` 不谎报）。

---

## 七、流水线定义（OrchestrationChiplet steps 草案）

```text
steps = [
  {engine:"open_notebook", cap:"doc.ingest",    in:{"sources": <上传清单>}},
  {engine:"open_notebook", cap:"doc.transform", in_from:previous, in_key:"summary"},
  {engine:"ag2",           cap:"media.script",  in_from:previous, prompt:"把上面的摘要写成60秒竖版科普视频分镜：每镜{画面描述, 旁白台词, 时长}"},
  {engine:"agnes/vimax",   cap:"media.image",   in_from:previous, for_each:"shots"},   # 逐镜出图
  {engine:"vimax",         cap:"media.video",   in_from:previous, for_each:"shots"},   # 逐镜成片
  {engine:"ffmpeg",        cap:"media.render",  in_from:previous, out:"out/video/<id>.mp4"},
  {engine:"short_drama",   cap:"agent.short_drama", in_from:previous},                  # 下游素材
]
```

- 确定性多步已由 OrchestrationChiplet 真跑验证（上一步输出作下一步入参、逐跳故障隔离）。
- `media.script` 经 `hub.run_task(planner="ag2")` 接缝；无 ag2 自动降级 heuristic。
- 任一 step 失败：下游自动阻断（沿用 `test_pipeline_blocks_dependent_step_when_upstream_failed` 行为），并保留上游 data 不吞上下文。

---

## 八、诚实边界与主机部署前置

**沙箱做不了（写码 + mock 测即可）**：
- 装不了 Docker / Open Notebook；FFmpeg 未必存在；Ollama 本地模型需主机。
- 适配器用 `responses`/`unittest.mock` 注入假 HTTP 响应做单测；`health()` 诚实探本地 5055，探不到即 `live=False`。

**主机前置（用户执行）**：
```bash
# 1) 起 Open Notebook
docker run -d -p 8502:8502 -p 5055:5055 \
  -v notebook_data:/app/data -v surreal_data:/app/surreal \
  -e OPEN_NOTEBOOK_ENCRYPTION_KEY="<随机串>" \
  lfnovo/open-notebook:v1.3.1
# 2) UI 里 Settings → API Keys 生成 token；Settings → 配 AI 提供商(Ollama/DeepSeek)
# 3) 装 ffmpeg（Windows: winget install ffmpeg）
# 4) AOS 环境变量
export AOS_OPEN_NOTEBOOK_URL="http://localhost:5055/api"
export AOS_OPEN_NOTEBOOK_TOKEN="<token>"
```

---

## 九、分阶段实施计划

| Phase | 内容 | 交付 | 沙箱可验度 |
|---|---|---|---|
| **0（本次）** | 集成架构 spec | 本文 | 纯文档 |
| **1** | `open_notebook_adapter.py` + capability 枚举 + 注册 + `health()` + 单测(mock) | 适配器芯粒 | ✅ 写码+mock 全过 |
| **2** | `ffmpeg` 渲染适配器（`media.render`）+ 流水线 steps 定义 + 编排单测 | 可跑编排骨架 | ⚠️ 渲染需主机 ffmpeg |
| **3** | companion living-home 加「🎬 生成科普视频」入口 + `POST /api/pipeline/video-overview` | UI + API | ✅ 路由/mock 可验 |
| **4** | 短剧编导智能体 handoff（step7 接消费端） | 端到端闭环 | ⚠️ 取决于短剧agent 现状 |

> 下一步（Phase 1）等你拍板即开工：先建 Open Notebook 适配器芯粒，沙箱可写码 + mock 单测，主机配好 token 后即真连。

---

## 十、配置落点（计划内，供实现参考）

- `core/fabric/capability.py`：补 `DOC_*` / `MEDIA_VIDEO` / `MEDIA_RENDER`。
- `core/fabric/adapters/open_notebook_adapter.py`：新建，遵循 `_ADAPTERS` 注册 + 契约。
- `core/fabric/adapters/ffmpeg_adapter.py`：新建，封装本地 `ffmpeg` 合成（竖版 9:16 + 旁白音轨混流）。
- `kernel/plugins/fabric_hub.py`：`_ADAPTERS` 追加两适配器。
- `core/fabric/http_server.py`：加 `POST /api/pipeline/video-overview`。
- `src/core/fabric/companion.py`：living-home 加入口按钮 + 调用。
- `tests/test_open_notebook_adapter.py` / `test_ffmpeg_adapter.py`：mock HTTP / mock subprocess。
