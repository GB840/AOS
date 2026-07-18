# AOS 架构图问题「落实」报告（2026-07-18）

> 目的：用户贴了一张 AOS 架构图（标注"基于代码，非文档宣称"），我此前指出了 4 处疑点。
> 本报告用**实跑脚本 + 源码静态确证**逐条落实，判定"我说得对 / 错 / 部分对"。
> 所有结论附证据链（源码行号 + 实跑输出），拒绝模糊描述。

---

## 1. 「FabricHub 全局单例，所有模块共享同一实例」—— ❌ 与代码相反

**图说法**：FabricHub 统一内核（全局单例）`get_fabric_hub()` · 所有模块共享同一实例

**落实结论**：存在**两套获取路径、两个全局实例**，装配内容不同。

| 获取函数 | 位置 | 性质 | 谁在用 |
|---|---|---|---|
| `get_fabric_hub()` | `fabric_hub.py:1556` | 模块级 `_hub_instance` 单例，但**裸 `FabricHub()`**（基础初始化，未注册外部适配器） | `main.py:373` `_get_fabric_hub` → AutoSkill 钩子注册；content_flywheel / studio 等多处 |
| `build_fabric_hub()` | `wiring.py:55`（带 `functools.lru_cache(maxsize=1)`） | **完整装配**（注册引擎 + 编排芯粒 + MCP/weknora/code_team/comfyui/content_director 等） | `build_default_kernel`、mcp `protocol._get_hub`、bridge 内核 |

**实跑证据**（`_verify_dup_hub.py`，系统 Python 3.14.5，PYTHONPATH=src，耗时 6m11s 因重型依赖 cognee/272 角色/MCP 注册）：
```
=== IMPORT kernel.plugins.fabric_hub OK ===
--- get_fabric_hub source ---
def get_fabric_hub() -> FabricHub:
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = FabricHub()   # ← 裸实例
    return _hub_instance
--- get_fabric_hub() called twice ---
same object: True | id_a= 1560406061952 id_b= 1560406061952   # ← 自身是单例
```
`get_fabric_hub()` 自身是单例（同进程复用 `_hub_instance`），但它是**裸单例**；
`build_fabric_hub()` 是另一个 lru_cache 单例、做完整装配 → 两者是**不同的全局实例**。

**关键不一致**：`main.py:373` `hub = await _get_fabric_hub()` → `autoskill.register_with_fabric_hub(hub)`，
而 `_get_fabric_hub`（main.py:2224）内部 `await asyncio.to_thread(get_fabric_hub)` ——
**AutoSkill「缺能力自动装技能」钩子挂在裸实例上**，而 `/api/chat` 真正走的 bridge/内核是完整装配那份。
两路「缺能力触发」行为不一致。

**判定**：图写"全局单例、共享同一实例"是**反的**。准确说法应是"FabricHub 有两套获取路径：裸单例（内容飞轮/AutoSkill 用）与完整装配单例（chat/MCP 用），二者能力集不同"。

---

## 2. 「飞轮全链路验证通过 + 反哺→Studio」—— ⚠️ 我上轮判错了，部分通

**图说法**：Studio → Pulse → Evolve → 反哺 → Studio（双飞轮互相增强）

**落实结论**：**产品飞轮（Studio 工作流）侧自动反哺闭环已通；内容飞轮侧未接自动写回**。

**实跑/源码证据**：
- `src/kernel/studio/workflow_runner.py:258` `_maybe_evolve`：
  ```python
  run_count = wf.run_count
  if run_count % 5 != 0:
      return                      # 节流：每 5 次运行检查一次
  proposals = evolve.generate_proposals(wf_id)
  for prop in proposals:
      if prop.risk_level == "low" and prop.auto_applicable and not prop.applied:
          result = evolve.apply_proposal(prop.id, self._store)   # :282 真写回
          break                  # 每次只应用 1 个，渐进式
  ```
- `evolve_engine.py:386` `apply_proposal` **真写回工作流定义**：
  - `update_step`：改 step 字段 → `workflow_store.save(wf)` + `_bump_version` + 回滚快照（`:449`）
  - `add_step`：插入新步骤 → `workflow_store.save(wf)`（`:479`）
  → 是**写实、可回滚**的自动进化，非空壳。
- **内容飞轮侧未接**：`content_flywheel.py` grep 无 `apply_proposal / generate_proposals / evolve` 调用（已证实）；Echo 仅把反馈上报 Pulse，自动优化靠 `product_flywheel_api.py` 手动 API 拉取。

**判定**：图"反哺→Studio"对**产品飞轮**成立；"全链路验证通过"对产品飞轮成立、对**双飞轮整体夸大**。
我上轮把整条标成"未接 ❌"是**错误**的——已纠正。准确说法："产品飞轮自增强已通（保守节流）、内容飞轮自动写回待接"。

---

## 3. 「8 大融合点」—— ❌ 非代码概念

**图说法**：飞轮业务闭环层（8 大融合点 · 全链路验证通过）

**落实结论**：**全仓库代码与文档均无"融合点"一词**，是用户自定义框架词。

**证据**：
- 全仓内容 grep 超时（文件过多），但**逐文件证伪**关键文档均 `No matches`：
  `AGENTS.md` / `STATUS.md` / `README.md` / `AOS_CURRENT_STATE_SNAPSHOT.md` / `AOS_V5_COMPLETION_SUMMARY.md`。
- `src/` 与 `docs/` 目录 grep "融合点" 亦 `No matches`。

**判定**：图标注"基于代码，非文档宣称"，却用了代码里不存在的概念，**自相矛盾**。
应改为"8 个业务融合环节（设计视角）"。

---

## 4. 内容飞轮 5 适配器命名 —— ⚠️ 确有出入

**图说法**：内容飞轮 Director / Cast / Echo / Refine / Marketer

**落实结论**：代码真实 engine_id 与图不完全对应。

**源码证据**（grep 适配器的 `engine_id`）：
| 文件 | 真实 engine_id | 图写法 | 一致？ |
|---|---|---|---|
| `content_marketer_adapter.py:58` | `content-marketer` | Marketer | 简化 |
| `cast_adapter.py:110` | `cast` | Cast | ✅ |
| `echo_adapter.py:70` | `echo` | Echo | ✅ |
| `refine_adapter.py:65` | `refine` | Refine | ✅ |
| `video_maker_adapter.py:54` | `video-maker`（Capability.MEDIA_VIDEO） | Director | ❌ 错 |

**判定**：Cast/Echo/Refine 完全对；Marketer 实为 `content-marketer`（简化可接受）；
**Director 实际不在这 5 个适配器里**（Director 是另一个 `content_director` skill，非 core/fabric 适配器），
图把第 5 个 `video-maker`（视频生成）错写成 Director，且漏了 `video-maker`。

---

## 总判定表

| 图的断言 | 落实结果 |
|---|---|
| FabricHub 全局单例、共享同一实例 | ❌ 反的：裸单例 vs 完整装配双实例 |
| 飞轮全链路验证通过 + 反哺→Studio | ⚠️ 部分：产品飞轮闭环通、内容飞轮未接 |
| 8 大融合点 | ❌ 非代码概念（自相矛盾标注） |
| 内容飞轮 5 适配器命名 | ⚠️ Director 错（应为 video-maker）；Marketer=content-marketer |
| 分层结构 / 8 个 API 路由 / 双轨未合流 / 芯粒隔离 / 记忆系统 | ✅ 属实 |

---

## 附：可复核证据
- 实跑脚本：`_verify_dup_hub.py`（已清理，关键输出见上）
- 关键源码：`fabric_hub.py:1556` / `wiring.py:55` / `main.py:373,2224` / `workflow_runner.py:258,282` / `evolve_engine.py:386,449,479` / 5 个内容飞轮适配器文件
