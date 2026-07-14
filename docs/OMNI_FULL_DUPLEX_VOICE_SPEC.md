# AOS 真全双工语音：选型 + 接入 Spec

> 依据用户 2026-07-15 铁律「任何技术/方案/软件选型先全网搜开源核实」产出。
> 本文所有事实均经 2026-07-14/15 全网搜证，并**纠正了此前错误记忆**：
> 之前记的"Moshi.cpp（Windows 二进制 + 9.7GB 权重）"是假的——Moshi 是 Kyutai
> 的 Rust/MLX 项目（Mac/iPhone 优先，**没有 C++ 版**），我把 whisper.cpp（纯 STT）
> 和 Moshi（全双工）搞混了。本 spec 一律以搜证为准。

---

## 0. 决策结论（B 已落地）

选 **MiniCPM-o 4.5**（OpenBMB/面壁智能 + 清华，MIT/Apache 开源）作为 AOS 全双工
全模态推理后端。适配器骨架已写入：

- `src/core/fabric/adapters/omni_minicpm_adapter.py`（`MiniCPMOAdapter`，`VOICE_OMNI`）
- `src/core/fabric/capability.py` 新增 `VOICE_OMNI = "voice.omni"`
- `adapters/__init__.py` + `fabric_hub.py _ADAPTERS` 已挂接

沙箱无 GPU、HF 被墙下不了权重，**真模型跑不了**；以下为代码层正确 + 主机验证路径。

---

## 1. 选型对照表（真实开源全双工候选，铁律搜证）

| 模型 | 机构 | 参量 | 原生全双工 | 全模态 | 端侧 / Windows | 许可 | 适合 AOS? |
|---|---|---|---|---|---|---|---|
| **MiniCPM-o 4.5** | OpenBMB（面壁+清华） | 9B | ✅ 原生，无需 VAD | 视/听/说/文 | Comni Win 一键包；INT4 12GB（RTX5070/4090） | MIT/Apache | ⭐ **最贴**：中文优先 + Windows + 视频生命体流水线 |
| **Moshi** | Kyutai | 7B | ✅ 原生 | 纯语音 | Mac/iPhone(MLX) 优先，Windows 弱 | CC-BY 4.0 | 纯语音最成熟（30K+ stars） |
| **PersonaPlex** | NVIDIA | 基于 Moshi 微调 | ✅ | 纯语音 + 角色/声音控制 | 同 Moshi | — | 多角色"生命体伙伴" |
| **Qwen2.5-Omni** | 阿里 | 7B | 部分 | 全模态 | 自托管 | Apache-2.0 | 备选 |
| **Mini-Omni** | 社区 | 0.5B | 部分 | 语音 | 任何设备 | MIT | 低门槛验证用 |

**关键架构事实（MiniCPM-o 4.5）**：端到端全模态——视觉 SigLIP-ViT(0.4B) +
音频 Whisper-Medium(0.3B) + LLM Qwen3-8B(8B) + 语音 Token 解码器(0.3B)。
**Omni-Flow 流式框架**：毫秒级时间轴统一所有流 + 时分复用，原生全双工、
**1Hz 自主决策是否发言**，无需外部 VAD。

**显存真相（诚实标注，避免再被简化误导）**：
- llama.cpp-omni 量化版：INT4 **12GB** 显存可跑全双工（RTX5070/4080/4090）。
- 官方 **PyTorch 全量**全双工：需 **~21.5GB / 24GB** 显存（GGUF ≠ PyTorch，
  全双工需官方 PyTorch 方案）。

---

## 2. 真实接入点（MiniCPM-o 4.5，铁律核实）

| 模式 | 端点 | 说明 |
|---|---|---|
| Chat Completions（半双工/轮次） | `POST https://api.modelbest.cn/v1/chat/completions` | OpenAI 兼容，`model:"MiniCPM-o-4.5"`，支持 text + image_url(base64)。公开测试 key：`sk-pQ8L2zF3XmR5kY9wV4jB7hN1tC6vM0xG3aD5sH2bJ9lK4cZ8`（可能变动，以官方 api.md 为准） |
| Realtime API（真全双工） | WebSocket `wss://localhost:8443/v1/realtime?mode=audio` | 本地 PyTorch 方案，自签证书需关 ssl 验证；`mode=chat` 轮次、`mode=audio&duplex=half` 半双工 |
| 免费云端 Realtime | 同 host `/realtime`（见官方 Realtime API Overview） | 全双工实时交互，无需 VAD |
| Comni 一键包（Windows） | `https://github.com/tc-mb/llama.cpp-omni/releases/latest/download/Comni-Setup-win64.exe` | 集成模型下载+环境+Demo，双击运行 |
| 开源 Demo 仓库 | `https://github.com/OpenBMB/MiniCPM-o-Demo` | 全栈代码，Linux/WSL2 可二次开发 |

本地 Python SDK：`model.as_duplex()` 切全双工，`model.as_simplex(reset_session=True)` 回退。

---

## 3. AOS 现状（复用基础）

- `src/core/fabric/voice_chiplet.py`
  - `ConversationStateMachine`：idle/listening/processing/speaking + 3s 打断窗口（barge-in）
  - `VoicePipeline`：STT → AOS 能力路由（默认接 `companion.handle_companion_message`）→ TTS 的**回合制**编排
  - 这是**轮次制**（听→想→说），全双工需从"回合"升级为"持续流 session"
- `src/core/fabric/adapters/`：stt/tts/litellm 等真实芯粒入口；本次新增 `omni_minicpm_adapter.py`
- `src/skills/omni_route.py`：**与 MiniCPM-o 无关**——它是写死的模型网关（231 家是占位假数据），别混淆

---

## 4. 接入架构（薄适配 + 不重造）

```
浏览器/前端 (麦克风+扬声器)
      │  WebSocket (方案① 流式基础已铺)
      ▼
AOS api/main.py  (/api/voice/omni 新端点, 已用 to_thread 包)
      │
      ▼
MiniCPMOAdapter (VOICE_OMNI)  ── 薄翻译层，绝不自研 Omni 模型
      ├─ invoke():       单次/回合契约 (chat / realtime_once)  ← 兼容现有 fabric 路由
      └─ open_realtime_session(): 持续流 generator, yield {text|audio|state|error}
      │
      ├─ cloud_api    → https://api.modelbest.cn/v1  (+ Realtime WS)
      ├─ local_comni  → Comni/llama.cpp-omni  (INT4, 12GB)
      └─ local_pytorch→ wss://localhost:8443/v1/realtime?mode=audio (~21.5GB/24GB)
```

**适配器已落地的接口**（沙箱验证通过）：
- `engine_id="minicpm_o"`、`advertise_capabilities()=[VOICE_OMNI]`
- `health()`：cloud 查 key、local 探活 `/health`，**诚实不谎报**
- `invoke({action:"chat"})`：真实 HTTP（OpenAI 兼容），沙箱无网返回 ok=False+真实错误
- `invoke({action:"realtime_once"})` / `open_realtime_session()`：真 WS 对接为
  **TODO(host)**，骨架已 yield 诚实 error 事件、不抛未捕获异常

---

## 5. 全双工升级方案（voice_chiplet 改造路线）

1. **复用打断状态机**：`ConversationStateMachine` 的 barge-in 逻辑直接复用。
   MiniCPM-o 原生全双工已支持随时插话——前端/适配器收到用户新音频即中断当前
   audio 流，无需自研 VAD。
2. **VoicePipeline 新增全双工模式**：用 `open_realtime_session()` 替换
   "STT→respond→TTS" 三步，改为单一 Omni 模型端到端持续流（音频进 → 文本+音频出）。
   非实时/低配场景仍走原轮次制（高低搭配）。
3. **前端 WS 桥接**：MiniCPM-o Realtime WS ↔ 浏览器麦克风/扬声器。方案①流式架构
   已铺好 SSE/WS 基础，复用即可实现"流式语音 + 逐字蹦字 + 随时打断"。

---

## 6. 端云合作降级链（对齐 AOS 第一性「云端用不了就本地」）

```
全双工 MiniCPM-o 可用
   ↓ 不可用（无 GPU / 服务挂 / key 过期）
轮次制 VoicePipeline：本地 whisper STT + AOS LLM(本地或云端) + kokoro/edge TTS
   ↓ 仍不可用
浏览器 Web Speech API 兜底（STT+TTS 全在端侧浏览器）
```
层层降级不崩；每一层 health() 如实反映可用性。

---

## 7. 主机验证步骤（需 GPU，沙箱做不到）

1. **部署模型**：装 Comni 一键包，或 `llama.cpp-omni`（INT4，12GB）；或 PyTorch 全量（21.5GB/24GB）。
2. **起服务**：暴露 `/health` + `/v1/realtime?mode=audio`（Comni 一键起；PyTorch 按官方 CookBook）。
3. **配置 AOS**：`AOS_MINICPM_MODE=local_comni` + `AOS_MINICPM_LOCAL_WS/HTTP` 指向服务。
4. **冒烟**：
   ```bash
   PYTHONPATH=src python -c "from core.fabric.adapters.omni_minicpm_adapter import MiniCPMOAdapter; a=MiniCPMOAdapter(mode='local_comni'); print('health=', a.health())"
   ```
   应打印 `health= True`。
5. **补全真对接**：按官方 Realtime API 协议实现 `open_realtime_session` 的
   send(用户音频)/recv(模型 text+audio) 循环 + barge-in 中断；`realtime_once` 复用同循环收满一回合。
6. **前端验**：浏览器开 `/api/voice/omni` WS，验流式全双工对话（边听边说、随时打断）。

---

## 8. 诚实边界（不弄虚）

- **沙箱限制**：无 GPU、HF 被墙下不了权重 → 真模型推理跑不了；本 spec + 适配器骨架
  仅保证**代码层正确**（语法 + 接口 + 降级路径已验证）。
- **TODO(host)**：`open_realtime_session` / `realtime_once` 的真 WebSocket 对接是
  留给主机（有 GPU + 有效服务/key）补全的部分；接口、事件类型、降级均已就绪。
- **未做实搜证的点**：云端 Realtime WS 的确切 host 路径以官方 Realtime API Overview
  为准（适配器已用 `CLOUD_BASE` 同 host `/realtime` 合理默认构造，env 可覆盖）。
