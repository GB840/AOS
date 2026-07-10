# AOS v1.0 内核 · 架构现状对账表（#171 审查步）

> 生成于 2026-07-10。方法：逐文件读代码核验，不凭规划文档。
> 目的：在动手接管运行系统（#172）与 brain.py 下沉（#173）之前，摸清
> **已落地 / 未接线 / 缺口**，确保"先审查再动手、不遗漏"。

---

## 0. 一句话结论

**v1.0"物种思维"内核已完整落地（31 模块 / 6112 行，零依赖内核 + 四层 + 插件 + 物种三层），
但它整体游离在真实运行系统之外——`src/api/*` 对内核零引用，两个桥接层从未被挂载。
真实 `/api/chat` 仍 100% 走 `brain.py(1965行) → LLMRouter → mistralrs`。
内核的 ModelGateway 只认 `zhipu/glm-4-flash`，完全不知道 mistralrs 的存在。**

---

## 1. 真实运行链路（当前实际在跑的）

```
api/main.py  (FastAPI app)
   └─ @app.on_event("startup")  →  brain = get_brain()      # core/brain.py 1965行单体
   └─ POST /api/chat  →  brain.chat(message, session_id)
                          └─ meta_orchestrator.route_intent  (L3.5 进化门控)
                          └─ _route_l1 / _route_l2 / _route_deerflow_skill
                          └─ brain._init_router → `from router import LLMRouter`
                                                    └─ src/router/llm_router.py
                                                         └─ mistralrs 1234/1235/1236 (PRIMARY)
                                                         └─ Ollama (fallback)
                                                         └─ Zhipu / SiliconFlow (云端兜底)
```

- **mistralrs 配置真相源**：`src/utils/config.py`（`MISTRALRS_MODEL_*` = 真实目录路径 id，`ROUTER_PREFER_LOCAL=True`）
- **mistralrs 唯一消费者**：`src/router/llm_router.py`（非内核）
- 结论：mistralrs 三端点端到端可用，但只挂在**遗留 llm_router 路径**上。

---

## 2. 内核落地清单（31 模块 · 已落地 = 代码存在且此前冒烟通过）

| 分层 | 模块 | 行 | 状态 | 说明 |
|---|---|---|---|---|
| **内核核心** | `kernel.py` | 169 | ✅ 落地 | AOSKernel：生命周期/路由/权限，零依赖，干净 |
| | `interfaces.py` | 104 | ✅ 落地 | 三 ABC：ModelGateway / AgentRuntime / SkillBus |
| | `types.py` | 159 | ✅ 落地 | 纯 dataclass 契约 |
| | `wiring.py` | 83 | ✅ 落地 | 登记种子插件（litellm + 5 fabric 适配器 + MCP） |
| | `system.py` | 169 | ✅ 落地 | build_default_system：内核+四层+物种回调 |
| **四层** | `layers/model_gateway_layer.py` | 229 | ✅ 落地 | 统一调用/智能路由/成本控制 |
| | `layers/mcp_bus_layer.py` | 104 | ✅ 落地 | 服务发现/消息路由/权限校验 |
| | `layers/agent_runtime_layer.py` | 313 | ✅ 落地 | 记忆/工作流编排 |
| | `layers/ui_layer.py` | 170 | ✅ 落地 | 三 UI 面抽象 |
| | `layers/model_fallback.py` | 160 | ✅ 落地 | 降级链 |
| **插件** | `plugins/litellm_gateway.py` | 84 | ⚠️ 落地但残缺 | **只硬编码 zhipu/glm-4-flash，不含 mistralrs** |
| | `plugins/fabric_runtime.py` | 79 | ✅ 落地 | BaseAgentAdapter→AgentRuntime 薄封装 |
| | `plugins/mcp_skill_bus.py` | 52 | ✅ 落地 | MCP→SkillBus 薄封装 |
| **物种层** | `immunity.py` | 296 | ✅ 落地 | 异常检测/自愈/熔断 |
| | `evolution.py` | 342 | ✅ 落地 | DNA/变异/Fitness/育种 |
| | `ecology.py` | 255 | ✅ 落地 | 资源经济/自然选择/共生 |
| | `hippo_scroll.py` | 634 | ✅ 落地 | 双轨存储/金字塔检索/元认知巡检 |
| | `compliance.py` | 491 | ✅ 落地 | 审计/内容安全/规则引擎 |
| **扩展点** | `versioning.py` | 244 | ✅ 落地 | ModuleVersion/UpgradeManager/多版本共存 |
| | `events.py` | 239 | ✅ 落地 | 事件总线（内核关键路径发射） |
| | `hotswap.py` | 115 | ✅ 落地 | 运行时热替换 |
| | `future.py` | 130 | ✅ 落地 | 未来协议/合规扩展槽 |
| **桥接** | `auth_bridge.py` | 221 | ✅ 落地 | JWT→内核 Permission |
| | `skills_bridge.py` | 165 | ✅ 落地 | 现有 skills→SkillBus |
| | `aos_bridge.py` | 168 | ⚠️ 落地但未接线 | KernelAOSBridge.start(app) 从未被调 |
| | `v5_bridge.py` | 331 | ⚠️ 落地但未接线 | V5Bridge.mount(app) 从未被调 |
| | `live.py` / `router.py` / `v5_bridge` | — | ✅ 落地 | 活体进化闭环 / 内核路由 |

---

## 3. 未接线（landed but NOT wired）— 核心缺口

| # | 缺口 | 证据 | 影响 |
|---|---|---|---|
| G1 | **内核整体不在运行路径** | `grep kernel\|bridge src/api/*` = 0 命中 | 6112 行内核 = 离线演示，未接管任何真实请求 |
| G2 | **两个桥接层均未挂载** | main.py `startup_event` 只 `get_brain()`，无 `bridge.mount(app)` | aos_bridge / v5_bridge 双双空转 |
| G3 | **ModelGateway 不识 mistralrs** | `litellm_gateway.py:34-37` 只返回 zhipu/glm-4-flash | 内核即使接管，也调不到本地 mistralrs（会退回云） |
| G4 | **两个桥接冗余** | aos_bridge.KernelAOSBridge 与 v5_bridge.V5Bridge 职责重叠 | 需二选一（v5_bridge 功能更全，含 7 缺口 + compliance） |
| G5 | **内核模型栈 ≠ 运行模型栈** | 内核走 LiteLLMAdapter；运行走 src/router/llm_router.py | 两套模型路由并存，mistralrs 只在后者 |

---

## 4. 据此确定的动手顺序（#172 / #173）

**#172 内核接管运行系统 + mistralrs 归并为 ModelGateway 插件**（不改 brain.py）
1. 新建 `kernel/plugins/mistralrs_gateway.py`：实现 `ModelGateway`，读 `src/utils/config.py` 的
   `MISTRALRS_MODEL_*`，把 1234/1235/1236 三端点 `list_models()` 出来，`chat()` 走 OpenAI 兼容 HTTP。→ 补 G3
2. `wiring.py` 登记 mistralrs 为首选 ModelGateway（litellm 作兜底）。
3. **二选一保留 `v5_bridge`**（功能全），在 `api/main.py` startup 里 `V5Bridge().mount(app)`，
   把内核挂进 `app.state.kernel`，新增 `/api/v1/chat` 走内核（与旧 `/api/chat` 双轨并存）。→ 补 G1/G2/G4
4. 端到端验证：`/api/v1/chat` → kernel.send_message → mistralrs 命中本地端口。

**#173 brain.py 1965 行下沉为内核插件**（模式已定，渐进执行）
- brain 的路由/记忆/合规/编排逐块下沉到对应 kernel 层/插件，`/api/chat` 逐步切到内核，brain 降温。

---

## 5. 铁律校验（本轮改动须守）

- 不改 brain.py（演进非革命）。✅ #172 全部走桥接层新增，不动 brain。
- 内核核心零依赖。✅ mistralrs 插件放 `kernel/plugins/`（允许 import 具体实现），不污染 `kernel.py`。
- 不在锁内 await；`/health` 秒回；chat 重活 `asyncio.to_thread`。✅ 新增内核路由沿用同规范。
- mistralrs 主、Ollama 备、云兜底。✅ 由插件 + wiring 优先级保证。
