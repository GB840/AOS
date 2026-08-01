# 生命体操作系统白皮书 · 外部引用核验表

> 核验人：AOS Agent　核验方式：WebSearch 逐项交叉检索（两轮）
> 核验日期：**2026-07-26**
> 铁律：白皮书里凡出现外部项目名、版本号、星标数、许可证，必须先核实再落笔。本表是白皮书 v2 的事实底座。

---

## 判定口径

| 等级 | 含义 | 处置 |
|---|---|---|
| 🟢 真实可用 | 项目真实存在、许可证允许我们的用法 | 白皮书保留，标 🔧 复用 |
| 🟡 真实但需修正 | 项目存在，但白皮书里的数字/描述/适用范围有误 | 改写描述后保留 |
| 🟠 许可证陷阱 | 项目存在，但许可证挡商用 | 降级为 opt-in，另找主用方案 |
| 🔴 描述不符 / 存疑 | 搜不到、或搜到的与描述对不上 | 从白皮书删除或替换 |

---

## 一、🟢 真实可用（可直接复用）

| 项目 | 核验结论 | 许可 | 白皮书用途 |
|---|---|---|---|
| **MCP 2026-07-28 无状态规范** | 真实。Anthropic 规范修订，移除 handshake/session，请求自携带协议版本，header-based 路由 | 开放规范 | L7 粒子间通信协议 |
| **LocalAI** | 真实。OpenAI 兼容的本地推理网关，支持 llama.cpp / whisper / diffusers 多后端 | MIT | L1 肉体层本地算力 |
| **CLIProxyAPI**（router-for-me/CLIProxyAPI） | 真实。把各家 CLI 版模型统一成 OpenAI 兼容端点 | 开源 | L1 外部算力聚合 |
| **AgentENV** | 真实。Agent 运行环境隔离/沙箱 | 开源 | L7 粒子隔离参考 |
| **openship** | 真实。Agent 编排/投递 | 开源 | L5 演进层参考 |
| **nanobot**（nanobot-ai/nanobot） | 真实。轻量 MCP agent 运行时 | 开源 | L7 粒子运行时候选 |
| **Cindy** | 真实。本地语音助手项目 | 开源 | 语音子层参考 |
| **Vosk** | 真实。纯离线 STT，支持中文小模型 | Apache-2.0 | 语音子层 STT 主用 |
| **plasma-ai/fractal** | 真实。分形式 agent 组织实验 | 开源 | L7 分形集群参考 |
| **PhyAgentOS** | 真实。具身/物理 agent OS 研究项目 | 开源 | L1 肉体层参考 |
| **Octop**（TencentCloud） | 真实。腾讯云开源 agent 编排 | 开源 | L5 编排参考 |
| **broomva/life** | 真实。个人生活自动化 agent | 开源 | L4 精神层参考 |
| **openKylin AgentOS SIG** | 真实。openKylin 社区 Agent OS 兴趣小组 | 社区组织 | 生态对齐 |
| **video-shotcraft** | 真实。分镜/视频生成工具链 | 开源 | L6 虚实交互产出 |
| **dg-ai-notes** | 真实。AI 笔记/知识沉淀 | 开源 | L2 记忆层参考 |

---

## 二、🟡 真实但白皮书描述需修正

| 项目 | 白皮书原描述 | 核验真相 | 修正动作 |
|---|---|---|---|
| **AgentENV** | "2.7k 星" | 核验时约 **1.4k** 量级 | **删掉具体星标数**。星标是流动值，写进白皮书就是给自己埋雷 |
| **CLIProxyAPI** | "45k 星" | 源仓 router-for-me/CLIProxyAPI 约 **32k** 量级 | 同上，删数字 |
| **LocalAI v4.4.0** | 锁死版本号 | 版本持续滚动 | 改为"核验日（2026-07-26）主线版本"，不锁死 |
| **turbo-fieldfare** | 当通用本地推理写 | 实际**仅 Apple Silicon**，且绑定 Gemma-4 专用路径 | 加硬性适用条件标注，Windows/Linux 主机不可用 |

---

## 三、🟠 许可证陷阱（挡商用）

| 项目 | 陷阱 | 影响 | 处置 |
|---|---|---|---|
| **Fish Speech** | 代码开源，但**模型权重是 CC-BY-NC-SA-4.0，禁止商用** | 生命体OS 若走单创OS 的商业化路线，用其权重 = 侵权 | ① 主用方案换成商用友好的 **Piper（MIT）/ edge-tts / Kokoro**；② Fish Speech 降级为 `opt-in` 非商用场景，代码里加许可证门控提示 |

> 这一条是本次核验最有价值的发现。白皮书原文把 Fish Speech 当默认 TTS 写进 L1 肉体层，直接放行会在商业化那天炸掉。

---

## 四、🔴 描述不符 / 存疑（必须删或换）

| 项目 | 白皮书原描述 | 核验真相 | 处置 |
|---|---|---|---|
| **Mobius** | "全球首个自进化开源 Agent OS" | 搜到多个同名项目：AaronGoldsmith 的对抗蜂群编排器、lonexreb 的 ML 实验、hamzamerzic 的自构建代理、mobius-style（AGPL 治理）。**没有一个匹配"全球首个自进化 Agent OS"** | **删除该表述**。若要引"自构建代理"理念，改引 hamzamerzic/Mobius 并如实描述为个人实验项目 |
| **sifta-living-os** | 当同类"生命体 OS"对标 | 仅在 HuggingFace 找到 `georgeanton/sifta-living-os`，充满 "AGI-Class Organism" 等艺术化宣称，非工程仓库形态 | **删除**。不作为对标，最多作为"概念艺术参照"脚注 |
| **constitutional-agent-governance** | 当宪法治理层引用 | 未精确命中该 repo 名。近似真实项目：**acgs-ai/acgs-lite（宪法式 agent 治理）**、arifOS | **替换**为 acgs-lite。⚠️ **许可证已于 2026-07-25 实测更正**：本文早前写 AGPL-3.0 系凭检索预判，克隆源码后逐字复核 `vendor/acgs-lite/LICENSE` 为 **Apache-2.0**（全文无 "Affero" 字样，`grep -ci affero LICENSE` = 0），附注 "Commercial licensing is available for proprietary or SaaS embedding"。详见 §六 |

---

## 五、核验带来的结构性结论

1. **白皮书里 20 个外部引用，16 个真实、4 个有硬伤。** 硬伤率 20%，全部集中在"最能唬人的那几个名字"上（全球首个、生命体 OS、宪法治理）——这正是编造/夸大最容易藏身的地方。
2. **星标数一律不写进白皮书。** 它是流动值，写死就等于自埋定时炸弹，且一旦被人发现夸大，整份文档的可信度归零。
3. **许可证必须逐项标注，且区分「代码许可」与「权重许可」。** Fish Speech 就是典型：代码能用、权重不能商用。
4. **凡"全球首个 / 唯一 / 最强"这类词，一律删。** 白皮书 v2 不使用任何无法被 URL 佐证的最高级形容。

---

## 六、许可证实测清单（vendor/ 逐项复核，2026-07-25）

> 铁律：许可证不凭记忆，克隆源码后逐字读 `vendor/*/LICENSE` 再落库。本次 8 个组件全部实测。

| 组件（vendor/） | 实测许可 | 处置 | 复核命令 |
|---|---|---|---|
| acgs-lite | **Apache-2.0**（附商用授权提示） | ✅ 可引码；SaaS 嵌入建议走商用授权洽谈，代码层面借鉴宪法治理 | `grep -ci affero vendor/acgs-lite/LICENSE` = 0 |
| plasma-ai-fractal | **Apache-2.0** | ✅ 可引码（分形派生理念参照） | `head vendor/plasma-ai-fractal/LICENSE` |
| nanobot | **Apache-2.0** | ✅ 可引码（MCP agent 编排参照） | `head vendor/nanobot/LICENSE` |
| video-shotcraft | **Apache-2.0** | ✅ 可引码（L6 分镜） | `head vendor/video-shotcraft/LICENSE` |
| LocalAI | **MIT** | ✅ 可引码（本地推理网关） | `head vendor/LocalAI/LICENSE` |
| AgentENV | **MIT** | ✅ 可引码（环境自治参照） | `head vendor/AgentENV/LICENSE` |
| CLIProxyAPI | **MIT** | ✅ 可引码（多模型代理） | `head vendor/CLIProxyAPI/LICENSE` |
| piper | **MIT** | ✅ 可引码（L6 TTS） | `head vendor/piper/LICENSE.md` |

**结论**：8 个 vendor 组件**无一 AGPL/GPL 传染许可**，均为 MIT / Apache-2.0（宽松）。
早前审计凭检索把 acgs-lite 判为 AGPL-3.0，实测证伪，已在 §四更正。
`vendor/` 已在 `.gitignore:293` 忽略（不入库、防体积膨胀），组件以"参照+opt-in 复用"方式使用。

**AGPL 传染仍需警惕的（非本次 vendor，仅列名单避免将来误引）**：mobius-style（AGPL-3.0）等 —— 一旦 link 进来整个生命体OS 被迫开源，只可读源借鉴。

商用友好白名单（可直接引码）：MIT / Apache-2.0 / BSD → 上表 8 项 + img2threejs、self-learning-skill、harness-engineering。
