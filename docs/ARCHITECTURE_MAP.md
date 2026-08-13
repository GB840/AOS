# AOS 模块架构地图

> 四层架构总览 + 核心模块职责 + 29 个适配器清单 + 数据流图。

> **视角说明**：本图是 **模块分层视角**（产品 / 内核 / 能力路由 / 基础设施 四层 + 适配器清单），用于厘清"代码模块归哪层、谁调谁"。另两份是不同镜头，非矛盾：
> - `docs/LIFEFORM_OS_WHITEPAPER_V6.md`：**生命体分层视角**（L0–L9 六维 + 宪法，对齐白皮书叙事）。
> - `docs/ARCHITECTURE.md`：**部署拓扑视角**（alpha 控制台 / beta 前端 / gamma 内核 三层进程拓扑）。

---

## 1. 四层架构

```
+=====================================================================+
|                        产 品 层 (danchuang)                         |
|   单创OS 总入口 / OPC 5 岗位智能体 / 创业调度引擎 / 多租户 SaaS    |
+=====================================================================+
        |                           |                          |
        v                           v                          v
+=====================================================================+
|                       内 核 层 (kernel)                             |
|   AOSKernel(生命周期/路由/权限)  |  autopilot(自主闭环)            |
|   FabricHub(能力路由枢纽)        |  evolution/immunity/hippo      |
|   wiring(接线层/插件装配)        |  compliance/causal/distiller   |
+=====================================================================+
        |                           |                          |
        v                           v                          v
+=====================================================================+
|                      能 力 路 由 层 (core/fabric)                   |
|   FabricRegistry(按Capability发现) |  BaseAgentAdapter(合约ABC)    |
|   Capability(40+能力枚举)         |  route_runtime(三级路由策略)  |
+=====================================================================+
        |                           |                          |
        v                           v                          v
+=====================================================================+
|                    基 础 设 施 层 (api / core)                      |
|   api/main.py(FastAPI入口)  |  web/app.py(Streamlit界面)          |
|   aos_mcp(protocol/MCP出口) |  sandbox(沙箱隔离执行)              |
+=====================================================================+
```

---

## 2. 核心模块职责表

### 2.1 内核层 (kernel/)

| 模块 | 类/入口 | 三行职责 |
|------|---------|---------|
| `kernel/kernel.py` | `AOSKernel` | 1. Agent 生命周期管理（register/list/stop）<br>2. 消息路由（send_message 经 route_hook 分发）<br>3. 权限治理（check_permission 默认拒绝零信任） |
| `kernel/autopilot.py` | `run()` | 自主闭环引擎：规划 -> 执行（硬判定）-> 反思（根因诊断）-> 重设计 -> 续跑。含反思记忆（Meta-Trace）跨任务沉淀失败教训 |
| `kernel/evolution.py` | `EvolutionEngine` | 物种进化系统：DNA 编码（代码变更基因化）、变异算子（随机扰动）、Fitness 评估（通过率/覆盖率）、育种（优胜劣汰选父代） |
| `kernel/immunity.py` | `ImmunitySystem` | 免疫系统：异常检测（运行时行为偏差）、自愈（自动回滚/重启）、熔断（故障隔离防蔓延） |
| `kernel/hippo_scroll.py` | `HippoScroll` | 可信记忆：双轨分离（短期工作记忆/长期语义记忆）、分歧收纳（多源记忆冲突调和）、新陈代谢（TTL 自动淘汰过期记忆） |
| `kernel/causal.py` | `CausalWorldModel` | 因果世界模型：Pearl 因果之梯（关联/干预/反事实）、干预认知（what-if 模拟）、反事实推理（如果当时做了 X 会怎样） |
| `kernel/evolution_distiller.py` | `EvolutionDistiller` | 白盒蒸馏：Trace -> 可靠性评分 -> 路由偏好（不可靠引擎自动降权）、经验沉淀（结构化教训持久化） |
| `kernel/compliance.py` | `ComplianceEngine` | 合规安全：审计链（操作可追溯）、脱敏（敏感信息过滤）、策略引擎（规则化安全策略执行） |
| `kernel/wiring.py` | `build_default_kernel()` | 接线层：把真实 OSS 引擎 + 模型网关 + MCP 总线装配进 AOSKernel。重型引擎（agnes/ag2）默认隔离进独立子进程 |
| `kernel/system.py` | `build_default_system()` | 系统组装层：内核 + 四层（ModelGatewayLayer/MCPBusLayer/AgentRuntimeLayer/WebUILayer）装配成完整 AOSSystem |
| `kernel/plugins/fabric_hub.py` | `FabricHub` | 能力路由枢纽：29+ 适配器注册、故障转移（云端优先->本地兜底）、三级路由策略、白盒蒸馏降权、记忆门面（mem0 双后端） |
| `kernel/plugins/orchestration_chiplet.py` | `OrchestrationChiplet` | 编排芯粒：steps[] 逐跳经 hub 路由的流水线执行器，支持 parallel_groups 组内并发 |
| `kernel/aos.py` | `python -m kernel.aos` | CLI 统一入口：意图解读 -> 环境探测 -> 多方案生成 -> 选方案 -> 执行 -> 汇报 |
| `kernel/events.py` | `EventBus` | 事件总线：内核关键路径事件发射（agent.registered/message.routed/message.denied 等） |

### 2.2 能力路由层 (core/fabric/)

| 模块 | 类/入口 | 职责 |
|------|---------|------|
| `core/fabric/registry.py` | `FabricRegistry` | 能力注册表：按 Capability 发现引擎、偏好策略（learned/static）、outcome 记录与重训触发 |
| `core/fabric/adapter.py` | `BaseAgentAdapter` ABC | 适配器合约：engine_id / advertise_capabilities() / invoke() / health() 四个必须实现的方法 |
| `core/fabric/capability.py` | `Capability` 枚举 | 能力枚举：40+ 标签（web.search / inference.llm / memory.semantic / code.generate / media.image / ...） |
| `core/fabric/route_runtime.py` | `build_route_runtime()` | 路由策略运行时：preference（静态偏好表）/ learned（基于历史 outcome 训练）两种策略 |

### 2.3 产品层 (danchuang/)

| 模块 | 职责 | 状态 |
|------|------|------|
| `danchuang/core.py` | 单创OS 总入口：融合 OPC 内核 + 创业调度引擎 + 多租户底座 | 规划中 |
| `danchuang/engine/` | 创业调度引擎：目标拆解 -> 任务调度 -> 进度跟踪 -> 成果交付 | 规划中 |
| `danchuang/tenant/` | 多租户 SaaS：租户隔离 / 计费 / BYOK（自带密钥） | 规划中 |

> 产品层（danchuang）为 2026-07-23 用户明示的战略升级方向，代码层面尚未独立成包。
> 当前产品能力由 kernel 层的 autopilot + fabric_hub + OPC 循环提供支撑。

---

## 3. 29 个适配器清单

适配器按 `engine_id` 注册进 FabricHub，由 `Capability` 枚举声明能力标签，
内核路由层按能力匹配 -> 偏好排序 -> 故障转移。

| # | engine_id | 适配器类 | 核心能力 | 档位 | 说明 |
|---|-----------|----------|---------|------|------|
| 1 | openclaw | OpenClawAdapter | media.image, media.video | HIGH | 本地自托管网关（127.0.0.1:18789），MIT 免费 |
| 2 | ag2 | AG2Adapter | cognition.planning, cognition.reasoning | HIGH | AutoGen 多 Agent 框架（隔离子进程） |
| 3 | litellm | LiteLLMAdapter | inference.llm | MEDIUM | 云 100+ 模型兜底（opt-in，需 ZHIPU_API_KEY） |
| 4 | mem0 | Mem0Adapter | memory.semantic | MEDIUM | 记忆系统（默认本地 ollama+chroma，零成本） |
| 5 | browser-use | BrowserUseAdapter | action.aci, web.browse | HIGH | ACI 浏览器自动化 |
| 6 | langfuse | LangfuseAdapter | observability.trace | LOW | LLM 可观测性（trace 日志） |
| 7 | web-search | SearchAdapter | web.search | HIGH | 多源搜索（DuckDuckGo + AnySearch + 百度/Bing） |
| 8 | web-fetch | WebFetchAdapter | web.fetch | HIGH | URL 内容抓取（stdlib urllib，零依赖） |
| 9 | crawl4ai | Crawl4AIAdapter | web.crawl | MEDIUM | 网页爬取转 LLM 友好 Markdown（需 pip install） |
| 10 | media-gen | MediaGenAdapter | media.image, media.video | MEDIUM | 国产文生图/视频（智谱 CogView-4 + CogVideoX） |
| 11 | agnes | AgnesAdapter | inference.llm, vision.understand | HIGH | 多模态平面（需 AGNES_API_KEY，隔离子进程） |
| 12 | code-exec | CodeExecutionAdapter | code.execute | HIGH | 本地沙箱代码执行（subprocess 隔离） |
| 13 | file-io | FileAdapter | file.read, file.write | HIGH | 文件读写（workspace 内，路径遍历防护） |
| 14 | threejs | ThreejsAdapter | media.3d | LOW | 交互式 3D 场景生成（浏览器端渲染） |
| 15 | stt | STTAdapter | voice.stt | MEDIUM | 语音识别（whisper.cpp/faster-whisper/Web Speech） |
| 16 | tts | TTSAdapter | voice.tts | MEDIUM | 语音合成（kokoro/edge-tts/XTTS/Web Speech） |
| 17 | lnn | LNNAdapter | inference.lnn | LOW | 液态神经网络时间序列推理（纯 numpy） |
| 18 | lfm2 | LFMAdapter | inference.llm | LOW | LFM2 轻量 LLM（低功耗一极） |
| 19 | scripts | ScriptsAdapter | code.script | MEDIUM | 动态脚本执行（scripts/repls/*.py 热加载） |
| 20 | minicpm-o | MiniCPMOAdapter | voice.omni | MEDIUM | MiniCPM-o 4.5 全双工全模态推理 |
| 21 | vlm | VLMAdapter | vision.understand | MEDIUM | 视觉理解（云端/本地 ollama MiniCPM-V-2） |
| 22 | video-maker | VideoMakerAdapter | media.video | LOW | 本地视频生成（edge-tts + PIL + ffmpeg） |
| 23 | remotion | RemotionAdapter | media.video.render | LOW | 高质量数据可视化视频渲染（Remotion CLI） |
| 24 | security-audit | SecurityAuditAdapter | security.audit | LOW | 防御型本地漏洞自查（只读，公开 CVE 元数据） |
| 25 | code-team | CodeTeamAdapter | code.generate | HIGH | 多智能体代码团队（hub 统一路由） |
| 26 | comfyui | ComfyUIAdapter | media.image, media.video | HIGH | 本地 ComfyUI 视觉生产引擎 |
| 27 | content-director | ContentDirector | content.produce | HIGH | 内容生产导演（一句话目标 -> 自主编排全链路） |
| 28 | content-marketer | ContentMarketerAdapter | content.produce | MEDIUM | 内容营销适配器 |
| 29 | orchestrator | OrchestrationChiplet | system.workflow | HIGH | 编排芯粒（steps[] 流水线执行器） |

**动态注册芯粒**（通过 MCP 协议即插即用，按需出现）：

| engine_id | 能力 | 触发方式 |
|-----------|------|---------|
| mcp-{name} | 由 capability_map 映射 | `AOS_MCP_SERVERS` 环境变量配置 |
| weknora | data.query, memory.knowledge | `WEKNORA_MCP_URL` 环境变量 |
| ida-pro-mcp | re.ida | `IDA_PRO_MCP_URL`（仅 localhost） |
| desktop-touch | action.aci | `DESKTOP_TOUCH_MCP_ENABLED=1` |
| omni-video | media.video | `OMNI_VIDEO_MCP_ENABLED=1` |
| video-use | media.video | `VIDEO_USE_MCP_ENABLED=1` |
| codebase-memory-mcp | code.understanding | 二进制存在即自动注册 |

---

## 4. 数据流图

```
用户请求
  |
  v
+------------------+
| API / CLI / Web   |  api/main.py | kernel/aos.py | web/app.py
+------------------+
  |
  v
+------------------+
| FabricHub         |  kernel/plugins/fabric_hub.py
|  .route(cap, payload)
|  1. resolve_engine(cap)         -- 按能力找 live 引擎
|  2. providers_for(cap, tier)    -- 三级路由（云端/本地/全量）
|  3. reorder_by_distiller()      -- 蒸馏降权（可选）
|  4. adapter.invoke(req)         -- 逐个尝试，故障转移
+------------------+
  |
  |--- 成功 ---> InvokeResult(ok=True, data=..., engine_id=...)
  |--- 失败 ---> 尝试下一个 live provider
  |--- 全部失败 -> InvokeResult(ok=False, data=last_res.data, error=...)
  |
  v
+------------------+
| Adapter 执行层    |  core/fabric/adapters/*.py
|  - 进程内适配器   |  SearchAdapter / CodeExecAdapter / ...
|  - 子进程隔离     |  IsolatedEngineHost (agnes / ag2)
|  - MCP 协议       |  MCPClientAdapter / MCPStdioAdapter
+------------------+
  |
  v
+------------------+
| 结果返回          |  含真实 stdout / exit_code / 相似度分数
|  + 诚实自检       |  health_report() 如实报告 live/dead
|  + 可观测 Trace   |  outcome 记录喂路由预测器
+------------------+
```

### 4.1 反思闭环数据流（autopilot）

```
任务输入
  |
  v
[规划] -> LLM/AG2 生成 plan -> 解析为 steps
  |
  v
[执行] -> OrchestrationChiplet 逐跳 route()
  |
  v
[硬判定] -> 每步检查：stdout 非空？exit_code==0？文件落盘？
  |
  |--- 成功 ---> 记录 success -> 下一步
  |--- 失败 ---> 触发反思
  |
  v
[反思] -> 质疑 agent 用 trace 诊断根因 -> 产出修正计划
  |
  v
[重设计] -> 只重设计失败处的剩余步骤（不重跑已成功的）
  |
  v
[续跑] -> 新计划执行 -> 再次硬判定
  |
  |--- 最多 3 轮（MAX_REFLECT=2 额外反思）--->
  |
  v
最终结果 + 反思记忆沉淀（_traces/reflection_memory.jsonl）
```

### 4.2 白盒蒸馏闭环

```
真实路由流量
  |
  v
outcome 记录（ok/fail/error）---> _traces/evolution_distiller.jsonl
  |
  v
EvolutionDistiller.distill()  -- 按 capability+engine 聚合成功率
  |
  v
沉底建议（不可靠引擎列表）
  |
  v
route() 消费端：
  - 不可靠引擎排到 providers 列表末尾
  - AOS_DISTILLER_DROP=1 + 有可靠备选时硬跳过
```

---

## 5. 关键设计原则

| 原则 | 落点 |
|------|------|
| 内核零依赖 | kernel.py 只 import 标准库 + 同包 types/interfaces，具体引擎都是插件 |
| 依赖倒置 | 内核只认 ABC（BaseAgentAdapter），真实引擎经 wiring.py 注入 |
| 故障隔离 | 重型引擎（agnes/ag2）跑在独立子进程，崩溃不传染宿主 |
| 能力路由 | 适配器通过 advertise_capabilities() 声明能力，内核按标签调度 |
| 诚实自检 | health_report() 如实报告 live/dead，resolve_engine() 绝不返回未通电引擎 |
| 万物为我所用 | 任何支持 MCP 的外部服务都能经协议级接入成为 AOS 供给方 |
