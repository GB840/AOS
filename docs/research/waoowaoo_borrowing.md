# 借鉴 waoowaoo（AI 短剧/漫剧一站式生成平台）—— 单创OS 视角

> 核实日期：2026-07-25
> 来源仓库：`github.com/saturndec/waoowaoo`（约 11K–13K Star，单人开发，测试版）
> 处置类别（依据 MEMORY § XII 铁律）：**第①类 —— 不能商用 → 只借鉴，不引代码、不商用集成**
> 判定依据：① 许可证为 **CC BY-NC-SA 4.0**（明确 NonCommercial，禁止商业使用，与单创OS 商业 SaaS 冲突）；② 技术栈 Next.js 15 + React 19 + MySQL/Prisma + Redis/BullMQ + MinIO + NextAuth，是带数据库的 Docker 全栈 Web 服务，既非 CLI 也无法 opt-in subprocess 接入；③ 与 AOS 的 Python FabricHub 体系完全不兼容。

---

## 一、waoowaoo 是什么（核实自官方 README + 多方评测）

一款"工业级全流程 AI 影视生产平台"：输入小说文本，自动跑完 **剧本分析 → 一致性角色/场景图 → 分镜视频合成 → 多角色 AI 配音 → 成片** 全链路。核心卖点不是单步生成，而是**把影视工业拆成可人工干预的环节**，且数据完全自控（本地 Docker 部署）。

四个核心环节：
1. **AI 剧本分析**：解析小说，提取角色/场景/剧情结构化元数据（非简单摘要）。
2. **角色 & 场景生成**：AI 生成跨镜头一致性的人物与场景图（6 层身份锚点管理外观）。
3. **分镜视频制作**：自动拆镜头脚本（Shot List）并合成视频片段，支持好莱坞"预可视化"工作流。
4. **AI 配音**：多角色语音合成，匹配不同音色。

特点：中英文界面切换、Docker 一键拉起、每个环节可手动改确认（符合影视审核习惯）。

---

## 二、为什么不能"弄"（集成/复用代码）—— 诚实结论

| 维度 | 判定 | 说明 |
|------|------|------|
| 许可证 | ❌ 禁商用 | CC BY-NC-SA 4.0，NonCommercial 条款与单创OS 商业变现直接冲突；衍生品须同协议（ShareAlike），会污染 AOS 代码。 |
| 技术栈 | ❌ 不兼容 | Next.js/TS/Node 全栈 + MySQL/Redis/MinIO，AOS 是 Python FabricHub 适配器体系，无接入面。 |
| 形态 | ❌ 非 CLI | 它是带数据库的 Web 服务，不像 Mediakit/Remotion 能用 `shutil.which` 探测 + subprocess 薄胶水层接入。 |
| 贡献政策 | ⚠️ 不并 PR | 作者明言"审阅 PR 思路，但不直接合并外部 PR"——本质是源码可见、非自由开源。 |

**结论：waoowaoo 不能成为 AOS 的芯粒/适配器，也不能作为其能力的 subprocess 封装。** 任何"把 waoowaoo 接进单创OS"的设想都违反 § XII 第①类铁律，直接否决。

---

## 三、能借鉴什么（落到单创OS 架构叙事，不引代码）

waoowaoo 从**产品理念**上验证了"内容营销岗应覆盖短剧/漫剧垂直场景"，且有 3 个具体设计点值得单创OS 借鉴优化自身：

### 借鉴点 A：分阶段可干预的 AI Agent 管线（→ 内容营销岗工作流）
- waoowaoo 把"小说→成片"拆成 4 个可人工确认环节，而非黑盒一键出片。
- **AOS 映射**：单创OS 内容营销岗（`content_marketing`）已有的 `workflow=["promote"]` 应扩展为**显式多阶段**：`剧本/选题 → 素材生成(图/视频) → 分镜编排 → 配音 → 成片 → 分发`。每一阶段对应一个 capability 路由（如 `media.image` / `media.video` / `media.audio`），且每阶段产出可经 §0.7 白盒审核门控后再进下一阶段。
- 价值：契合单创OS「白盒才可进化 / 可验证即真理」纪律，避免"一键生成不可控"。

### 借鉴点 B：角色/场景一致性锚点（→ 媒体生成能力的"一致性"要求）
- waoowaoo 用 6 层身份锚点维持跨镜头角色外观统一，这是 AI 视频公认难题。
- **AOS 映射**：在 `media.image` / `media.video` 适配器契约里，把"一致性"作为一等约束写入——例如 `invoke` 请求体增加 `identity_anchors`（角色参考图/场景模板）字段，路由到支持一致性的引擎（如已接入的 Seedream/Seedance 类、或 img2threejs 的 `media.3d.reconstruct` 用于产品外观统一）。
- 价值：弥补 AOS 当前媒体生成"只承诺单次生成、未承诺跨镜头一致"的缺口。

### 借鉴点 C：短剧/漫剧垂直场景作为内容营销岗的子能力（→ OPC 内容营销岗扩面）
- waoowaoo 证明"小说/IP 一键转短剧"是强需求、高变现赛道。
- **AOS 映射**：内容营销岗新增可选 `short_drama` 能力标签（默认关闭，opt-in），由上游 `media.*` 引擎组合编排实现，**不自建影视引擎**（避免重造轮子，也避免 CC 协议污染）。单创OS 只做"编排层 + 一致性约束 + 审核门控"，底层生成仍走已接入的开放/商用许可引擎。
- 价值：让单创OS 在"内容飞轮"叙事里补齐"视频化/短剧化"一环，对标 waoowaoo 但不碰其代码。

### 借鉴点 D：数据完全自控 + 分阶段审核的产品哲学（→ 强化单创OS 合规叙事）
- waoowaoo 强调本地部署、数据自控、每环节人工确认——与单创OS §0.7 可验证纪律同源。
- **AOS 映射**：在 AGENTS.md / 产品愿景里把"用户数据自控 + 阶段审核门控"作为单创OS 相对闭源 SaaS 的差异化卖点，直接呼应 OpenWorker 借鉴里已立的"审批门控/审核收件箱"缺口（A 项）。

---

## 四、与已借鉴项目的协同

| 外部项目 | 处置 | 与 waoowaoo 的关系 |
|----------|------|-------------------|
| OpenWorker | 只借鉴（MIT 但技术栈不兼容） | 两者共同印证"本地优先 + 审批门控 + 分阶段"是正确架构方向；waoowaoo 补了"内容/短剧"这一具体场景。 |
| img2threejs | 能用就用（Apache-2.0，已接入） | waoowaoo 的"一致性场景图"可由 `media.3d.reconstruct`（产品研发岗）在"产品外观统一"维度互补。 |
| Mediakit CLI | 只借鉴 + opt-in subprocess（火山引擎） | waoowaoo 的"分镜合成/配音"环节，底层可借 Mediakit 的 `media.process` 后期能力实现（商用许可 CLI，opt-in）。 |

---

## 五、落地建议（不引代码，纯叙事/架构层）

1. **不创建 waoowaoo 适配器、不 vendored、不 subprocess 接入**（铁律第①类）。
2. 在 `docs/SHANCHUANG_OS_PRODUCT_VISION.md` 内容营销岗章节，补"短剧/漫剧子能力（opt-in，编排层不自建引擎）"与"一致性锚点作为媒体生成一等约束"。
3. 在 `AGENTS.md §5` 借鉴小节补 §5.3「借鉴 waoowaoo（内容管线理念，CC BY-NC-SA 禁商用，只借鉴）」。
4. 内容营销岗 `opc_roles.py` 可加可选 `short_drama` capability 标签（默认关闭），驱动上游 `media.*` 引擎组合——**仅声明，不实现底层引擎**。

> 诚信备注：以上均为"理念借鉴 + 架构叙事"，未引入 waoowaoo 任何代码、未违反其 CC BY-NC-SA 4.0 许可证。单创OS 在内容/短剧方向的实际能力，仍由已接入的开放/商用许可引擎（img2threejs / Mediakit / 自研 media.* 适配器）提供。

---

## 六、落地状态（代码已落地，2026-07-25）

原"仅声明不实现"的借鉴点现已在工程层实现（仍**不引入 waoowaoo 代码**，只借鉴其理念）：

| 借鉴点 | 落地代码 | 诚实边界 |
|--------|----------|----------|
| A 多阶段可干预管线 | `ContentMarketerAdapter.promote_pipeline()`：选题→素材→分镜→配音→成片→分发 6 阶段，每阶段经 `reviewer` 闸门（§0.7 白盒审核），False 即停。 | 仅适配层真跑（layer ①② 已测）；端到端视频生成仍需真 LLM+媒体引擎（layer ③ 未验）。 |
| B 一致性锚点 | `produce`/`promote_pipeline` 接收 `identity_anchors` 并透传至 `media.video` 调用契约（已测试桩验证透传）。 | 是"约束字段 + 透传"，不是"一致性生成算法"——底层一致性由接入引擎负责，AOS 不自建。 |
| C 短剧子能力 | `Capability.CONTENT_SHORT_DRAMA` 枚举 + `content_marketer` 注册 + `opc_roles` 内容营销岗能力表，opt-in（默认走普通短视频）。 | 仅是能力标签与短剧提示词变体；底层生成仍走已接入引擎，未自建影视引擎。 |
| D 审核哲学 | 由 promote_pipeline 的 `reviewer` 闸门机制承载（默认 reviewer 自动放行并记录，不等同人工已审）。 | 默认非人工审核，调用方需自传 reviewer 做真门控。 |

新增测试 `tests/test_content_marketer_pipeline.py`（5 例全过）：验证 6 阶段真跑、reviewer 任意阶段挡停、short_drama 能力注册、pipeline 分支可由 invoke 触发、identity_anchors 透传。

