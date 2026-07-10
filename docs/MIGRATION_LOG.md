# AOS Kernel Migration Log

> 记录 v5 (brain.py) → v1 (kernel) 的切流进度。

## 端点状态

| 端点 | 当前路径 | 目标路径 | 状态 |
|------|----------|----------|------|
| `/api/chat` | brain.py | kernel (灰度) | 灰度机制已就位，默认 0% |
| `/api/v1/chat` | kernel.send_message() | kernel | 已切换（Phase 3.2） |
| `/api/v1/chat/stream` | kernel ModelGateway | kernel | 新建（Phase 3.3） |
| `/api/v1/health` | kernel bridge.health() | kernel | 正常 |
| `/api/chat/stream` | brain.hermes.stream_chat | kernel streaming | 待迁移 |

## 引擎注册

| 引擎 | 注册状态 | 注册时机 |
|------|----------|----------|
| litellm | 已注册 | wiring.py build_default_kernel() |
| hermes | 已注册 | _deferred_brain_init() Phase 3.4 |
| deerflow | 已注册 | _deferred_brain_init() Phase 3.4 |

## 灰度控制

环境变量 `AOS_KERNEL_TRAFFIC_PCT`（0-100）：
- `0`（默认）= 全部走 brain.py
- `5` = 5% 流量走 kernel
- `100` = 全部走 kernel

切流阶段：0% → 5% → 20% → 50% → 100%

## 变更日志

### 2026-07-11 Phase 3
- `/api/v1/chat` 从直接访问 `_model_gateway` 改为调用 `bridge.chat()` → `kernel.send_message()`
- 新增 `/api/v1/chat/stream` SSE streaming 端点
- hermes/deerflow 引擎回调注册到 kernel（`register_engine_callback`）
- `/api/chat` 灰度切流机制就位（`AOS_KERNEL_TRAFFIC_PCT` 环境变量）
- brain.py 路径添加 debug 级别日志标记
