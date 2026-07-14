# 生命体入口（Living Companion Entry）—— AOS 的 3D 伙伴作为终端直接交互入口

> 映射阶跃星辰 2026-07-13 发布会（STEPX Neo / Step AOS / 阶跃Amoo）+ 真实 AOS 代码落点。
> 一句话：别人打开 AOS，第一眼不是聊天框，而是一个**有生命感的 3D 伙伴 / 生命体**，
> 它才是入口；你对着「它」说话，它去调 AOS 的真实能力（MCP 原子能力 / 3D 生成 / 检索）。

---

## 1. 愿景 ↔ 阶跃 Step AOS / Amoo（同源映射）

| 阶跃概念 | AOS 落地映射 | 状态 |
|---|---|---|
| 原子能力引擎（MCP 标准拆解系统能力） | `src/mcp/protocol.py` 的 `aos_*` 工具 + 适配器注册机制 + `MEDIA_3D` | ✅ 已有 |
| 双域记忆（用户域 / 智能体域） | 伙伴状态 JSON 落盘，分 `user_domain` / `agent_domain` 两域 | ✅ 已实现（轻量 JSON；mem0 是语义记忆升级路径） |
| 端云多脑（Edge/Flash/Pro 三级） | 路由层端云合作（`PROVIDER_PREFERENCE`+故障转移）；3D 本地永远可用 | ⚠️ 部分（无三级级联，但本地兜底已成立） |
| NUI 结果交互（说意图→完成全流程） | 生命体首页：输入浮层 + 语音按钮，伙伴去编排执行 | ✅ 已实现（Slice 1+2+4） |
| 硬件终端 STEPX Neo | AOS 是软件系统，无硬件 | N/A |
| 3D 交互（Omma 式生成式 3D） | `ThreejsAdapter` + 生命体身体场景 | ✅ 已实现 |

**核心一致点**：伙伴 = 系统的唯一交互入口（对标 Amoo「感知-记忆-规划-连接-执行」），
而非挂在角落的聊天框。这完全契合 AOS 架构第一性：单一内核（FabricHub）统一持有路由/记忆/上下文主权。

---

## 2. 已落地的代码（本次提交，纯增量、零破坏）

### 2.1 `src/core/fabric/companion.py`（新建）
- `Companion`：身份（`name` / `persona` / `body_prompt` / 视觉种子）+ 状态（`mood` / `energy` / `attention` / `turns`），跨会话持久化到 `.companion/<user_id>.json`。
  - **双域记忆**：`user_domain`（用户偏好/事实）+ `agent_domain`（伙伴自身经验/自我记录）。
  - **并发安全**：类级 `_STORE_LOCK` 串行化所有读写（Windows 下并发读写 `.json` 会 `WinError 32`，已修）。
- `build_living_home_html(companion)`：返回整页 —— 伙伴的「身体」(3D 场景) + HUD（名字/心情）+ 输入浮层 + 语音按钮 + **在场感 JS**（呼吸 / 随光标转头 / 消息脉冲）。
- `route_intent(text)`：自然语言 → 意图（3D / 搜索 / 对话），复用 AOS 真实能力。
- `handle_companion_message(text, user_id)`：编排「感知 → 记忆 → 规划 → 执行 → 回应」：
  - 3D 意图 → 直连 `ThreejsAdapter`（不经重型 hub，秒回、零依赖）；
  - 搜索/对话意图 → 经 FabricHub 路由层（`AOS_COMPANION_LLM=1` 时启用真 LLM；默认离线优雅降级，诚实不谎报）。

### 2.2 `src/core/fabric/adapters/threejs_adapter.py`（改）
- `_scene_js` 各分支把主对象赋给 `wobj`；`_TEMPLATE` 注入 `window.AOS_SCENE = {scene,camera,renderer,controls,t,main,sceneType}`，供在场感层操作「身体」。

### 2.3 `src/core/fabric/http_server.py`（改，Phase 1a 服务上叠加）
- `GET /` → 生命体首页（`text/html`）；`GET /?info=1` → JSON 元信息（API 客户端）。
- `GET /api/companion` → 伙伴身份+状态 JSON。
- `POST /api/companion/message` → 伙伴编排回应（`{reply, mood, scene_id, companion}`）。
- 保留：`/api/3d/generate`、`/scene/{id}`、`/api/mcp`、`/api/chat`、`/health` 等。

---

## 3. 四 Slice 落地状态

| Slice | 内容 | 状态 |
|---|---|---|
| **Slice 1 生命体首页** | `GET /` 直接是 3D 伙伴：身体场景 + HUD + 输入浮层，替代原 JSON info 页 | ✅ 已完成 |
| **Slice 2 有状态的「生命」** | mood/energy/turns 跨会话持久化（`.companion/*.json`）；消息触发心情变化；回归按 turns 问候 | ✅ 已完成 |
| **Slice 3 意图→行动** | 自然语言 → 路由 `aos_*` / `media.3d` / `web.search` / `inference.llm`（Amoo 式）；默认离线优雅降级，`AOS_COMPANION_LLM=1` 启用真 LLM 编排 | ✅ 基础版已完成（3D 直连 + 搜索/对话路由；真 LLM 需 key） |
| **Slice 4 语音 NUI** | Web Speech API（`webkitSpeechRecognition`，纯浏览器）语音输入按钮 | ✅ 已完成（浏览器原生，无需服务端改动） |

---

## 4. 怎么跑（用户主机）

```powershell
cd D:\AOS
python scripts/aos.py serve          # 默认 127.0.0.1:8123
```
浏览器打开 `http://127.0.0.1:8123/`：
- 第一眼是转动的 3D 生命体伙伴「小元」+ HUD + 底部输入框 + 🎤 语音按钮。
- 试试：「做个宇宙粒子星河」→ 生成可拖拽的 3D 场景（点开即玩）；
  「你好我是小明」→ 伙伴离线用心听、用身体回应（诚实，不谎报云端能力）；
  「搜索最新AI新闻」→ 记下了，联网后办。

开启真实 LLM 对话：
```powershell
$env:AOS_COMPANION_LLM="1"
python scripts/aos.py serve
```

---

## 5. 诚实边界（不弄虚）
- Three.js 走 CDN（unpkg），**浏览器需联网**；离线会显示错误提示。
- 视觉交互（拖拽/呼吸/转头/脉冲）**须用户在自有浏览器验证**（沙箱无 WebGL）。已验证：生成的 HTML 合法、含 Three.js + OrbitControls + `window.AOS_SCENE`；HTTP 全链路（首页/消息/场景/伴状态）在沙箱真跑通过（含 20 线程并发 0 失败）。
- 当前 `Companion` 持久化用轻量 JSON 文件（零依赖、可验证）；**mem0 是双域记忆的语义升级路径**（接入 `MEMORY.md` 的 domain 维度即可），尚未切换，避免引入重依赖。
- 伙伴默认人设「小元」写在 `companion.py` 的 `_default_identity()`，可改；后续可经配置/UI 让用户自定义名字与身体风格。

---

## 6. 下一步（可选增强）
1. **人设/视觉自定义**：配置化伙伴名字、身体场景类型、调色板（替代硬编码默认）。
2. **真 LLM 对话 + 规划**：`AOS_COMPANION_LLM=1` 已接路由层；可加 ag2 规划让伙伴拆解长流程任务（订行程式）。
3. **mem0 双域记忆**：把 `user_domain` / `agent_domain` 迁移到 mem0（带 `domain` filter），获得语义检索。
4. **导出/分享**：把伙伴生成的 3D 场景导出 GLB / 截图，对接「生产就绪」。
5. **多伙伴/多用户**：`user_id` 已参数化，可扩展为每用户独立生命体。
