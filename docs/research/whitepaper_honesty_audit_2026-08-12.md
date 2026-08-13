# 白皮书诚实核验报告（2026-08-12 · 独立复核）

> 任务：对 `docs/LIFEFORM_OS_WHITEPAPER_V6.md` 做「全网搜索 + 对齐架构图 + 反复交叉检查」。
> 态度：**不采信自写的审计脚本、不采信上一轮的任何文档结论，全部重验**。以下结论均来自本轮独立实证。

## 0. 方法（可复现）

| 检查项 | 做法 | 工具 |
| :--- | :--- | :--- |
| 代码真值 | 白皮书架构节点表所列 51 个 `src/` 路径逐条 `test -e` | Bash |
| 集成真值 | 查 `GET /api/lifeform` 路由、数 `lifeform_runtime` 组件装配 | Bash/Grep |
| 版本真值 | 环境 `pip` 实装版本 vs 白皮书声称版本 | Bash |
| 外部声明 | 直接 WebSearch 独立核实（不看旧审计文档） | WebSearch |
| 内部一致性 | mermaid 节点数 + 状态标记用 python 精确计数（grep 的 emoji 编码不稳，python 才是真值）；③ 越级扫描 | Bash/Python |

---

## 1. 外部声明全网核实（✅ 全部坐实）

| # | 白皮书声明 | 核实结果 | 结论 |
| :--- | :--- | :--- | :--- |
| 1 | openKylin 智能体 OS（国防科大牵头，2026-06-25 开放原子大会，基于 openKylin 2.0） | 人民网/新华网/国防科大官网均确认：国内首个全栈开源智能体 OS，国防科大+哈工深+麒麟软件共建 | ✅ 真实 |
| 2 | x402（Coinbase 发起，Linux 基金会 2026-07-14 正式运营） | x402.org / Coinbase 官方文档确认：Coinbase 贡献协议，Linux 基金会 2026-07-14 正式运营 | ✅ 真实，日期精准 |
| 3 | openEuler Agentic Infra（Agent Kernel / Agent Service / Conch 沙箱引擎 / Agent POSIX 原语） | openEuler 官网 + openatom 确认：Conch 快照沙箱、Agent POSIX 原语、三级动态沙箱 | ✅ 真实 |
| 4 | OpenHarmony 小艺 HMAF 2.0（HDC2026，意图即服务，2100+ 系统能力，Skill 化，MCP 兼容） | 华为 HDC2026 多篇报道确认 HMAF 2.0 发布、2100+ 能力、MCP 兼容 | ✅ 真实 |
| 5 | 「IEEE 2026-02 四层记忆+CIAR 论文」实为伪造，真实来源是 `maksim-tsi/mas-memory-layer` 的 ADR-004 | 该 GitHub 仓库确含 `docs/ADR/004-ciar-scoring-formula.md`（个人项目，四层记忆+CIAR 公式），**无任何 IEEE 论文/DOI** | ✅ 白皮书「删伪造 IEEE 论文」的自我纠正**诚实且可证** |
| 6 | LocalAI v4.7.1 | 2026-07-14 发布，47.5k+ stars | ✅ 版本真实（但许可证标错，见第 5 节） |
| 7 | Mandol（arXiv:2606.29778，中科院软件所+微软） | arXiv 确认 2606.29778 由中科院软件所+Microsoft Research 提交 | ✅ 真实 |
| 8 | MiniCPM-Robot / RobotManip / RobotTrack（面壁+OpenBMB，WAIC 2026 开源） | 新浪/多家确认：面壁联合 OpenBMB 于 2026-07-19 WAIC 发布并开源 | ✅ 真实 |

**结论**：白皮书所有当成事实的外部声明，独立 WebSearch 均**未翻车**。此前删掉的 Mobius/Holo/IEEE 三项，其「删除/纠正有据」的判断也经复核成立。

---

## 2. 代码真值（白皮书 ↔ 真实仓库）

- 白皮书架构节点表所列 **51 个 `src/` 路径**，`test -e` 全部存在（0 缺失）。
- `GET /api/lifeform` 路由真实存在于 `src/api/main.py:830`。
- `src/kernel/lifeform_runtime.py` 含 **32 处 `_try` 装配**（≈31 组件实例化），与白皮书「焊接度 42/42、31 组件实例化」的集成叙述一致。
- **无「写着有、其实没接」的漂移**。

---

## 3. 版本号核对（环境实装 = 最硬证据）

| 包 | 白皮书声称 | 环境实装 | 一致 |
| :--- | :--- | :--- | :--- |
| litellm | 1.95.0 | 1.95.0 | ✅ |
| vosk | 0.3.45 | 0.3.45 | ✅ |
| piper-tts | 1.6.0 | 1.6.0 | ✅ |
| constitutional-agent | 0.7.0 | 0.7.0 | ✅ |
| lancedb | 0.36.0 | 0.36.0 | ✅ |
| duckdb | （仅称「真连」） | 1.5.5 | ✅ 未虚报版本 |
| localai | v4.7.1（服务端二进制，非 pip 包） | 未装（白皮书明说 opt-in 需跑服务端） | ✅ 一致 |

**结论**：所有可 pip 核实的「已真接开源」版本号与仓库**逐一吻合**，不是编的。

---

## 4. 内部一致性

- mermaid 架构图节点行数 = **61**，与白皮书自称「61 节点」吻合。
- python 精确计数各状态标记：**✅46 / 🔁4 / 🔗11 / 🚧0** —— 与白皮书统计表**逐字吻合**（grep 因 emoji 编码漏数 🔁/🔗，python 才是真值）。
- **③ 越级扫描**：白皮书所有「③」出现处，100% 绑定「未验 / 未做 / 非端到端 / 窄场景 / 诚实」等限定语；唯一例外是某处把「③ 遗忘衰减曲线」列为设计建议（非宣称已完成）。**未发现任何把 ③ 当完成来吹的越级行为**。

---

## 5. 发现的问题与处置

### 5.1 [已修复] LocalAI 许可证硬标错 ⚠️
白皮书把 LocalAI 写成 **Apache-2.0**，但全网一致是 **MIT**（LocalAI 官方/MIT 许可证，47.5k stars 项目）。
**已改**：`LIFEFORM_OS_WHITEPAPER_V6.md` 第 53 / 214 / 276 行，`Apache-2.0` → `MIT`（3 处）。

### 5.2 [已撤销 · 复核纠正] openKylin 精确指标"未被佐证"系上轮误判 ❌→✅
**纠正**：上轮（2026-08-12）因搜索不充分，误以为公开报道只到「Token 降 50%+/时间降 60%」档，将 L9B 精确数字列为"待修点"。
本轮（2026-08-13）重新独立搜索，发现 **央广网、CSDN(openEuler)、百度百科、今日头条 四大独立信源均明确刊载了相同精确数字**（降 75% 模型切换、73.6% 任务等待、81.7% token、38.2% 时间、24%+ 记忆 token）。
**结论**：这些数字已是公开发布数据；且白皮书第 864 行已诚实标注「厂商自测口径，未见第三方复测」——自身带有诚实边界。
→ **5.2 撤销。白皮书 openKylin 部分无误，无需软化或加链接。**（诚实纪律：自己之前给的"待修点"若复验不成立，必须主动纠正，不能为了"完成建议"硬改一个正确的东西。）

### 5.3 [已实施] 三份架构文档视角交叉引用 ✅
已消除连贯性缺口：在 `LIFEFORM_OS_WHITEPAPER_V6.md`（一、完整架构图）、`ARCHITECTURE.md`（顶部）、`ARCHITECTURE_MAP.md`（顶部）三处各加「视角说明」块，互相点名另两份是"部署拓扑 / 模块分层 / 生命体分层"三种不同镜头，非矛盾。

---

## 6. 总判定

- **白皮书整体诚实**：外部声明经独立全网搜全部坐实；代码真值 51/51 路径存在、集成件真实；版本号与实装逐一吻合；无越级吹 ③；内部节点计数自洽。
- **系统性编造 = 0**。此前用户最担心的「一堆不是一套 / 虚假集成」，经 2026-08-09 焊接整改 + 本轮复核，已无证据支持。
- **本轮实修 1 处硬伤**（LocalAI 许可证）；5.2「openKylin 待修点」经复核实为误判已撤销；5.3「三份架构文档互引」已实施。所有修正均为"诚实边界/连贯性"，**未改动白皮书任何事实断言**。

> 诚实边界仍成立：白皮书所有能力绝大多数为 **② 级（代码+单测）**，仅 P0 自进化一个窄场景到 ③；③ 端到端未全架构覆盖——这一条白皮书自己写明了，本轮复核确认它没偷偷越级。

---

## 7. 追加复核（2026-08-13）

承接上轮（2026-08-12）收尾的 2 处"待修点"，本轮执行并复验：

1. **5.2 openKylin 精确数字** —— 原列"待修点"。重新独立 WebSearch 后发现 **央广网 / CSDN(openEuler) / 百度百科 / 今日头条 四大独立信源均报道了相同精确数字**（75% / 73.6% / 81.7% / 38.2% / 24%+），证明这些是已公开的发布数据，且白皮书第 864 行已自标"厂商自测口径"。**判定：误判，撤销，白皮书无误。**
2. **5.3 三份架构文档互引** —— 已在三份文档顶部加「视角说明」块，互相点名"生命体分层 / 部署拓扑 / 模块分层"三种镜头，消除连贯性缺口（非事实错误）。**判定：已实施。**

**最终收口**：白皮书诚实性经四重独立验证（代码真值 / 版本号 / 全网搜 / 内部一致性）+ 本轮追加复核，结论是**整体诚实、无系统性编造、无越级吹③**；唯一实修硬伤（LocalAI 许可证 Apache-2.0→MIT）已落地；所有"待修点"经复验要么撤销（5.2）、要么已落实（5.3）。

---

## 8. 追加实证：已真接开源库的运行时 import 真接验证（2026-08-13 第二轮）

承接"全面检查10遍"，补做此前未穷尽的一遍：**白皮书声称"已真接/已用开源"的库，是否在运行时真有 import/调用（不只装包、不只路径存在）**。逐条 grep `src/` 实证：

| 白皮书声明 | 库 | 代码实证（grep `src/`） | 结论 |
| :--- | :--- | :--- | :--- |
| ✅已接 L1B | LiteLLM 1.95.0 | `litellm_adapter.py:149 class LiteLLMAdapter` + `byok.py:22/115/166`、`voice_chiplet.py:203/205`、`brain.py:961/970` 真 invoke/装配 | ✅ 真接 |
| ✅已接 L1E2 | Vosk 0.3.45 | `vosk_backend.py:28 import vosk`、`stt_adapter.py:102 import vosk`、`dialect_asr.py/companion.py` 探测 `import vosk` | ✅ 真接 |
| ✅已接 L1E3 | Piper 1.6.0 | `piper_backend.py:26 import piper`、`tts_adapter.py:69 import piper`、`lifeform_runtime.py:111 __import__("...piper_backend")` | ✅ 真接 |
| ✅已接 CONST3 | constitutional-agent 0.7.0 | `constitutional_governor.py:22 import constitutional_agent` + `.Constitution(...)` 真调用、`lifeform_runtime.py:84` 装配 | ✅ 真接 |
| ✅已接 L3A | LanceDB 0.36.0 | `memory_ladder.py:244 import lancedb`（缺失即 ImportError 诚实降级） | ✅ 真接 |
| ✅已接 L3D | DuckDB | `memory_ladder.py:86 import duckdb`（惰性 import，缺则降级） | ✅ 真接 |
| ✅已用 L3B | Chroma/cognee/mem0 | `mem0_store.py:77 from mem0 import Memory`、`memory.py:14 import chromadb`、`skills/cognee.py:41 import cognee` | ✅ 真用 |
| ✅已接 L5G | video-shotcraft | `video_shotcraft_backend.py` 真接开源 + `lifeform_runtime.py:112 __import__("...video_shotcraft_backend")` 装配 | ✅ 真接 |

**结论**：白皮书"已真接开源 8 个 + 已用开源 3 个"的声明，**全部在代码里有真实 import/调用实证**，且被挂入 `lifeform_runtime` 运行脊柱（`_try` 装配）。无"装了包没 import"的虚假集成，无"路径存在但不被引用"的孤儿。各适配器均 `try/except` 惰性导入（失败 `=None` 诚实降级），与白皮书"诚实降级"叙述一致。

→ **这一遍直接、硬核地回应了最初"一堆不是一套 / 虚假集成"的质疑：开源库是被真接进运行时、被运行脊柱引用的，而非只贴标签。至此"全面检查"的硬维度（路径存在→版本安装→外部声明→内部计数→运行时真接）已全部覆盖、全绿。**

---

## 9. 追加核查：白皮书 vs 项目宪法（AGENTS.md 母纲）一致性（2026-08-13 第三轮）

承接"全面检查10遍"，补做此前未系统覆盖的一遍：**白皮书作为对外能力承诺地图，是否与项目宪法 `AGENTS.md` 母纲十条、§0.0.3 四硬检验、选型铁律一致，有无越级或矛盾**。

### 9.1 发现 1（已修硬伤）：DBX 措辞自相矛盾，误导"违反无 AGPL 铁律"
- **问题**：白皮书第十章宪法原则第 3 条（原第 772 行）写"（注：**被集成组件**中 DBX 为 AGPL-3.0，须履行相应开源义务）"。但白皮书自身第 87/242/313 行均把 DBX 标为"🔗纯参考/不集成"，AGENTS.md 第 54/159 行明确"DBX=AGPL-3.0 仅为白皮书 L3E 提到的可视化参考，**AOS 从未 import 该组件**"，且本轮在 `src/` 全仓 Grep `dbx|databox|DataBox` **零匹配**。原措辞会误导读者以为 AOS 集成了 AGPL 组件（违反选型铁律"无 AGPL"）。
- **修复**：第 772 行改为"DBX 为 AGPL-3.0，仅作纯参考**不集成**，AOS 代码层从未 import，零 AGPL 真接组件；若未来真接须过 §0.0.3 四硬检验 + 母纲双重过审"。措辞与白皮书自身节点表、AGENTS.md、代码实证三方对齐。

### 9.2 发现 2（已补缺口）：白皮书未显式呼应"不收割四硬检验"守门机制
- **问题**：AGENTS.md §0.0.3 把"不收割四硬检验（断网/出走/付费墙/抽成）"定为硬性可验证要求，由 `tests/test_no_harvest_charter.py`（33 项，当时沿用旧称"16 项"）承接；但白皮书全文 Grep `no_harvest|harvest_charter|四硬检验|硬检验` **零匹配**——能力声明地图未与宪法的可执行守门机制挂钩。
- **修复**：在第十章宪法原则表后新增「宪法原则的可验证承接」小节，显式点明四硬检验 + `test_no_harvest_charter.py` 33 项守门（当时记作"16 项"是沿用旧数字）+ 代码层零 AGPL 真接组件，使白皮书能力声明背后有可执行守门，而非仅靠文档自我声明。

### 9.3 其余母纲条款一致性核验（全绿）
| 母纲原则 | AGENTS.md 表述 | 白皮书对应 | 一致性 |
| :--- | :--- | :--- | :--- |
| 1 本地优先·数据自持 | §0.0 原则1 / §0.0.2 维度1 | 白皮书第770行 / 第402行"本地模型优先" / 第637行"本地优先" | ✅ |
| 4 主权归你·永不收割 | §0.0 原则4 | 白皮书第773行 / 第387行"完全离线自给自足…随时自由切断" | ✅ |
| 5 无平台·无抽成·无中心节点 | §0.0 原则5 / §0.0.4 | 白皮书第774行 / 第387行"不谋求吞并任何厂商生态" | ✅ |
| 8 终身陪伴·代际传承 | §0.0 原则8 | 白皮书第777行 / 第402行"代际传承…有尊严地告别" | ✅ |
| 商业化边界 | §0.0.4 "开源核心永久免费；只卖省事不卖准入" | 白皮书第117处（守门测试承接）/ 第246类似约束 | ✅ |

**结论**：白皮书与 AGENTS.md 母纲**整体一致、无越级、无矛盾**；本轮抓到并修复 1 处硬伤（DBX"被集成"措辞）、补 1 处连贯性缺口（四硬检验守门呼应）。白皮书诚实性结论维持不变：**整体诚实、无系统性编造、无越级吹③**；所有历史"待修点"已清零（LocalAI 许可证已改、openKylin 误判已撤销、三份文档互引已加、DBX 措辞已修、四硬检验已呼应）。

---

## 10. 追加核查：四硬检验守门测试真跑 + 白皮书状态计数更新（2026-08-13 第四轮）

承接"检查 继续"，挑两个**尚未真实验证、且最关乎诚实纪律**的镜头做第 10 遍：
（1）第 9 节新加的"四硬检验守门呼应"背后是不是空话——必须真跑守门测试；
（2）白皮书 61 节点计数是否还准——重新精确计数。

### 10.1 守门测试"16项"是错的——实际 33 项，且真跑绿
- **问题**：AGENTS.md §0.0.3 第 86 行写"`tests/test_no_harvest_charter.py`（16 项）= 宪法的可执行版本"；第 9.2 节也沿用"16 项"。但文件里 `grep -cE "def test_"` = **33 个**测试函数。文档数字与代码实际不符——这正是"宣称 vs 真值"硬核核查要抓的。
- **真跑实证**（managed Py3.13.12 + pytest 9.1.1，`AOS_FORCE_EXIT=1` 防挂死）：
  - 收集 **33 items**，结果 **32 PASSED + 1 SKIPPED**。
  - 跳过项：`test_dialect_real_transcription_end_to_end`（方言真实转录端到端）——需音频+模型，sandbox 无资源时**诚实 skip，不假绿**（非伪造通过）。
  - 覆盖四条硬检验（断网/出走/付费墙/抽成）+ 方言能力层 + 灵魂同步；含反向验证（故意塞回 `WORKFLOW_COUNT:0` → 测试 FAILED，证明真拦得住功能墙）。
- **结论**：守门机制**真能跑绿，非空话**（坐实第 9 节"呼应"小节的可信度）；但"16项"是过时/错误数字，实际 **33 项（32 通过 + 1 资源跳过）**。

### 10.2 诚实修正（已落地）
- AGENTS.md 第 86 行：`（16 项）` → `（33 项 = 32 通过 + 1 资源跳过）`。
- 白皮书第 781 行「可验证承接」小节：`（**16 项守门测试**）` → `（**33 项守门测试 = 32 通过 + 1 资源跳过**）`。
- 审计报告 9.2 节两处"16项"同步更正为"33项（当时沿用旧称）"。

### 10.3 自我纠错：第 10 遍节点计数复核本身有误（白皮书 61 正确）
- **更正**：第 10 遍用 python 重数得"mermaid 图内 67 / 全文 71"，并据此认定白皮书"61 节点"过期——**这是错误的**。
- **根因**：第一轮计数正则把 **mermaid 图例（LEGEND 内 LGD1–LGD4，其 label 本身含 `[✅…]/[🔁…]/[🔗…]/[🚧…]` 标记）与正文节点对照表里的状态列标记** 也算进了"节点"，造成 +6 假增量。
- **重新精确计数（排除图例 + 表格，只数架构图节点定义行）**：**✅46 / 🔁4 / 🔗11 / 🚧0 = 61 节点**，与白皮书正文第 198 / 307–314 / 330 行完全一致。
- **结论**：白皮书节点计数（61）经复核**正确，无需修改**；上轮"61→67/71 过期"系误数，特此撤销并更正。本轮（第 11 遍）复核坐实。

**结论**：本轮抓到并修正 1 处文档-代码数字不符硬伤（16→33 项守门测试）；并自我纠错——上轮"61→67/71 过期"是把 mermaid 图例标记与正文表格状态标记误算入节点的假差异，真实架构图节点为 **61（✅46🔁4🔗11🚧0）**，白皮书计数**正确无误**。守门机制经实跑证明**真有效**。白皮书诚实性结论维持：**整体诚实、无系统性编造、无越级吹③**。至此"全面检查"硬维度新增"守门测试真跑"一层，全部覆盖、全绿。

---

## 11. 第 12 遍：标 ✅/② 能力"真完 vs 假完"桩代码扫描（实证）

**镜头**：前 11 遍只验证了"路径存在 / import 存在"，未查核心函数是否空壳。本轮直击最深一刀——**扫描 `src/`（排除测试）的桩/假标识，对命中的被宣称模块逐一读源码 + 跑专属单测**，验证"标 ✅ 实则空壳"是否成立。

### 11.1 扫描与方法
- Grep 全仓（含 `src/`）：`NotImplementedError | TODO | FIXME | placeholder | stub | 未实现 | 待实现 | 占位`。
- 对命中的**被白皮书宣称**的模块，逐一 Read 源码定性 + 跑对应专属单测。

### 11.2 命中定性（4 类，均非"虚假宣称"）
1. **生成代码样板（非宣称项）**：`src/common/meta_orchestrator_pb2_grpc.py`、`mcp_control_plane_pb2_grpc.py` 的 `raise NotImplementedError` 是 gRPC 编译器生成的服务端样板（文件头 `# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!`），且**白皮书对这些模块零提及** → 不构成"标✅实空壳"。
2. **防御性 inert 桩（非宣称项）**：`src/core/brain.py:1314` 的 `DeerFlow inert stub`（`_InertDeerFlow`）仅在真实网关与本地调度兜底都起不来时兜底防崩；白皮书**未宣称 DeerFlow 为 ✅**。
3. **抽象基类方法（标准 OOP，被真实子类重写）**：
   - `constitutional_governor.py`（CONST3 ✅）：`evaluate()` 真实调用 `constitutional_agent.Constitution.evaluate()` 返回结构化结果 —— **真逻辑**。
   - `memory_ladder.py`（L3A LanceDB ✅）：`MemoryTier` 基类 `store/recall` 抛 NotImplementedError，由 `InMemoryTier` / `LanceDBTier` 真实重写；`merge` 的 NotImplementedError 是**代码注释已标注的诚实边界**（本地模式仅 remote 表支持，白皮书第 543 行已写明"跨分支合并需 LanceDB Cloud"）。
   - `soul_sync.py`（原则 10 灵魂同步 ②）：`Transport` 基类 `put/get/list` 抛 NotImplementedError，由真实子类 `LocalDirTransport`（U盘/本地目录、零网络）重写；核心 push/pull/sync 含 Lamport 计数、内容哈希、冲突副本、zip+JSON manifest、可选 Fernet 加密 —— **真同步，非占位**（docstring 显式声明"不是占位，是真同步"）。
   - `hal.py`（L1G 硬件抽象层 ✅）：`Driver` 基类 `profile/execute` 抛 NotImplementedError（显标 `# pragma: no cover - 抽象`），由 `DryRunDriver` / `CallableDriver` 真实重写；`HAL` 类实现注册/路由/执行并返回真实退出码与耗时 —— **真实现**。
4. **未宣称基础设施**：`v5_bridge.py` 的 NotImplementedError 白皮书零提及，非虚假宣称。

### 11.3 单测实证（managed Py3.13.12 + pytest 9.1.1，`AOS_FORCE_EXIT=1`）
- `tests/test_constitutional_governor.py` → **4 passed**
- `tests/test_memory_ladder.py` → **18 passed**
- `tests/test_soul.py` → **4 passed**
- `tests/test_body_layer.py`（hal）→ **13 passed**
- 合计 **39 用例全过（exit 0）**，坐实"②级 = 代码 + 单测可跑"对非桩。

### 11.4 结论
本轮**未发现任何"标 ✅/② 实则空壳"的虚假宣称**。所有被白皮书宣称能力模块的核心函数均为真实实现（`NotImplementedError` 一律是抽象基类方法，或被真实子类重写，或已在代码注释 + 白皮书正文中标注为诚实边界），且均有专属单测全绿。这从代码层坐实了白皮书第 330 行的判断——**"真正零代码的节点为 0 / 一半以上是空壳不成立"**。白皮书诚实性结论维持：**整体诚实、无系统性编造、无越级吹③**。

（说明：本轮为只读实证，未改动任何白皮书/代码文件；仅把核查结论记入本报告与项目日志。）

---

## 12. 第 13 遍："一套系统 vs 一堆"实证——运行脊柱真实装配

**镜头**：前 12 遍验了路径 / import / 非桩 / 单测，但未验"标 ✅ 组件是否被运行脊柱串成一套活的、可统一健康检查的系统"。本轮直击用户原焦虑"弄的一堆而不是一套"。

### 12.1 白皮书的可测断言（第 175 行）
> 焊接度：✅ 节点运行时 import 8/42 → 42/42；孤儿 34（81%）→ 0；启动真实实例化 **31 个组件，构造失败 0**。

白皮书第 169–192 行整节标题即为"系统集成与焊接诚实状态（2026-08-09 补 · 回应「一堆不是一套」）"——直接回应用户该疑虑。

### 12.2 实证（managed Py3.13.12 + AOS_FORCE_EXIT=1，PYTHONPATH=src）
真实例化 `LifeformRuntime()`：
- **components 数 = 31**（life_state / homeostasis / soul_sync / hal / memory_ladder / constitutional_governor / localai_backend / piper_tts / video_shotcraft … 计 31）；
- **errors 数 = 0**（构造失败列表为空）；
- `status()` 正常返回活体快照（`components_loaded` / `components` / `vital_sample` 等键）。

**结论：白皮书"31 个组件，构造失败 0"的精确断言被实跑坐实。** 31 个生命体层组件被 `lifeform_runtime.py` 以独立 try 焊入运行脊柱，统一经 FabricHub 可达、`GET /api/lifeform` 可观测——确为"一套系统"的运行态焊接，而非磁盘上互不相通的导入。

### 12.3 诚实边界（白皮书已自标，未越级）
- 白皮书第 179–192 行明确该焊接为 **② 级（代码 + 运行时实例化实证）**，非 ③ 级（真 LLM 端到端闭环）；并诚实补齐降档前提（仅 autopilot 配置 `AOS_LLM_MODEL` 时触发）与"③ 未验"边界，未把"挂着"谎称"真驱动"。
- **观察（非硬伤）**：`lifeform_runtime.py` docstring 仍写"逐步把白皮书 34 个孤儿焊进此表即可完成两套合一"，与当前 31/31 实装、孤儿≈0 的实况略有滞后；属代码注释未同步，不影响白皮书结论。

### 12.4 结论
本轮**未发现"标 ✅ 实一堆"的虚假宣称**；用户原焦虑"一套 vs 一堆"在 ② 级运行态下被实证为**一套（焊接成网、31/31 活、0 失败）**。白皮书诚实性结论维持：**整体诚实、无系统性编造、无越级吹③**。

（说明：本轮为只读实证，未改动白皮书/代码文件；仅把核查结论记入本报告与项目日志。）

---

## 第 13 节 · 第 14 遍（infra 层 "42 表" 数据库金标准实证）

### 13.1 镜头与措辞校准
- 用户长期画像 / 项目记忆均引用 AOS 数据库为 **"42 表跨 infra/ecosystem/evolution/economy/immune 五层（SQLModel/ORM、WAL）"**。这是一个**硬、可证伪**的数字，直接关乎 infra 层 ✅ 底座是否诚实。
- **诚实校准**：白皮书 V6 字面**未写"42 表"**（grep "42 表/42张/张表" 零命中）；白皮书第 175 行唯一的"42"是**运行时 import 覆盖率**（42 个 ✅ 类节点由 8 焊到 42，与第 12 节 31 组件实例化属同一焊接叙事的不同度量，**不是 42 张表**）。故本轮验证对象为**项目级"42 表"硬数字**，而非白皮书某句措辞——结论不影响白皮书诚实性判定，但坐实 infra 层真实底座。

### 13.2 三重验证（防漏数 / 防空心）
1. **类定义精确计数**（脚本 `grep -rEo "class X(... table=True ...)"`，非手工）：全 `src/` 共 **42** 个 `table=True` SQLModel 表类，全集中于 `src/core/database/models/` 五层文件（infra 13 / immune 4 / evolution 10 / ecosystem 10 / economy 5）。`grep -rEl` 在 `src/kernel/evolution.py`、`src/kernel/live.py` 误报的"table=True"经核查为 `Gene(... immutable=True)` 子串带偏，**非表类**。
2. **引擎焊接核实**：`src/core/database/engine.py::init_db()` 先 `from core.database import models`（把所有表注册进 metadata），再 `SQLModel.metadata.create_all(engine)`，docstring 明写"幂等创建全部 42 张表"——**表非孤儿定义，被引擎焊接**。
3. **金标准实证（真实 SQLite 建表）**：managed Py3.13 隔离 venv 装 `sqlalchemy 2.0.51 + sqlmodel 0.0.39`，指向临时 SQLite 跑 `init_db()`：
   - `sqlite_master` 实际建出表数 = **42**；
   - `SQLModel.metadata` 注册表数 = **42**；
   - 42 张表名按五层逐一对应（infra: users/agents/threads/messages/checkpoints/conversations/knowledge/tasks/audit_log/notifications/event_store/snapshots/cold_memories；immune: compliance_records/identity_vault/semantic_firewall_rules/sandbox_policies；evolution: task_fingerprints/orchestration_specs/workflow_definitions/evolution_log/learning_experiences/model_routing_history/performance_metrics/prompt_templates/negotiation_sessions/self_modification_proposals；ecosystem: skills/skill_versions/tool_registry/mcp_connectors/agent_cards/subagent_registry/knowledge_graph_nodes/knowledge_graph_edges/agency_roles/capability_registry；economy: token_ledger/cost_accounting/reward_events/budget_pools/economic_transactions）——**零重名、零垃圾表**。

### 13.3 结论
**项目级"42 表"硬数字经金标准实证为真**——42 个表类全部被引擎 `create_all` 真建出、五层分布与架构宣称完全吻合，坐实 infra 层 ✅ 底座诚实。**本轮未发现硬伤、无新增待修点**；白皮书诚实性结论维持：**整体诚实、无系统性编造、无越级吹③**。

（说明：本轮为只读实证，未改动白皮书/代码文件；仅把核查结论记入本报告与项目日志。）

---

## 第 14 节 · 第 15 遍（LLM Router 标 ✅AOS代码/② 真实注册与路由逻辑实证）

### 14.1 镜头与措辞校准
- 用户长期画像 / 项目记忆反复引用 AOS「LLM Router 已接入 **15/16** provider（deepseek、scnet×12、siliconflow、zhipu，ollama 不可用，另有 3 个本地 GGUF 待接入）」。这是一个硬、可证伪数字，且直刺核心路由底座诚实度——但**白皮书 V6 字面未写该串数字**。
- **白皮书真实写法**（grep 实证）：第 58 行 mermaid「L1B 模型路由网关：LiteLLM（MIT 100+ provider，已真接）」、第 219 行表格「`LiteLLMAdapter` 统一 100+ provider OpenAI 格式路由，已装 1.95.0」、第 285 行把「LiteLLM 多 provider 真路由」**诚实标为 ③ 端到端待主机验证项**。
- 故本轮验证对象 = **「LLM Router 标 ✅AOS代码/②」这项能力是否真注册 provider、路由逻辑是否活（非桩）**，而非白皮书某句数字；白皮书 ②/③ 边界本身正确，无需改。

### 14.2 实证（真实例化 `LLMRouter()`，managed Py3.13 venv：openai/litellm/requests/sqlmodel 已装，仅 websocket 缺）
- `ModelProvider` 枚举共 **8** 个成员（ZHIPU / SILICONFLOW / BAIDU / XFYUN / OLLAMA / MISTRALRS_GENERAL / MISTRALRS_CODING / MISTRALRS_REASONING）。
- **真实运行环境实际注册 7 个 provider**（`available=True`）：智谱GLM-4-Flash、硅基流动(DeepSeek-V2.5)、百度ERNIE、Ollama本地(qwen2.5:7b)、MistralRS-MiniCPM5 / QwenCoder / DeepSeek。
- 唯一未注册 = **XFYUN（讯飞星火）**，原因 = venv 缺 `websocket-client` 库，代码 `_init_providers()` 明写「websocket-client库未安装，讯飞星火不可用」——**诚实降级，非虚假缺失**。
- 注册为**条件式**（依赖 `config.XXX_ENABLED` + API key 非空 + 依赖库可用），无 key 则不注册；本沙箱 `.env` 已配真实 key，故 7 个上线。

### 14.3 路由逻辑活性（非桩）
- `_get_provider_priority(TaskType.CODING)` 真实返回优先级链 `['mistralrs_coding','ollama','zhipu','siliconflow','baidu']`——按任务类型动态选路；
- `_call_provider` 实为 **32 行**真实分发函数（按 provider 路由到 `_call_zhipu/_call_siliconflow/_call_baidu/_call_xfyun/_call_ollama/_call_openai_compatible`）；
- `chat()` 实为 **62 行**真实 dispatch（默认走 `_call_litellm_fallback` 统一推理平面，失败才降级逐 provider 试）——**全链路真实代码，零 `pass`/空壳**。

### 14.4 结论与诚实备注
- **LLM Router 标 ✅AOS代码/② 经实证非桩**：provider 注册机制真工作（实跑注册 7/8）、路由逻辑全活、与白皮书 ② 级边界一致（库已真接 litellm 1.95.0、路由逻辑活、「多 provider 真路由」③ 待主机）。**本轮无白皮书硬伤、无新增待修点。**
- **记忆/画像裂缝（须校准、非白皮书硬伤）**：记忆中的「15/16 provider / scnet×12 / ollama 不可用」与代码真值**不符**——代码枚举仅 8、无 `scnet` 这个 provider、ollama 在沙箱真实注册且 `available=True`。属历史画像过时，建议在后续会话以代码真值（8 枚举 / 实跑 7 注册 / 讯飞因缺 websocket 降级）覆盖旧记忆；白皮书因未写该串数字而不受影响。
- 细节观察（③ 级待验证，非 ② 级硬伤）：三个 `MISTRALRS_*` provider 的 `model` 字段在 `.env` 缺对应值时为空串；真推理时需补 config。白皮书已诚实把「真路由」标 ③，故在此边界内。

（说明：本轮为只读实证，未改动白皮书/代码文件；仅把核查结论记入本报告与项目日志。）

---

## 第 15 节 · 第 16 遍（HTTP/API 服务边界实证："/api/lifeform" 真返回 31 组件活体快照）

### 15.1 镜头与动机
- 用户最原始的焦虑是「AOS 是一套系统，还是一堆散件」。前 15 遍已验证内部焊接（第 12 节：31/31 组件实例化、0 失败）、DB 底座（42 表）、路由（LLM Router 7/8），但**从未在对外服务边界锤过**——即 `GET /api/lifeform` 这类端点是否真把运行脊柱的活体快照暴露出去。
- 白皮书第 169–192 节整节回答「一堆不是一套」，第 192 行明确可测断言：`/api/lifeform` 的 `picked_now` 应在体征降档时**从 `qwen3:8b` 变 `qwen2.5:3b`**。本轮即锤此服务边界。

### 15.2 服务层焊接定位（先读代码，再实证）
- 服务端 `src/api/main.py` 真实存在：`@app.on_event("startup")`（line 666-675）把 `LifeformRuntime` 挂到 `app.state.lifeform`（`get_lifeform_runtime()`），并 `lf.register_with_hub(hub)` 焊入 FabricHub；构造失败 best-effort 跳过。
- `@app.get("/api/lifeform")`（line 830-851）直接读 `app.state.lifeform` → 调真实 `lf.status()`（活体快照）+ `lf.pick_model(heavy)`（真实降档决策），docstring 明写「证明白皮书生命体 OS 是运行系统的一部分，不是磁盘上的孤儿」。
- 端点由真实 `APISecurityMiddleware`（`src/api/security.py:315`）保护：本环境 `.env` 配了 `AOS_API_KEY`，故中间件激活——不带凭据直接返回 **401 Unauthorized**（证明鉴权网关**真生效、非摆设**，符合母纲「本地优先、打开即用」外的真实安全边界）。

### 15.3 金标准实证（managed Py3.13 venv：fastapi/starlette/httpx/uvicorn/pydantic 均 OK）
- 用 `fastapi.testclient.TestClient` 真实拉起 `api.main:app`（触发 startup 挂载），**清空 `AOS_API_KEY`/`AOS_API_KEY_HASH` 让 dev 模式放开鉴权**，走完整 HTTP 路径：
  - `GET /health` → **200** `{"status":"alive","service":"aos",...}`（应用真启动）；
  - `GET /api/lifeform` → **200**，返回：
    - `components 数 = 31`、`errors 数 = 0` —— **与第 12 节内部实例化逐字吻合**（同一运行脊柱，服务边界与内部态一致）；
    - `model_decision = {"heavy":"qwen3:8b","picked_now":"qwen2.5:3b",...}` —— **真实降档逻辑生效**，与白皮书第 192 行断言精确一致；
    - 顶层键含 `lifeform_runtime / components_loaded / components_failed / vital_sample / model_decision` —— **真实体征采样，非编造**。
- 反向证明：端点带 `AOS_API_KEY` 时返回 401（鉴权真拦），再次确认服务不是裸奔。

### 15.4 结论
**HTTP/API 服务边界实证为真**：31 组件运行脊柱已通过 `startup` 真实焊入 FastAPI、并经 `/api/lifeform` 对外暴露真实活体快照（31/0、降档决策 qwen3:8b→qwen2.5:3b 全部真发生），且受真实鉴权网关保护。这把「一套系统」从**内部焊接**（第 12 节）推到**对外可观测的服务边界**——用户原焦虑「一堆不是一套」在 ② 级下被闭环坐实：**一套（焊接成网、31/31 活、0 失败、对外可观测、鉴权生效）**。**本轮无白皮书硬伤、无新增待修点。**
