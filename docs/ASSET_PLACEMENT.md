# AOS 开源资产归位目录 (Asset Placement Map)

> 用户决策 (2026-07-08)：仓库内 agents/skills 均为开源可复用构件，
> 归位到 DeerFlow 子智能体 / 技能 或 对应基建平面，不重造。

## 统计

- 子智能体 (sub-agents): **7** → DeerFlow 子智能体
- 领域技能 (skills): **34**
  - DeerFlow 技能: 19
  - Mem0 平面 (记忆/知识): 5
  - browser-use 平面 (UI 自动化): 7
  - fabric 自举能力 (元技能): 3
- 角色模板 (agency_roles): **266** → DeerFlow 子智能体角色模板
- DeerFlow 子智能体注册项合计: **273**

## 子智能体 → DeerFlow 子智能体

| 名称 | 源码 | 说明 |
|---|---|---|
| `lobster_agent` | `src/subagents/lobster_agent.py` | LobsterAI 子智能体 — 通过 OpenClaw ACP 桥接网易有道 LobsterAI 的办公自动化能力. |
| `loop_engineering_agent` | `src/subagents/loop_engineering_agent.py` | Loop Engineering Subagent - 循环工程子智能体. |
| `pixelle_agent` | `src/subagents/pixelle_agent.py` | Pixelle-Video Subagent - 短视频自动化生产线子智能体 |
| `ruflo_agent` | `src/subagents/ruflo_agent.py` | RuFlo Subagent - 多智能体编排子智能体 |
| `skill_agent` | `src/subagents/skill_agent.py` | 技能子智能体包装器 - 将任意技能自动转换为子智能体. |
| `uitars_agent` | `src/subagents/uitars_agent.py` | UI-TARS 子智能体 — 通过子进程/MCP 桥接字节跳动的 GUI 自动化 Agent. |
| `vimax_agent` | `src/subagents/vimax_agent.py` | ViMax Subagent - 多智能体视频生成子智能体 |

## 角色模板 → DeerFlow 子智能体角色模板 (节选前 40)

| 名称 | 源码 | 说明 |
|---|---|---|
| `aeo_基础架构师` | `src/skills/agency_roles/aeo_基础架构师.py` | [marketing] AI 引擎优化基础设施专家——落地 llms.txt、AI 感知的 robots.txt、token |
| `ai_工程师` | `src/skills/agency_roles/ai_工程师.py` | [engineering] 精通机器学习模型开发与部署的 AI 工程专家，擅长从数据处理到模型上线的全链路工程化，专注构建可靠、 |
| `ai_引文策略师` | `src/skills/agency_roles/ai_引文策略师.py` | [marketing] AI 推荐引擎优化（AEO/GEO）专家，审计品牌在 ChatGPT、Claude、Gemini、P |
| `ai_数据修复工程师` | `src/skills/agency_roles/ai_数据修复工程师.py` | [engineering] 自愈数据管道专家——使用气隙隔离的本地 SLM 和语义聚类，自动检测、分类和修复大规模数据异常。专注 |
| `ai_治理政策专家` | `src/skills/agency_roles/ai_治理政策专家.py` | [specialized] 面向中国企业和机构的 AI 治理与合规专家，精通《生成式 AI 管理办法》、算法备案制度、深度合成管 |
| `api_测试员` | `src/skills/agency_roles/api_测试员.py` | [testing] 专注于全面 API 验证、性能测试和质量保证的 API 测试专家，覆盖所有系统和第三方集成 |
| `backend_architect` | `src/skills/agency_roles/backend_architect.py` | [mcp-memory] Senior backend architect specializing in scalable  |
| `bimgis_专家` | `src/skills/agency_roles/bimgis_专家.py` | [gis] 整合专家，打通 BIM（建筑信息模型）与 GIS（地理信息系统）——负责 Revit/IFC 数据转 |
| `blender_插件工程师` | `src/skills/agency_roles/blender_插件工程师.py` | [blender] Blender 工具专家——构建 Python 插件、资源验证器、导出工具和管线自动化，把重复的 D |
| `b站内容策略师` | `src/skills/agency_roles/b站内容策略师.py` | [marketing] 专注B站（哔哩哔哩）平台的中长视频内容策略专家，精通UP主运营、弹幕文化、社区生态、品牌合作、推荐算 |
| `cms_开发者` | `src/skills/agency_roles/cms_开发者.py` | [engineering] Drupal 与 WordPress 专家，精通主题开发、自定义插件/模块、内容架构和代码优先的 C |
| `devops_自动化师` | `src/skills/agency_roles/devops_自动化师.py` | [engineering] 精通基础设施自动化、CI/CD 流水线开发和云运维的 DevOps 专家 |
| `discovery_教练` | `src/skills/agency_roles/discovery_教练.py` | [sales] 销售方法论专家，辅导团队掌握高阶 Discovery 技巧——问题设计、现状诊断、差距量化和通话结构 |
| `drupal_购物车工程师` | `src/skills/agency_roles/drupal_购物车工程师.py` | [engineering] 资深 Drupal 电商工程师，精通 Drupal Commerce，负责商品目录管理、支付网关集成 |
| `esg_与可持续发展官` | `src/skills/agency_roles/esg_与可持续发展官.py` | [specialized] 企业可持续发展战略专家与 ESG 信息披露专员，负责搭建 environmental、social、 |
| `filament_优化专家` | `src/skills/agency_roles/filament_优化专家.py` | [engineering] 专精于重构和优化 Filament PHP 后台管理界面的专家，专注高影响力的结构性改造，而非表面调 |
| `fpa_分析师` | `src/skills/agency_roles/fpa_分析师.py` | [finance] 专业财务规划与分析（FP&A）专家，精通预算编制、差异分析、财务规划、滚动预测和战略决策支持。在数字 |
| `fpgaasic_数字设计工程师` | `src/skills/agency_roles/fpgaasic_数字设计工程师.py` | [engineering] FPGA 与 ASIC 数字前端设计专家——精通 Verilog/SystemVerilog、VHD |
| `geoaiml_工程师` | `src/skills/agency_roles/geoaiml_工程师.py` | [gis] 地理空间机器学习专家，构建模型从卫星与航拍影像中做特征提取、目标检测、影像分割和地表覆盖分类。 |
| `gis_分析师` | `src/skills/agency_roles/gis_分析师.py` | [gis] 日常 GIS 操作员，负责制图、图层管理、空间查询，并在桌面与 Web 环境中维护地理空间数据的完整 |
| `gis_质检工程师` | `src/skills/agency_roles/gis_质检工程师.py` | [gis] 质量保证专家，负责校验地理空间数据的完整性——拓扑检查、元数据审计、CRS 一致性、精度评估与合规验 |
| `git_工作流大师` | `src/skills/agency_roles/git_工作流大师.py` | [engineering] Git 工作流专家，精通分支策略、版本控制最佳实践，包括约定式提交、变基、工作树和 CI 友好的分支 |
| `godot_shader_开发者` | `src/skills/agency_roles/godot_shader_开发者.py` | [godot] Godot 4 视觉效果专家——精通 Godot 着色语言（类 GLSL）、VisualShader |
| `godot_多人游戏工程师` | `src/skills/agency_roles/godot_多人游戏工程师.py` | [godot] Godot 4 网络专家——精通 MultiplayerAPI、场景复制、ENet/WebRTC 传 |
| `godot_游戏脚本开发者` | `src/skills/agency_roles/godot_游戏脚本开发者.py` | [godot] 组合与信号完整性专家——精通 GDScript 2.0、C# 集成、节点式架构和类型安全信号设计，面 |
| `hr_入职管理专家` | `src/skills/agency_roles/hr_入职管理专家.py` | [specialized] 全面的 HR 入职管理专家，负责员工迎新、文档管理、合规追踪、福利登记、文化融入和新员工支持——打造 |
| `instagram_策展师` | `src/skills/agency_roles/instagram_策展师.py` | [marketing] Instagram 营销专家，适合出海营销场景。擅长视觉叙事、社区运营和多格式内容优化，打造品牌美学 |
| `iot_方案架构师` | `src/skills/agency_roles/iot_方案架构师.py` | [engineering] 物联网端到端方案设计专家——精通设备接入（MQTT/CoAP/LwM2M）、边缘计算、云平台（AWS |
| `it_服务经理` | `src/skills/agency_roles/it_服务经理.py` | [engineering] 资深 IT 服务管理（ITSM）专家，运用 ITIL 4 框架进行服务目录设计、incident（事 |
| `jira工作流管家` | `src/skills/agency_roles/jira工作流管家.py` | [project-management] 交付运营专家，执行Jira关联的Git工作流，确保提交可追溯、PR结构规范、分支策略安全可控。 |
| `linkedin_内容创作专家` | `src/skills/agency_roles/linkedin_内容创作专家.py` | [marketing] 专注于 LinkedIn 个人品牌打造和专业内容创作的策略师，深谙 LinkedIn 算法与社区文化 |
| `lsp_索引工程师` | `src/skills/agency_roles/lsp_索引工程师.py` | [specialized] Language Server Protocol 专家，通过 LSP 客户端编排和语义索引构建统一的 |
| `ma_整合经理` | `src/skills/agency_roles/ma_整合经理.py` | [specialized] 并购(M&A)整合专家，负责设计并执行并购后整合(PMI)项目——涵盖 Day 1 就绪、百日计划、 |
| `macos_metal_空间工程师` | `src/skills/agency_roles/macos_metal_空间工程师.py` | [spatial-computing] 原生 Swift 和 Metal 专家，构建高性能 3D 渲染系统和空间计算体验，覆盖 macOS  |
| `mcp_构建器` | `src/skills/agency_roles/mcp_构建器.py` | [specialized] Model Context Protocol 开发专家，设计、构建和测试 MCP 服务器，通过自定义 |
| `offer_与_lead_gen_策略师` | `src/skills/agency_roles/offer_与_lead_gen_策略师.py` | [sales] 漏斗顶端（top-of-funnel）架构师，设计无法抗拒的 offer 和 lead magnet |
| `orgscript_工程师` | `src/skills/agency_roles/orgscript_工程师.py` | [engineering] 精通 OrgScript 语法的设计、解析与实现，擅长 AST 校验和业务逻辑定义。 |
| `outbound_策略师` | `src/skills/agency_roles/outbound_策略师.py` | [sales] 基于信号的 Outbound 专家，设计多渠道触达序列、定义 ICP、通过调研驱动的个性化开发 Pi |
| `persona_走查专家` | `src/skills/agency_roles/persona_走查专家.py` | [design] 从设定好的 persona（用户画像）心理视角出发，对网页进行认知走查的模拟——捕捉每个滚动位置上的 |
| `pipeline_分析师` | `src/skills/agency_roles/pipeline_分析师.py` | [sales] 收入运营分析师，专精 Pipeline 健康诊断、单子速度分析、Forecast 准确度和数据驱动的 |
| … | … | 其余 226 个角色同结构省略 |

## 领域技能 → 按平面归位

### DeerFlow 技能 (19)

| 名称 | 源码 | 说明 |
|---|---|---|
| `duckduckgo_search` | `src/skills/duckduckgo_search.py` | [?]  |
| `engineering` | `src/skills/engineering.py` | [?]  |
| `frontend_design` | `src/skills/frontend_design.py` | [?] Frontend Design - Production-Grade Dashboard & HTML Generato |
| `herdr` | `src/skills/herdr.py` | [agent] Herdr — 多Agent终端管理，允许同时运行并管理多个AI编码Agent |
| `j_stack` | `src/skills/j_stack.py` | [?] J Stack - 23 Expert Roles Skill Library. |
| `jina_reader` | `src/skills/jina_reader.py` | [web] Jina Reader 网页正文提取 — 将任意URL转换为干净的Markdown或JSON，免费额度充足 |
| `lingbot_map` | `src/skills/lingbot_map.py` | [vision] Lingbot-Map — 实时3D重建能力，支持机器人、AR/VR场景的点云处理和场景建模 |
| `llama_cpp` | `src/skills/llama_cpp.py` | [ai] Llama.cpp 推理引擎 — Windows原生，最快CPU推理，支持GGUF量化模型，8GB内存最优解 |
| `loop_engineering` | `src/skills/loop_engineering.py` | [?] Loop Engineering Skill Module - 循环工程框架 |
| `monitoring` | `src/skills/monitoring.py` | [?]  |
| `no_mistakes` | `src/skills/no_mistakes.py` | [engineering] No-Mistakes — AI驱动的代码质量自动把关，在代码推送前自动运行验证流程 |
| `ollama` | `src/skills/ollama.py` | [ai] Ollama 本地大模型 — 运行Qwen、DeepSeek等模型，全程本地、无Token费用，支持与Llama.cpp |
| `omni_route` | `src/skills/omni_route.py` | [ai] OmniRoute — 智能省钱网关，统一接口连接231家AI提供商，支持4级智能降级 |
| `ruflo` | `src/skills/ruflo.py` | [development] RuFlo 多智能体编排平台 — 为 AI 开发团队提供神经系统 |
| `sandbox` | `src/skills/sandbox.py` | [?]  |
| `searxng` | `src/skills/searxng.py` | [search] SearXNG 元搜索引擎 — 聚合70+搜索引擎结果，支持多种搜索类型，完全免费无限制 |
| `versioning` | `src/skills/versioning.py` | [?]  |
| `video_use` | `src/skills/video_use.py` | [video] Video-Use — 对话式视频剪辑，AI通过自然语言指令自动完成视频编辑 |
| `viitor_voice` | `src/skills/viitor_voice.py` | [audio] ViiTorVoice 中文语音编辑 — 片段级局部编辑，像改Word一样修语音，中文词错率0.99全球第一 |

### fabric 自举能力 (元技能) (3)

| 名称 | 源码 | 说明 |
|---|---|---|
| `learning` | `src/skills/learning.py` | [?]  |
| `skill_creator` | `src/skills/skill_creator.py` | [?] Skill Creator — AOS 元技能。 |
| `superpowers` | `src/skills/superpowers.py` | [?] Superpowers — "流程大于提示词"的技能框架。 |

### browser-use 平面 (UI 自动化) (7)

| 名称 | 源码 | 说明 |
|---|---|---|
| `comfyui` | `src/skills/comfyui.py` | [content_generation] ComfyUI 视觉内容生产引擎 — 文生图、图生视频、风格迁移、视频生视频 |
| `design_md` | `src/skills/design_md.py` | [design] Design.md — UI/UX设计标准化规范知识库，让AI生成符合设计规范的前端代码 |
| `open_montage` | `src/skills/open_montage.py` | [video] OpenMontage — 视频生产流水线，12条专业流水线、52种工具、500+技能，创意到视频自动化 |
| `pixelle_video` | `src/skills/pixelle_video.py` | [content_generation] Pixelle-Video 短视频自动化生产线 — 从文案到成片的端到端自动化，支持抖音/快手/B站风格 |
| `ui_ux_promax` | `src/skills/ui_ux_promax.py` | [?] UI/UX Pro Max - Complete Design System Generator. |
| `uitars` | `src/skills/uitars.py` | [automation] UI-TARS 桌面自动化 — 字节跳动开源GUI Agent，看懂屏幕、操控鼠标键盘 |
| `vimax` | `src/skills/vimax.py` | [content_generation] ViMax 多智能体视频生成框架 — 从创意到成片的端到端自动化 |

### Mem0 平面 (记忆/知识) (5)

| 名称 | 源码 | 说明 |
|---|---|---|
| `codebase_memory` | `src/skills/codebase_memory.py` | [development] Codebase Memory MCP — 将代码库索引成知识图谱，提供语义搜索、调用链追踪、架构分析等14个代码分析工 |
| `codebase_memory_mcp` | `src/skills/codebase_memory_mcp.py` | [development] Codebase Memory MCP — 项目级长期记忆引擎，将代码库解析为知识图谱，Token消耗降低99% |
| `cognee` | `src/skills/cognee.py` | [memory] Cognee — 知识图谱记忆层，支持对话/文档转化为长期记忆，提供知识图谱推理能力 |
| `lightrag` | `src/skills/lightrag.py` | [knowledge] LightRAG 本地知识图谱 — 基于ChromaDB的轻量级向量数据库，支持向量检索、知识图谱和混合搜索 |
| `zvec` | `src/skills/zvec.py` | [knowledge] Zvec 嵌入式向量数据库 — 阿里巴巴开源，向量数据库领域的SQLite，零依赖进程内运行 |
