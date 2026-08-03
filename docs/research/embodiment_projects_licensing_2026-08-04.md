# 肉体层外部项目许可证核验与处置（2026-08-04 核实版）

> 用途：用户评估一批 2026 年活跃的「生命体 OS 肉体层（embodiment）」外部项目——生物计算机 / 数字人 / 多机器人协同，
> 要求入库并对齐 AOS 外部开源项目处置铁律（MEMORY.md §十二：引入须 MIT/Apache-2.0，无 AGPL；
> 不能商用→只借鉴 / 能商用开源→能用就用 / 能商用但技术栈不兼容→借鉴优化）。
>
> **重要**：本文所有条目均已联网核实（WebSearch + WebFetch 直达 GitHub/LICENSE，2026-08-04）。
> 凡与用户原描述不符处，均在「核实纠正」中标注。凡许可证未确认成 MIT/Apache-2.0 的一律不得接入。

## 0. 总表（核实后）

| # | 项目 | 真实地址 | 协议 | 核实状态 | 处置分类（§十二） |
|---|------|----------|------|----------|-------------------|
| 1 | SoulX-FlashHead | github.com/Soul-AILab/SoulX-FlashHead | **Apache-2.0** | ✅ LICENSE 直达取证 | 能用就用（轻量实时） |
| 2 | SoulX-FlashTalk | github.com/Soul-AILab/SoulX-FlashTalk | **Apache-2.0** | ✅ badge+搜索取证 | 能用就用（重实时） |
| 3 | SoulX-LiveAct | github.com/Soul-AILab/SoulX-LiveAct | **Apache-2.0** | ✅ org badge+HF base | 能用就用（小时级） |
| 4 | 美团 LongCat-Video-Avatar | github.com/meituan-longcat/LongCat-Video | **MIT** | ✅ HF model card+多源 | 能用就用（高质量视频生成） |
| 5 | OmniRT | github.com/datascale-ai/omnirt | **MIT** | ✅ README+LICENSE 直达 | 能用就用（统一推理运行时） |
| 6 | OpenTalking | github.com/datascale-ai/opentalking | **Apache-2.0** | ✅ org badge | 能用就用（数字人全栈编排） |
| 7 | M-Robots OS | atomgit.com/m-robots | **Apache-2.0**（OpenHarmony 底座） | ✅ 多源确认 | 借鉴优化（桥接，非代码依赖） |
| 8 | CL1 / Cortical Labs | cortical.io / Cortical Cloud | **商业闭源** | ✅ 商用硬件+付费 API | 只借鉴（实验探针，永不进生产） |

**核心结论**：除 CL1 外，全部开源候选均满足 MIT/Apache-2.0 铁律，可依法依规「能用就用」或「借鉴优化」。
许可证卡点已解除——之前未确认许可证的 SoulX 系列与 OmniRT 现已取证为 Apache-2.0 / MIT。

---

## 1. SoulX 系列（Soul-AILab，统一 Apache-2.0）

Soul AI Lab（Soul App 旗下）2026 年连续开源数字人模型家族，GitHub org 全部仓库均为 Apache-2.0。

### 1.1 SoulX-FlashHead（最轻，优先）
- **协议**：Apache-2.0（GitHub LICENSE 文件 + 仓库 badge 双确认）。
- **真实能力**：1.3B 参数的实时流式 talking-head 框架。Lite 版单张 RTX 4090 达 **96 FPS / 3 路并发 25+ FPS**；Pro 版单 RTX 4090 约 10.8 FPS，双 RTX 5090 实时 25+ FPS。Oracle-Guided 双向蒸馏 + TACC 8 秒音频缓存，解决长时身份漂移。
- **用途对准**：消费级显卡上的轻量实时数字人头部——最契合我们「有 GPU 才升 Tier 1」的策略。
- **核实纠正**：用户原说「96 FPS」属实；原把 FlashHead/LiveTalk/LiveAct 混称，实际是三个独立仓库。

### 1.2 SoulX-FlashTalk（14B，重实时）
- **协议**：Apache-2.0（badge + 搜索确认）。
- **真实能力**：14B，首字延迟 **0.87s**，8×H800 节点 32 FPS；单卡需 64G+ 显存。
- **用途对准**：高质量实时数字人，但显存门槛高，排 FlashHead 之后。

### 1.3 SoulX-LiveAct（小时级无限时长）
- **协议**：Apache-2.0（org badge + HuggingFace base model card 均标 Apache-2.0）。
- **真实能力**：Neighbor Forcing + ConvKV Memory，2×H100/H200 → 20 FPS，支持「无限时长」生成；消费级 RTX 4090/5090 经 FP8 KV offload 可跑。延迟低至 0.94s。
- **核实纠正**：有第三方文章称「商用前需联系官方确认」，但仓库与模型卡均为 Apache-2.0——属 Apache-2.0 正常商用自由，仅团队礼貌性提示。接入前按 Apache-2.0 正常标注即可，无需额外授权。

---

## 2. 美团 LongCat-Video-Avatar（MIT）

- **协议**：MIT License（HuggingFace 模型卡 + 多个二手源一致确认；权重与推理代码均 MIT）。
- **真实能力**：音频驱动数字人视频生成（AT2V / ATI2V / 视频续写），Whisper-Large 音频编码器驱动唇形。DMD2 蒸馏 8 步，10 秒视频在 A800 上约 1 分钟生成。**注意：它是视频生成，非实时交互**——单 A800 跑 82 秒片段约 1 小时。
- **用途对准**：高质量内容生成（带货视频、课程讲师、虚拟客服视频），**不是实时陪伴载体**。用户原描述「商用就绪、聚焦唇形同步和多人互动」属实，但别误当实时交互层。
- **核实纠正**：用户原给的「13.6B DiT」在搜索中未精确复现参数；实际 LongCat-Video-Avatar 1.5 是基于 LongCat-Video 基础模型的音频驱动头像模型，MIT 属实。

---

## 3. OmniRT（MIT，统一多模态推理运行时）

- **协议**：MIT License（README「📄 许可证」章节逐字声明 + 根目录 LICENSE 文件双确认）。
- **真实能力**：数字人链路优先的多模态生成推理框架。统一请求契约（GenerateRequest/GenerateResult/RunReport）；跨后端（CUDA / Ascend 910B / cpu-stub）同一份请求可校验与执行；覆盖 talking avatar / TTS / 角色资产 / 后处理。CLI + Python API + FastAPI 三入口。当前主线验证 FlashTalk / FlashHead / LiveAct / CosyVoice / SenseVoice / SoulX-Podcast。
- **用途对准**：作为数字人管线的「统一推理运行时」，屏蔽底层模型差异——对应我们策略里「用 OmniRT 统一多模态推理运行时」。需 GPU。
- **关联**：OpenTalking（datascale-ai/opentalking，**Apache-2.0**）是工业级数字人全栈编排框架（LLM/STT/TTS/WebRTC/打断/记忆），可插拔 OmniRT 跑高质量模型。两者同源（中科大 Jun Yu 团队），协议均合规。

---

## 4. M-Robots OS（Apache-2.0，但技术栈不兼容 → 借鉴优化）

- **协议**：Apache-2.0（基于开源鸿蒙 OpenHarmony，微内核，Apache-2.0；多源确认「核心代码完全开放、无商用授权限制」）。
- **真实能力**：深开鸿牵头、捐赠开放原子开源基金会的分布式异构多机协同机器人 OS。六大能力：积木式框架 / 混合部署 / M-DDS 低延时协同（音视频时延 ~4ms，比 Fast-DDS 降 42%）/ 硬件能力共享 / AI 原生（多智能体自主协同）/ 中间件兼容（ROS1/ROS2/Dora-rs，迁移成本降 80%）。中断/任务切换时延 ≤1μs。
- **处置（§十二 第 3 类）**：协议合规（Apache-2.0），但它是 **OpenHarmony 实时 OS（C/C++/rust 栈）**，与 AOS 的 Python/FabricHub 栈不同源 → **借鉴优化，不当代码依赖，只做桥接（subprocess / bridge）**。其「AI Agent 多机自主协同」理念与我们的 OPC 五岗 + 分形架构有共振，可借鉴其协同调度思想优化自身架构，而非引入其二进制。
- **核实纠正**：用户原说「直接采用」「当核心依赖」——与本铁律冲突。修正为 opt-in 桥接、排肉体层最后。

---

## 5. CL1 / Cortical Labs（商业闭源 → 只借鉴）

- **协议**：**商业闭源**。CL1 是商用生物计算机硬件（$35,000/台，批量 $20,000）；Cortical Cloud 是付费远程 API（GitHub 有 SDK 但服务需授权）。
- **真实能力**：集成约 **80 万**（用户原说 20 万，已纠正）活体人类神经元，59 电极亚毫秒交互；神经元寿命约 6 个月；需每日更换脑脊液、恒温恒气生命支持。
- **处置（§十二 第 1 类）**：不能商用（天价 + 半年换脑 + 违背母纲「终身陪伴 / 零费用」）→ **只借鉴，绝不接入生产依赖**。仅允许通过 Cortical Cloud 做「生物基底能否做决策回路」的科研探针，明确标注为实验性。
- **核实纠正**：① 神经元数是 80 万非 20 万；②「24.5 万澳元政府资助」查无此说，实为 2023 年 1500 万美元风投（维港投资领投）；③ $35k / 6 个月寿命属实。

---

## 6. 处置分类（对齐 §十二 铁律）

**原则三句照执行**：
1. **不能商用的 → 只借鉴**：CL1（商业闭源）。已定。
2. **能商业化开源 → 能用就用**（均 MIT/Apache-2.0，技术栈兼容则直接集成/复用）：
   - SoulX-FlashHead（Apache-2.0，轻量实时，首选接入）
   - SoulX-FlashTalk（Apache-2.0，重实时）
   - SoulX-LiveAct（Apache-2.0，小时级）
   - LongCat-Video-Avatar（MIT，高质量视频生成）
   - OmniRT（MIT，统一推理运行时）
   - OpenTalking（Apache-2.0，数字人全栈编排，可选）
3. **能商用但技术栈不兼容 → 借鉴优化**：M-Robots OS（Apache-2.0 但 OpenHarmony 实时 OS，与 Python/FabricHub 不同源）→ 仅桥接（subprocess），借鉴其多机协同调度思想。

**许可证卡点已解除**：原未确认许可证的 SoulX 系列（Apache-2.0）与 OmniRT（MIT）现已取证，全部过 MIT/Apache-2.0 铁律，无 AGPL、无 source-available 模糊项。

---

## 7. 接入层级（肉体层，全部 opt-in，非核心依赖）

> 对齐母纲「本地优先 / 8G 旧电脑可跑 / 零费用 / 陪伴老百姓」。这些项目都是**肉体层的外设增强**，
> 不是 AOS/单创OS 的核心依赖。核心永远是本地优先、零费用的语音陪伴。

- **Tier 0（默认，8G 电脑，零成本）**：方言语音陪伴。已有 MiniCPM-o 全双工 + Vosk 方言 ASR + edge_tts——这是「陪伴」核心载体，**不依赖上面任何重项目**。
- **Tier 1（消费级 GPU，opt-in）**：SoulX-FlashHead 1.3B（Apache-2.0，RTX 4090 实时）做轻量数字人头部；LongCat-Video-Avatar（MIT）做高质量视频内容生成（非实时）。
- **Tier 1b（更高显存，opt-in）**：SoulX-FlashTalk 14B / SoulX-LiveAct（小时级）；OpenTalking + OmniRT 做数字人全栈编排与统一运行时。
- **Tier 2（机器人/边缘硬件，opt-in）**：M-Robots OS 作桥接（subprocess），当「物理执行器」，不是 OS 本体。
- **Tier X（实验性，明确标注）**：CL1 的 Cortical Cloud 远程探针，只做科研验证，永不进生产依赖。

**对母纲/理念的呼应**：方言语音陪伴（Tier 0）才是真正对齐「主权归你永不收割 / 22 种方言平等 / 8G 电脑可跑」的首选载体；数字人/机器人降级为「有了再接」的增强，避免重算力背叛母纲。

---

## 8. 诚实备注

- 本文为**许可证与可用性核验 + 处置分类**，不是接入实现。实际接入（subprocess 桥接 / 模型权重下载 / GPU 部署）须另立任务，且须用户在自有 GPU 主机上实操（沙箱无 GPU）。
- SoulX-LiveAct 团队对商用有「联系确认」礼貌提示，但许可证为 Apache-2.0，依法可自由商用，仅需在产品中标明 Apache-2.0 出处。
- CL1 的「硅基类脑计算」替代方向（单晶体管模拟神经元、FinalSpark 降耗百万倍）属前沿探索，本文未展开，列入观察项。

---

## 9. Tier 0 方言语音陪伴封装落地（2026-08-04 补）

> 上文 §7 把 Tier 0 列为首选载体；本节记录它已从「散落组件」收口为**正式封装**，不再零敲碎打。

- 新增 `src/voice/companion.py` 的 `CompanionVoice`：本地优先、方言平等、断网可跑的统一语音通道。
  - **听**：`DialectASR` 方言真路由（funasr 覆盖 7 大方言 / vosk 覆盖普通话）→ 不可用诚实给落地命令、绝不冒充；默认 Vosk 本地 STT；云 API（百度/讯飞）仅 `cloud_asr=True` 时 opt-in 兜底，不挡默认。
  - **说**：`TTSAdapter` 引擎真探测（piper/kokoro 全离线 > edge_tts 免费需联网 > web_speech 浏览器兜底）；方言音色只映射**已核实**的——粤语→`zh-HK-WanLungNeural`、东北/中原/西南→`zh-CN-liaoning/shaanxi-XiaoniNeural`；吴/闽/客/赣/湘/晋 等 edge_tts 无真方言 voice，诚实退回默认，不冒充。
  - **诚实**：缺 TTS 模型时 `speak` 降级到 web_speech 兜底，保证「陪伴不中断」；`health()/capabilities()` 如实反映此刻可否断网跑，绝不误报。
- **修复真实缺陷**：`src/voice/__init__.py` 原硬依赖 `utils.config(pydantic_settings)`，缺依赖时整个 `voice` 包 import 崩溃（违反「一键装可跑」）；现默认只导 `CompanionVoice`，云版 `ASREngine/TTSEngine` 改为 try/except 包裹，不拖垮入口。
- **接线**：`src/core/fabric/http_server.py` 的 `/api/voice/tts` 与 `/api/voice/info` 已改走 `CompanionVoice`（方言音色 + 降级兜底 + 诚实能力清单生效）；`/api/voice/stt` 方言分支本就走 `dialect_asr`，与 `CompanionVoice.listen` 等价。
- **诚实分级**：**② 级全真**（代码 + 单测实证，`tests/test_companion_voice_real.py` 9 项全绿，不连外网、不 mock 体征）；沙箱实测 vosk 模型可用、本地链路真实跑通、静音诚实失败。
- **③ 级未验**：真人在方言下「说→听→想→说」全链路需主机真 LLM + 麦克风实测；沙箱无 GPU/音频设备，仅②级，不谎报。
