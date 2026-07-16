# 双轨运行时收敛：现状核实与下一步（2026-07-15）

> 背景：全盘审视时把"FabricHub 新栈 vs legacy brain.py 并存"笼统列为最大架构债。
> 本轮用 grep 实挖引用点，**结论需要修正**：chat 主链路已基本收敛，真正的缺口在"非 chat 端点仍直调 brain.py"，且双轨并存是设计意图（渐进迁移）而非漏做。

## 一、核实结论（带行号证据）

### 1. `/api/chat` 已收敛 ✅
- `src/api/main.py:462-505`：灰度 `AOS_KERNEL_TRAFFIC_PCT`，**默认 100 = 全部走 kernel**；kernel 失败自动回退 brain（:498）。
- `src/kernel/v5_bridge.py`：同构设计，`kernel.send_message` 替代 `brain.chat`，brain 仅作 fallback（:151/:330-331 注册 hermes/deerflow 回调）。

### 2. kernel 本体已零依赖 ✅
- `src/kernel/kernel.py:9` 明确注释："**绝不 import brain / litellm / mcp / fabric** —— 那些是插件，由外部接线层登记进来。"

### 3. core 入口已 lazy ✅
- `src/core/__init__.py:15-16`：`UnifiedBrain`/`get_brain` 走 `__getattr__` 惰性导入，仅在真用到 brain 时才拖入重型依赖。

### 4. 真正还直调 brain.py 的地方（非 chat 端点）
集中在 `src/api/main.py`，这些是 brain 的 `hermes`/`deerflow`/`memory` 能力，FabricHub 暂未完全对等覆盖：
| 端点 | 行号 | 调的 brain 能力 |
|---|---|---|
| `/api/chat/stream` | 716 | `brain.hermes.stream_chat` |
| 记忆增/搜/导出 | 728 / 751 / 755 / 763 / 771 | `brain.add_memory` / `brain.search_memory` / `brain.export_memory` / `brain.semantic_memory_*` |
| 会话列表/获取/删 | 778 / 783 / 790-793 | `brain.list_sessions` / `brain.get_session` / `brain.hermes.sessions` |
| 任务提交/列表 | 802 / 807 / 811 | `brain.deerflow.submit_task` / `brain.deerflow.list_tasks` |

## 二、设计意图（不是漏做）

`src/kernel/wiring.py:185-188` 明确："**演化而非革命** —— 不改动 brain.py（1965 行单体），而是把已有的内核 ModelGateway 注入 brain.py，向内核让渡模型调用权。非物理删除 brain.py。"
即：brain 保留为"模块运行时兜底"，双轨并存是**有意为之的渐进迁移**。

## 三、剩余收敛步骤（等用户审计 P0 合入后再做，现在不动）

1. **能力对账**：确认 FabricHub 是否需要对等暴露 `memory` / `sessions` / `tasks` 三类能力；若需，在 `core/fabric/`（新栈，非 brain）新增对应路由/芯粒。
2. **逐端点迁移**：把上表 4 类端点从直调 brain 改为走 kernel / FabricHub；每迁一个删一处 brain 直调。
3. **回退开关化**：用显式 env（如 `AOS_LEGACY_CHAT` / `AOS_LEGACY_MEMORY`）控制是否保留 brain 兜底，默认关；全迁完再摘 brain。

## 四、为什么现在不能直接摘 brain

- `brain.py` 是 1965 行单体，且**含用户未提交的审计 P0 修复**（在途 50+ 改动之一）。
- 强删会丢修复 + 高风险阻断服务。等用户把这些改动 commit 后，再按本方案第 1-3 步收口。

## 五、验证方式

- 已有 `tests/test_fabric_hub.py` 覆盖路由；建议新增 `tests/test_chat_grayscale.py`：断言 `AOS_KERNEL_TRAFFIC_PCT=100` 时 `/api/chat` 落 kernel、`=0` 时落 brain。
- 双轨对比：`v5_bridge.dual_route`（:221-233）已支持 kernel 与 brain 并行跑、比结果，可用于迁移期等价验证。
