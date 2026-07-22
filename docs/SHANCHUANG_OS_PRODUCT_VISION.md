# 单创OS 产品愿景与落地蓝图（AOS 项目升级定义）

> 本文是 AOS 项目的**产品定义真值源**（product source of truth），由用户 2026-07-23 提出，
> 经全量代码盘点后补充「现状差距」与「落地路线」。代码宪法仍以 `AGENTS.md` 为准，
> 本文定义"这个系统对外是什么、怎么赚钱、怎么落地"。
>
> 对外品牌名：**单创OS**（全称：单人创业 OPC 智能操作系统）。代码内部仍称 AOS，对外售卖用"单创OS"。

---

## 一、产品定位（双层共生，一套代码两套模式）

不再只做"自用工具"，升级为**可售卖的 SaaS 平台**：

1. **自用侧（样板间）**：自己做青少年护眼眼镜，用系统搞定产品开发、调研、营销、财务。
   → 创业智能体 = 执行工具。
2. **商用侧（楼盘）**：打包成标准化平台，卖给单人创业者、独立开发者、个体户。
   → OPC 一人公司架构 = 组织底座。

两者**双向共生、一套系统两套使用模式**，不是上下层简单叠加：

- **底层统一**：OPC 作为数字公司组织底座，内置市场、研发、营销、客服、财务全套岗位智能体。
- **上层分叉**：
  ① 自用模式（你自己）：创业执行引擎，把硬件创业目标自动拆解、落地、迭代；
  ② 租户模式（付费客户）：多租户隔离，每个买家拥有独立"AI 一人公司"，适配各自行业。

---

## 二、融合逻辑（天然互补，非生硬叠加）

| 层 | 解决什么 | 对应代码现状 |
|---|---|---|
| OPC 数字组织内核 | 「组织」：一个人如何拥有完整公司部门，定义数字员工岗位体系 | `agency_roles/` 270 个通用角色 + `opc_loop.py` 阶段价值链（雏形） |
| 创业目标调度引擎 | 「目标落地」：任意创业目标自动拆解、执行、复盘迭代 | `autopilot.py` 规划-执行-反思-续跑（已较完整） |
| 融合后 | OPC 提供部门人力，创业智能体给部门派活、监督交付、优化流程 | **需新建编排层把两者接起来** |

---

## 三、完整可商用融合架构（四层）

```
┌─────────────────────────────────────────────────────────────────┐
│  第四层：双模式前端界面                                            │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │ 自用工作台（你专属）  │  │ 租户商户后台（付费客户）          │  │
│  │ 硬件开发全套插件      │  │ 电商/自媒体/硬件多行业模板       │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  第三层：创业目标调度引擎（原创业智能体核心）                      │
│  一句话目标 → 自动拆解 → 分配 OPC 岗位 → 监控进度 → 复盘迭代      │
├─────────────────────────────────────────────────────────────────┤
│  第二层：OPC 数字组织内核（5 大标准化岗位智能体）                 │
│  产品研发 │ 市场调研 │ 内容营销 │ 客户服务 │ 财务核算            │
│  每个岗位自带：完整工作流 + 行业知识库 + 工具调用权限            │
├─────────────────────────────────────────────────────────────────┤
│  第一层：多租户隔离底座（对外售卖核心，当前完全缺失）            │
│  租户A(DB) │ 租户B(DB) │ 租户C(DB) │ 平台管理员(全局管控)     │
│  共享：调度引擎 + 模型池 + 开源工具链                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、两套使用场景

**场景1：自用（护眼眼镜）**
总目标 → 调度引擎下发任务给 OPC 各岗位：研发（选型/模型量化/固件）、市场（竞品分析）、
营销（抖音脚本/海报）、财务（BOM/利润表）；每日汇总，发现"误提醒过高"自动让研发优化模型。

**场景2：租户（手工饰品个体户）**
开通会员 → 输入"小红书变现+开淘宝店" → 调度引擎拆任务，岗位切换饰品行业工作流 →
租户只做创意决策，执行全由 AI 数字员工完成。

---

## 五、产品命名

- 综合大气款：单人创核 OPC 系统 / 独企智核 / 孤创引擎
- 直白商用款：一人AI创业工厂 / OPC全链路创业智能平台 / 个体户AI数字公司系统
- 极简品牌名：**单创OS**（首选，全称 单人创业OPC智能操作系统） / 独企云 / 一企智盒
- 域名建议：`danchuang.com`（注册状态待核实）

---

## 六、盈利模式

1. 自用收益：降低护眼眼镜开发的时间/人力成本。
2. 平台售卖：订阅（基础/专业/硬件专属套餐）+ 行业模板收费 + 私有化部署（9800元/次）。
3. 定价建议：免费试用 / 49元月（个人标准）/ 99元月（硬件专业）/ 9800元（私有化）。

---

## 七、现状代码盘点（2026-07-23 全量，真实）

### 可复用资产
- `src/kernel/autopilot.py`：目标规划→执行→反思→续跑引擎（`_plan`/`_execute`/`_reflect_and_redesign`），带真实闸门。
- `src/kernel/opc_loop.py`：`build_default_stages()` 6 阶段 `analyze→promote→acquire→deliver→evolve→maintain`，Meta-Trace 失败回流。
- `src/kernel/plugins/fabric_hub.py` + `core/fabric/adapters/`：芯粒总线，含 crawl4ai(爬虫)/code_execution(代码)/media_gen+comfyui(图文)/video_maker(视频)/tts+stt(语音)。
- `src/skills/agency_roles/`：270 个通用咨询角色文件（数字员工库），统一入口 `_kernel_bridge.py`（feature flag 默认关）。
- `src/kernel/industry/restaurant/bbq_shop.py`：行业垂直闭环模板（运营→内容→客服→回流），可作 5 岗位映射参考。
- 前端壳：`web/portal.html`、`src/web/app.py`、`web/console.py`、`web/studio/`、`web/bidding/`。

### 完全缺失（需从零新建）
1. **多租户隔离层**：`src/core/database/engine.py` 单 SQLite，`infra.py` 的 users/agents 表**无 tenant_id**；全项目搜 `tenant` 零业务命中。需 tenant_id 贯穿 DB/路由/记忆/存储。
2. **租户认证 + RBAC + 商户/管理员后台前端**：当前全部单用户视角。
3. **订阅/计费/支付**：`src/core/database/models/economy.py` 仅内部 token 成本核算（token_ledger/cost_accounting），搜 `subscription|billing|支付|套餐` 零命中。
4. **5 岗位智能体 → 租户资源配置的注册表与编排层**：现有 agency_roles 是通用库，需映射到 5 业务职能并绑定租户。
5. **报表生成芯粒**：财务核算岗位缺报表生成工具（adapters 无 report/file 生成芯粒）。
6. **SLA/配额/用量计量**（租户级）。

### 与方案冲突、需用户拍板
- ⚠️ **模型依赖冲突**：方案称"底层只用开源 Qwen/DeepSeek、无第三方 API 分成风险"，
  但项目实际运行依赖 **智谱 ZHIPU_API_KEY（闭源付费 API）**（`AGENTS.md §7` 明记）。
  要兑现"无 API 分成"，需支持切到 Qwen/DeepSeek 本地/开源，或至少默认开源路径。
- ⚠️ **成本/毛利估算**：用户估算单租户增量 2-5元/月、毛利 90% 为商业假设，
  多租户共享推理的性能影响需实测压测，不能直接采信。
- ⚠️ **域名 `danchuang.com`**：注册状态待 WHOIS 核实。

---

## 八、分阶段落地路线（基于现状，不夸大）

### Phase 0 — 品牌与定位落档（本次完成）
- 本文档 + `AGENTS.md` 加产品定位段 + `MEMORY.md` 记产品定位。
- 代码内部仍 AOS，对外品牌"单创OS"。

### Phase 1 — 自用版 MVP（2-4 周，复用为主）
- 复用：autopilot + opc_loop + FabricHub + 前端 shell。
- 新建：
  - **5 岗位注册表**：把 `agency_roles` 映射到 产品研发/市场调研/内容营销/客户服务/财务核算，每个绑定 capability 组合（如研发=code_exec+web.search，营销=media_gen+content_director）。
  - **报表生成芯粒**：补财务岗位工具缺口（生成收支/利润表，可落盘 xlsx/md）。
  - **调度引擎→岗位派活编排**：autopilot 拆解后，按岗位注册表把 steps 路由到对应 role 的 capability 组合（在 `_dispatch` 加 role-aware 分支）。
  - 硬编码你的护眼眼镜项目为样板目标。
- 验证（主机）：浏览器一句话"开发护眼眼镜"→ trace 出现 5 岗位派活步骤。

### Phase 2 — 多租户骨架（与商用并行）
- 新建：tenant_id 贯穿 users/agents/traces/memory；路由层 tenant 隔离；记忆按租户分库；存储隔离。
- 配置开关 `AOS_MULTI_TENANT=0/1`：单租户（自用）/多租户（商用）一套代码切换。

### Phase 3 — 商用版上线（1-2 月）
- 新建：租户认证+RBAC、商户后台、管理员后台、订阅套餐、计费、支付集成（微信/支付宝）、行业模板市场、用量计量、SLA/配额。

### Phase 4 — 持续迭代
- 用户自助入驻、模板扩充、算力扩缩。

---

## 九、诚实声明（防止吹牛）

- 本文档是**产品定义 + 落地路线**，不是"已融合完成"。
- Phase 1 的"复用部分"已在项目存在（autopilot/opc/FabricHub 可跑），但**端到端在真实 LLM 任务下派活给 5 岗位并出报表，沙箱无真 LLM 未验证**。
- Phase 2/3 的多租户/计费/支付**全部新建**，且沙箱无法验证（无真支付环境/多租户压测）。
- 模型依赖冲突（智谱 vs 开源）是真实 blocker，需用户决策后才能兑现"无 API 分成"。

---

## 十、选型铁律与外部参照（WorkRally 评估，2026-07-23）

### 10.1 选型铁律（用户指令，全局适用）
构建单创OS 时，对每个能力先做三选一，绝不盲目造：
1. **现有且够好 → 复用，不造**：优先用 autopilot / opc_loop / FabricHub / agency_roles / bbq_shop。
2. **现有但比外部差 → 优化替换**：先量化差距，再用更优开源方案替换，不重复造。
3. **完全没有 → 用最新开源技术补**：禁止闭源锁定；设计必须可插拔、当下能用且面向未来。
凡引入外部依赖/框架/模型，先 WebSearch 全网核实真实性/许可/可替代项，禁止凭记忆下结论。

### 10.2 复用 / 优化 / 新建 决策矩阵（Phase 1 视角）
| 单创OS 需要的能力 | 系统现有 | 决策（按铁律） |
|---|---|---|
| 目标拆解→执行→反思 | `autopilot.py` 完整（`_plan/_execute/_reflect`） | ✅ 复用，不造 |
| OPC 价值链 + Meta-Trace | `opc_loop.py` 6 阶段 | ✅ 复用 |
| 芯粒总线（爬虫/代码/图文/视频/语音） | `FabricHub` + `core/fabric/adapters` | ✅ 复用 |
| 数字员工库 | `agency_roles/` 270 角色 | ✅ 复用→映射 5 岗位 |
| 行业模板范式 | `industry/restaurant/bbq_shop.py` | ✅ 复用为模板参考 |
| 5 岗位注册表 | 仅通用角色库，无业务映射 | 🔧 优化/新建：编排映射，不从头造 |
| 报表生成芯粒（财务岗） | adapters 无 report 芯粒 | 🆕 用开源（openpyxl/xlsxwriter）轻量补 |
| 内容营销→短视频/海报 | `media_gen`/`comfyui`/`video_maker`/`tts` | ✅ 复用；质量对标 WorkRally |
| 多租户隔离 | 无（单 SQLite，无 tenant_id） | 🆕 新建（未来商用必备，可插拔设计） |
| 计费 / 支付 | 无（仅内部 token 核算） | 🆕 新建（未来商用必备） |
| 漫剧/短视频工业级生产 | 外部：WorkRally | ➕ 可选接入（见 10.3），opt-in，不锁核心 |

### 10.3 外部参照：WorkRally（腾讯视频，2026-04-16 发布）
- **是什么**：腾讯视频「精品漫剧工业级 AI 生产平台」，**闭源商业产品**。三大能力：专家级 Agent + S+ 影视动漫技能库 + 智能流水线；覆盖 剧本解析→分镜→生产→资产管理→团队协作 全链路。公开指标：产能 5x、成本 -50%、角色/场景一致性 >95%、一次过率 >70%。2026-06-24 升级为 专业影视版/精品动画版/AI 漫剧版 三套体系。
- **有公开接口吗（决定能否接入）**：**有**。提供 `npm install -g workrally` CLI（`workrally auth login` / `auth status`）、Open API、标准 `SKILL.md`，**官方明确支持 OpenClaw 等 AI Agent 直接调用**；需腾讯授权账号（workrally.qq.com 微信扫码）。亦支持内容机构私有化部署。
- **能不能"弄"进单创OS**（分三层，防吹牛）：
  - ❌ **不能自托管 / fork**：闭源、需腾讯授权、垂直漫剧（2D/3D 动漫 / AI 仿真人剧），非我们业务（护眼眼镜 / 通用创业），强行克隆是浪费。
  - ✅ **可作为可选外部能力接入**：若用户有 WorkRally 账号，可把其 CLI / Open API 包成 **opt-in** 的 `content.workrally` 能力，让「内容营销岗」产出工业级短视频。这契合「万物为我所用 / 本地云端自由切换」原则，且**不锁死开源核心**——默认走我们 open-source media 芯粒，WorkRally 仅作可选云端增强。
  - ⚠️ **与「无第三方 API 分成」目标冲突**：WorkRally 是付费腾讯服务，接它等于引入外部成本。须明确标注为 opt-in 增强、非默认路径；用户方案里"纯开源"承诺以我们自建 media 栈为准。
- **架构验证价值（最重要）**：WorkRally 的「Agent + Skill + 智能流水线，把重复劳动编排掉让创作者聚焦创意」**与单创OS 的「OPC 岗位 + 创业目标调度引擎」同一范式**。它的腾讯级落地与 5x 产能**正面验证我们方向正确**，不必怀疑"岗位智能体 + 调度引擎"这条路；其质量指标应设为「内容营销岗」的标杆。

### 10.4 结论
- WorkRally **不是我们要造的东西**（垂直闭源），但**是我们要对标的东西**（架构范式 + 质量标杆）+ **可选接入的云端能力**（有 Open API/CLI）。
- 按选型铁律，单创OS 当前该做的不是追 WorkRally，而是**先把已有的 autopilot/opc/FabricHub/agency_roles 编排成 5 岗位闭环**（Phase 1），把"没有的"（报表芯粒、未来多租户/计费）用开源补上。
- 是否现在就搭 `content.workrally` 可选适配器，取决于用户是否有 WorkRally 授权账号——有则接（opt-in），无则暂留接口位。

---

## 十一、已落地：开源默认路由 + 全栈可插拔扩展（2026-07-23）

用户指令：①WorkRally 暂未购账号 → 留接口，且**所有能扩展的都留接口**；②Phase 1 动手（5 岗位 + 报表）；③解决"智谱 vs 开源"——全网搜开源技术，用开源。

### 11.1 开源模型路线（解决第3点，已代码落地）
**联网核实（2026-07-23，WebFetch）**：
- **Ollama**：本地运行开源模型，OpenAI 兼容原生 REST（`:11434`），支持 Qwen/DeepSeek/Llama，可离线、数据不出本地。最轻量开源默认网关。
- **vLLM**：高性能开源推理服务（Apache 2.0），`vllm serve` 提供 OpenAI 兼容 API，支持 200+ 架构（Qwen/DeepSeek），生产级、可量化。

**代码改动（已提交）**：
- 新增 `src/kernel/plugins/ollama_gateway.py`：Ollama 本地开源网关，零硬依赖（仅 urllib），优雅降级。
- `src/kernel/wiring.py`：网关装配顺序改为 **开源本地优先** `[ollama → mistralrs → (智谱 opt-in) → cloud → agnes]`；智谱仅当 `ZHIPU_API_KEY` 或 `AOS_ZHIPU_OPTIN=1` 才入链，默认不引入闭源依赖。
- `src/kernel/layers/model_gateway_layer.py`：`_default_model()` 开源（ollama/）优先；价格表加开源模型（成本 0），成本路由优先选开源；`AOS_DEFAULT_MODEL` 可覆盖。

**效果**：默认跑开源本地模型（无 API 分成），智谱降级为可选兜底，彻底兑现"无第三方 API 分成"。

### 11.2 全栈可插拔扩展点（解决"所有能扩展的都留接口"）
- 新增 `src/kernel/plugins/extension.py`：**统一 opt-in 扩展注册表** `register_extension(name, factory, env_gate=, local_only=, description=)`。
- 范式：env 门控 + 不可达静默跳过（复用 `fabric_hub.register_mcp_server` 思路），任何外部服务都走此机制，不复制样板。
- **WorkRally 接口位已留**：`register_extension("workrally", ..., env_gate="WORKRALLY_TOKEN")`，未购账号时 `get_extension("workrally")` 返回 None 静默跳过，**零腾讯依赖**。未来有账号时只需填 `WorkRallyAdapter` 实现（调 workrally CLI/Open API），映射 `content.workrally` 供内容营销岗可选增强。

### 11.3 5 岗位注册表 + 报表芯粒（解决第2点，已代码落地）
- 新增 `src/kernel/plugins/opc_roles.py`：**OPC 5 岗位智能体注册表**（产品研发/市场调研/内容营销/客户服务/财务核算）。每个岗位映射现有已注册 capability（复用不重造），行业差异走 `knowledge_base` 钩子可插拔。
- 新增 `src/kernel/plugins/report_agent.py`：**财务核算芯粒**（补财务岗工具缺口）。用开源 `openpyxl` 生成 xlsx 报表；`openpyxl` 不可用时自动降级 CSV，**零付费/零闭源依赖**。提供 `bom_cost`/`generate_report`/`profit_estimate`。

### 11.4 验证（诚实边界）
- **已验证（沙箱，12 项单测全过）**：5 岗位结构、报表生成（CSV fallback）、扩展注册与 WorkRally 静默跳过、Ollama 网关 health/list_models/chat 逻辑（mock）。
- **未验证（需主机真环境）**：
  - Ollama 网关真实连本地 Ollama 跑 Qwen/DeepSeek 出 token（需主机装 Ollama + 拉模型）。
  - autopilot/opc 在真实 LLM 任务下派活给 5 岗位并出报表的端到端闭环（沙箱无真 LLM）。
  - autopilot `_zhipu_generate` 直连 zhipu 的硬解耦未做；当前靠现有 `AOS_LLM_MODEL`/`AOS_LLM_BASE_URL` 开关 + 新 ollama 网关兜底，主机设 `AOS_LLM_BASE_URL=http://localhost:11434/v1`、`AOS_LLM_MODEL=qwen3:8b` 即可走开源。

### 11.5 下一步
- 主机装 Ollama + 拉 `qwen3:8b` → `bash start_all.sh` → 浏览器一句话验开源派活闭环。
- 多租户/计费/支付（Phase 2/3）仍待建；是否搭 `content.workrally` 取决于购账号。

---

## 十二、诚实复盘：本轮回填的真实漏洞（2026-07-23 凌晨）

提交 `542d457` 后用户质疑"都弄好了吗"——当场核验发现**之前声称的"开源默认路由"和"5岗位/报表/扩展"并未真正接起来**，是组件写好了但没接线的"东一点西一点"。本轮回填并加测试守护。

### 12.1 查出的 6 个真实漏洞（带行号）
| # | 漏洞 | 证据 | 严重度 |
|---|---|---|---|
| 1 | 规划路径锁死智谱，开源 ollama 进不去 | `autopilot.py` planner 仅 `("ag2","zhipu")` | 🔴 |
| 2 | 反思虽能 ollama 兜底，但顺序是智谱先、ollama 垫底，与"开源默认"反 | 先 `_zhipu_generate` 失败才 `_ollama_generate` | 🔴 |
| 3 | 文档写的 `AOS_LLM_MODEL/AOS_LLM_BASE_URL` 规划/反思代码里**没读**（只在注释） | grep 仅 `mem0_store`/`ag2_adapter` 读，autopilot 不读 | 🟠 |
| 4 | 新建的 `OllamaModelGateway` 抽象**没人调用**，是死子系统 | wiring 建了但 autopilot 走自己的 `_zhipu_generate`/`_ollama_generate` | 🟠 |
| 5 | `opc_roles.py`/`report_agent.py`/`extension.py` **全项目零 import**，死代码 | grep 仅文件内部自引用 | 🔴 |
| 6 | `singlechuang.py` 初版接口对不上（角色 id 错、误用 `ROLES`、`InvokeRequest/ReportAgent` 不存在）→ import 即崩 | 重写前 `opc_roles` 角色 id 为 `product_rd` 等、`report_agent` 无类 | 🔴 |

### 12.2 本轮回填（已代码落地 + 测试守护）
- **开源路由真正接进脑子**：`autopilot.py` 新增 `_openai_compat_generate`（读 `AOS_LLM_BASE_URL`/`AOS_LLM_MODEL`，支持 Ollama/vLLM OpenAI 兼容）+ 统一 `_llm_generate`（**开源优先 → 本机 Ollama → 智谱仅 `AOS_ZHIPU_OPTIN=1` 才 opt-in**）。规划路径加 `planner in ("ollama","open_source","local","auto")` 分支；反思路径改调 `_llm_generate`。文档里的 env 开关现在**真的生效**，不再只是注释。
- **三件套接成活的**：新建 `src/kernel/plugins/singlechuang.py` 编排层，真正 `import` 并消费 `opc_roles`+`report_agent`+`extension`；注册 `opc.orchestrate` 进 `autopilot._dispatch` + `compliance` 能力表；`main.py` 加 `POST /api/opc/plan`。现在三件套不再死代码。
- **修掉初版 self-bug**：`singlechuang.py` 重写对齐真实接口（`product_rd` 等 id、`generate_report`/`bom_cost`/`profit_estimate`、`get_extension`）。
- 测试 `tests/test_singlechuang_platform.py` 扩到 **17 项**，新增 `TestSingleChuangWiring` 5 项专门验证三件套被真实消费（若仍是坏接口会 `ImportError` 崩，现已全过）。

### 12.3 仍然诚实未验证 / 未做（不瞒）
- 端到端：autopilot 在**真实 LLM 任务**下派活 5 岗位 + 出报表，沙箱无真 LLM 未跑（需主机 `bash start_all.sh` + 真 Ollama/智谱）。
- `OllamaModelGateway`（抽象层）与 autopilot 的 `_ollama_generate`（stdlib 直连）是**两条并存的 ollama 路径**：抽象层供 kernel/app 路径，直连供 autopilot 反思兜底。功能不冲突，但确有重复，未来可统一（低优先）。
- 多租户隔离 / 计费 / 支付（Phase 2/3）**仍 ZERO**，未动。
- 老问题仍在：`app.py` 顶部 `brain` 绑架白页风险、仓库 13 个未跟踪杂文件。
