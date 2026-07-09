# brain.py 逐方法处置表

> 生成于 2026-07-10。逐方法判定「真决策 / 纯胶水 / 死代码」,给出收敛处置。
> 依据:AOS 铁律 = "不重造大脑,只做接线板"。决策逻辑 = 大脑,必须迁给 fabric 或砍;装配/转发 = 接线板,保留。

## 0. brain.py 体系全景(实测行数)

| 部分 | 行数 | 性质 |
|---|---|---|
| `DeerFlowGatewayClient` (brain.py:29-599) | ~570 | 协议翻译(胶水) |
| `UnifiedBrain` 初始化 `_init_*` (602-1021) | ~400 | 装配器(胶水) |
| `UnifiedBrain` 路由 `chat/_route_*` (1364-1782) | ~420 | **路由大脑(决策)** |
| 7 个大脑子模块 (task_classifier 等) | 1850 | **自研编排(决策)** |
| **合计** | **~3240** | |

**结论:brain.py 是三个东西焊在一起 —— 一个装配器(合法)、一个 HTTP client(合法但放错位置)、一个路由大脑(违反铁律)。**

---

## 1. DeerFlowGatewayClient (brain.py:29-599) — 协议翻译层

| 方法 (行) | 性质 | 处置 | 依据 |
|---|---|---|---|
| `_ensure_session`/`_api_request`/`_login` (54-110) | 胶水 | **保留** | 合法的 HTTP 客户端 |
| `_login` 兜底 `admin/aos123456` (91-94) | **隐患** | **删兜底,读不到配置就报错** | 明文口令残留 |
| `_build_run_payload`/`_extract_answer` (115-158) | 胶水 | **保留** | 翻译 AOS↔DeerFlow 2.x |
| `run`/`chat`/`stream` (174-260) | 胶水 | **保留** | 阻塞/SSE 调用 |
| `_chat_legacy` (262-288) | 死路径 | **删** | 1.x 降级,2.x 已为主路径,保留是负债 |
| catalog/memory (293-342) | 胶水 | **保留** | 透传 GET/POST |
| `submit_task`/`list_tasks`/... (347-411) | **混合** | **瘦身**:线程池逻辑迁出 | 自己管任务生命周期=决策,应走事件总线 |
| `_sandbox/guardrails/agents/subagent_bridge` (418-436) | 死代码 | **删** | 全返回 None |
| subagent 执行 (453-599) | 胶水 | **保留** | 经 HTTP 委派给后端 |

**整块处置:搬到独立文件 `src/deerflow/gateway_client.py`,brain.py 不该装 HTTP 客户端。预计 brain.py 瘦身 ~570 行。**

---

## 2. UnifiedBrain 初始化 (brain.py:602-1021) — 装配器

合法的接线板职责。但有两类问题:

### 2a. 纯装配(保留)

`_init_persistence` `_init_memory` `_init_skill_sync` `_init_mcp_protocol` `_init_compliance` `_init_identity` `_init_audit_startup` `_init_router` `_init_fabric` `_init_mem0_store` `_init_langfuse_tracer` —— 全是"实例化并挂到 self",**保留**。

`_init_real_hermes` (1026-1089):命名空间暂存/还原 hack 是真实集成的代价,**保留**但应提取成 `hermes/namespace_isolation.py` 工具函数,别埋在 brain 里。

`_init_real_deerflow` (1109-1153):三级降级(gateway→scheduler→inert)是合理的健壮性设计,**保留**。

`_init_execution_layer` + `_integrate_execution_with_deerflow` (1158-1262):注册 5 个工具,**保留**,但 5 个 `register_handler` 重复注册(tool_executor + deerflow 各一遍)应抽成循环。

### 2b. 挂载大脑(应剥离)

这些 `_init_*` 把**决策器**挂到 brain 上 —— 它们是大脑的装配点,本身是胶水,但挂的东西是大脑:

| 方法 (行) | 挂载的决策器 | 处置 |
|---|---|---|
| `_init_task_classifier` (800) | TaskClassifier (233行) | 见 §4-1 |
| `_init_meta_debate` (806) | MetaDebate (246行) | 见 §4-2 |
| `_init_meta_orchestrator` (893) | MetaOrchestratorEngine | 见 §4-3 |
| `_final_initialization_check` 内 LEMON/SwarmFlow/TaskFingerprint/AgentCARD/Negotiation/FinalDelivery (960-1013) | 6 个决策器(1620行) | 见 §4 |

### 2c. 直接删(死代码 / 空操作)

| 方法 (行) | 问题 | 处置 |
|---|---|---|
| `_init_deep_hermes` (790) | 只设 `self._deep_hermes_enabled=True`,无任何消费方 | **删** |
| `_init_deep_deerflow` (795) | 同上 | **删** |
| `_register_subagents` UITARS 块 (1273-1290) | **重复注册两次**相同代码 | **删第二个** |
| chat() 日期硬编码 if (1374-1387) | "今天几号"等 8 个模式硬编码,本该交给 LLM | **删**,交给 `_route_l1` |

### 2d. 应改为数据

| 方法 (行) | 问题 | 处置 |
|---|---|---|
| `_init_skills_registry` (686-733) | 硬编码 24 个 skill 类 import + 列表 | **改为自动发现**:扫 `src/skills/*.py`,凡 `Skill` 子类自动注册 |

---

## 3. UnifiedBrain 路由 (brain.py:1364-1782) — **路由大脑(核心违规区)**

这是 brain.py 的灵魂,也是铁律违规最重的地方。

### 3a. 入口与降级(保留)

| 方法 (行) | 性质 | 处置 |
|---|---|---|
| `chat()` 分发 (1364-1438) | 编排入口 | **保留骨架,瘦身**:见 §5 |
| `_llm_cloud_fallback` (1440) | 降级胶水 | **保留** |
| `_route_l1` (1469) | 调 hermes | **保留**(纯转发) |
| `_route_deerflow_skill` L6 (1637) | 转发给 deerflow | **保留**(纯转发) |
| `_route_l3_5` (1672) | 进化通道+人工门控 | **保留**(有安全门控,设计正确) |

### 3b. 真决策(必须迁给 fabric 或重写)

| 方法 (行) | 在决策什么 | 处置 |
|---|---|---|
| `_route_l2` (1497) | 选 1 角色 + 查 fingerprint 模板 | **迁**:角色匹配→fabric `TOOL_USE` 路由;模板复用→Mem0 |
| `_route_l3` (1516) | 选主+辅角色 + 协商 + 综合 | **迁**:多角色协作→AG2 group chat |
| `_route_l4` (1544) | 元辩论+LEMON spec+SwarmFlow 执行 | **砍最重**:这是自研编排引擎,应整体由 DeerFlow LangGraph 工作流替代 |
| `_route_l5` (1585) | 项目拆解(调 LLM)+递归 | **简化**:保留"拆解→递归"骨架,拆解提示词抽成数据;递归调度走 fabric |
| `_find_best_single_role` (1703) | skill_registry.search 包装 | **迁**:fabric capability 匹配 |
| `_find_main_and_support_roles` (1710) | 同上 | **迁** |
| `_synthesize_results` (1719) | 多角色结果综合 | **迁**:AG2 manager 的 summary |
| `_decompose_project` (1735) | 调 LLM + JSON 解析 | **保留**(薄),提示词抽数据 |
| `_synthesize_project_results` (1770) | 字符串拼接 | **保留**(纯格式化) |

---

## 4. 7 个大脑子模块(1850 行)— 逐个判决

| 模块 (行数) | 干什么 | 判决 | 替代方案 |
|---|---|---|---|
| **task_classifier** (233) | 把消息分到 L1-L5 | **改写进 fabric** | fabric 已有 capability 路由;L1-L5 分级→capability 映射表(数据) |
| **meta_debate** (246) | 角色 self-pitch + peer review + 投票 | **砍**,用 AG2 替代 | `AG2Adapter` 的 GroupChat 本就是多角色辩论+收敛 |
| **swarm_flow** (252) | 自研工作流引擎(spec→步骤→执行) | **砍**,用 DeerFlow 替代 | DeerFlow 后端就是 LangGraph 工作流引擎 |
| **lemon_orchestrator** (225) | 自动生成编排 spec | **砍** | DeerFlow/LangGraph 的 planner 节点;或 LLM + 简单模板 |
| **task_fingerprint** (200) | 任务指纹 + 模板复用 | **降级给 Mem0** | 这是"做过的事记住下次复用"=语义记忆,Mem0 的职责 |
| **agent_card** (324) | 成本-精度优化(小模型→大模型) | **砍**,用 LiteLLM 替代 | LiteLLM 的 router 自带 model fallback/cost routing |
| **negotiation** (370) | 主辅角色协商 + L4 终审交付 | **砍协商,留交付** | 协商→AG2;终审交付(质量审核+打包)保留为独立服务 |

**净效果:1850 行 → 约 0~200 行(只留"终审交付"服务 + L1-L5→capability 映射表)。**

---

## 5. 收敛后的 brain.py 长什么样

```
brain.py (~250 行,纯装配 + 转发)
├── UnifiedBrain.__init__       # 只跑 _init_* 装配,不挂决策器
├── chat(message)               # 入口:capability 推断 → fabric.route() → 回退 L1
├── _route_l1(message)          # 转发给 hermes
├── stream/memory/health/stats  # 转发方法
└── _llm_cloud_fallback         # 降级

decision logic 全部外移:
├── fabric (capability 路由)           ← 取代 task_classifier + role 匹配
├── AG2 group chat (多角色协作)        ← 取代 meta_debate + negotiation
├── DeerFlow (长时工作流)              ← 取代 swarm_flow + lemon
├── Mem0 (记忆复用)                    ← 取代 task_fingerprint
├── LiteLLM router (模型选择)          ← 取代 agent_card
└── delivery_service.py (终审交付)     ← 从 negotiation 拆出保留
```

**从 ~3240 行 → ~250 行。删掉的 ~3000 行决策逻辑,全部由 fabric 接入的真实开源引擎承担。这才符合"接线板"铁律。**

---

## 6. 执行顺序建议(风险从低到高)

1. **零风险清理**(可立即做):删 `_init_deep_hermes/deerflow`、删重复 UITARS 块、删日期硬编码、删 `_chat_legacy`、删 4 个 `_xxx_bridge` 死属性、删 `_login` 明文兜底。
2. **搬家**(低风险):DeerFlowGatewayClient → `deerflow/gateway_client.py`;命名空间 hack → `hermes/namespace_isolation.py`。
3. **数据化**(低风险):skill 自动发现;角色模板 → YAML;L1-L5→capability 映射表。
4. **砍大脑**(高风险,逐个验证):agent_card → LiteLLM;task_fingerprint → Mem0;meta_debate → AG2;swarm_flow/lemon → DeerFlow;最后 task_classifier → fabric 映射。
5. **收口**:L2-L5 路由改为 fabric 调用,brain.py 只剩转发。

每步做完跑一次 `make test` + `curl /health`,绿了再下一步。
