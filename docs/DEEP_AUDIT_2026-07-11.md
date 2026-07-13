# AOS v5.0 深度审计报告

**日期**: 2026-07-11
**审计方式**: 全量代码扫描 + 真实测试执行（不凭记忆，全部重新验证）

### 勘误记录（v2 — 2026-07-11 用户复核后修正）

| # | 原文错误 | 修正 |
|---|---------|------|
| 1 | "sqlmodel 未安装" | sqlmodel 0.0.39 已安装。初版检查时环境尚未就绪，报告定稿时未重新验证。 |
| 2 | "aos_server.py 不会崩溃" | import 有保护但 33-34 行 `get_router()` / `register_builtins(router)` 未判 `_HAS_ROUTER`，**必崩 NameError**。 |
| 3 | "test_memory.py 6 failed" | 实跑 7 failed。且套件 flaky — 单跑 xfail、全套跑因 SQLite 锁竞争抛不同异常变 FAILED。 |
| 4 | "修复成本: 1 行修改" | `acquire()` 是 `async def`，`_get_connection()` 是 sync，直接 rename 拿到 coroutine 不是 connection。需中等改动。 |

---

## 一、代码库真实规模

| 目录 | 文件数 | 行数 | 占比 |
|------|--------|------|------|
| skills/ | 586 | 55,423 | 59.2% |
| core/ | 56 | 10,215 | 10.9% |
| kernel/ | 42 | 9,112 | 9.7% |
| web/ | 2 | 4,297 | 4.6% |
| api/ | 4 | 2,793 | 3.0% |
| deerflow/ | 12 | 2,735 | 2.9% |
| utils/ | 8 | 1,758 | 1.9% |
| subagents/ | 9 | 1,303 | 1.4% |
| 其他 | 29 | 5,919 | 6.3% |
| **合计** | **748** | **93,555** | **100%** |

**测试**: 46 个测试文件，359 个 `def test_()` 函数。

**结论**: Skills 占代码库 59.2%（55K 行）。这不是"技能系统"，这是代码库本身。kernel 只占 9.7%。

---

## 二、真实 Bug（带文件行号，可复核）

### Bug #1: ConnectionPool.get_connection() 不存在

**位置**: `src/memory/memory.py:230`
```python
return self._pool.get_connection()  # ← 调用不存在的方法
```

**ConnectionPool 真实方法**（`src/core/pool/connection_pool.py`）:
- `__init__`, `initialize`, `acquire`, `release`, `_health_check_loop`, `_perform_health_check`, `close`, `get_stats`
- **没有 `get_connection()`**

**影响**: memory.py 中 6 处调用 `_get_connection()` 全部会触发 AttributeError。
- `memory.py:460`, `503`, `512`, `522`, `560` — 所有涉及数据库操作的测试全部失败。

**修复**: ~~将 `self._pool.get_connection()` 改为 `self._pool.acquire()`~~ — **不可行**。
`acquire()` 是 `async def`（`connection_pool.py:185`），而 `_get_connection()` 是同步方法。
直接 rename 拿到的是 coroutine 对象而非连接，会换一种方式崩。
真正修复需要：(a) 把 memory.py 的整条连接使用链路改为 async，或 (b) 在 ConnectionPool
中新增一个同步的 `get_connection()` 包装方法（内部用 `asyncio.run` 或预建连接池）。
**预估成本**: 中等改动，涉及 memory.py 的 `_get_connection` + 6 处调用点 + 可能的上下文管理器适配。

### Bug #2: kernel.router 不存在

**位置**: `aos_server.py:24`
```python
from kernel.router import get_router, register_builtins
```

**真实文件**: `src/kernel/` 下无 `router.py`。只有 `auth_bridge.py`, `skills_bridge.py`, `v5_bridge.py`。

**现状**: import 有 `try/except` 保护（23-27 行，设 `_HAS_ROUTER = False`），但 **33-34 行未判 `_HAS_ROUTER`**：
```python
33: router = get_router()        # ← NameError: get_router 未绑定
34: register_builtins(router)    # ← 同上
```
`kernel.router` 不存在 → import 失败 → `get_router` 名字从未定义 → **运行必崩 `NameError`**。
这不是"功能不可用"，是"启动即死"。

### Bug #3: 74 处 except Exception: pass 残留

Phase 1 修复了关键路径的 49 处，但仍有 74 处：
- **关键路径** (core/kernel/memory/deerflow): 41 处
- **非关键路径** (api/web/utils): 33 处

示例（关键路径）:
- `src/kernel/compliance.py:162`
- `src/kernel/immunity.py:266`
- `src/kernel/skills_bridge.py:105`
- `src/kernel/v5_bridge.py:50`
- `src/kernel/wiring.py:85`

### Bug #4: 8 处硬编码路径残留

- `src/skills/frontend_design.py:174`: `output_dir="D:/AOS/outputs"`
- `src/skills/skill_creator.py:79`: `Path("D:/AOS/src/skills/generated")`
- `src/kernel/isolation/subprocess_iso.py:44`: `"D:/AOS/src"`

---

## 三、测试套件真实状态

### 稳定通过的测试（可重复验证）

| 文件 | 测试数 | 耗时 | 状态 |
|------|--------|------|------|
| test_kernel_compliance.py | 27 | 2.86s | 全绿 |
| test_skills.py | 16 | 0.43s | 全绿 |
| test_brain_smoke.py | 15 | 0.16s | 全绿 |
| test_security_middleware.py | 18 | 3.42s | 全绿 |
| **小计** | **76** | **~7s** | **稳定** |

### 间歇性挂起的测试

| 文件 | 测试数 | 问题 |
|------|--------|------|
| test_kernel_units.py | 75 | 单独跑偶尔挂起，原因：v5_bridge → system → layers 导入链在某些状态下阻塞 |
| test_api.py | 13 | TestClient 初始化可能触发真实网络连接 |

### 确定性失败的测试

| 文件 | 测试数 | 根因 |
|------|--------|------|
| test_memory.py | 7 | ConnectionPool.get_connection() 不存在（Bug #1）。**注意**: 此套件不稳定 — 单跑某些测试触发 `AttributeError`（被 xfail 兜住），全套跑时 SQLite 锁竞争改为抛 `sqlite3.OperationalError`（xfail 的 `raises=AttributeError` 兜不住，变成 FAILED）。 |
| test_database.py | 6 | 同上 + SQLite 锁竞争 |
| test_config.py | 1 | 环境变量 reload 后单例未更新 |

### 被 skip 的遗留测试

| 文件 | 原因 |
|------|------|
| test_architecture.py | `deerflow.graph` 模块不存在 |
| test_e2e.py | 脚本式测试，非 pytest 兼容 |
| test_final.py | 脚本式测试，非 pytest 兼容 |
| test_graphrag_full.py | 需要 Qdrant 服务（localhost:6335） |
| test_memory_root.py | MemoryManager 初始化触发 Bug #1（ConnectionPool API 不匹配） |
| test_planner.py | `deerflow.graph` 模块不存在 |
| test_security.py | `skills.safe_eval` 导入链失败 |

---

## 四、环境债务

### 428 个过期 .pyc 文件

系统运行 Python 3.14，但 `src/` 下存在 428 个 `cpython-313.pyc` 文件。这些是 Python 3.13 的编译缓存，不会被 3.14 加载，但占用磁盘空间并造成混乱。

**清理命令**:
```bash
find src/ -name "*.cpython-313.pyc" -delete
```

### sqlmodel 已安装（v0.39）

`requirements.txt` 声明的 `sqlmodel>=0.0.14` 已安装（实测 `sqlmodel 0.0.39`）。
但 test_database.py / test_memory.py 仍失败 — 原因不是缺依赖，而是 Bug #1（ConnectionPool API 不匹配）和 SQLite 锁竞争。

---

## 五、Kernel 切流真实可用性

### 已实现

1. **`/api/v1/chat`** — 直接调用 `bridge.chat()`，走 kernel 的 `send_message()`
2. **`/api/v1/chat/stream`** — SSE streaming，走 `ModelGateway.stream_chat()`
3. **灰度控制** — `AOS_KERNEL_TRAFFIC_PCT` 环境变量（0-100），在 `/api/chat` 上按比例切流
4. **引擎回调** — `register_engine_callback()` 将 brain.hermes/deerflow 注册到 kernel 的 AgentRuntime

### 未实现 / 不可用

1. **kernel.router** — 不存在（Bug #2），`aos_server.py` 的路由功能不可用
2. **v5_bridge 导入不稳定** — `from kernel.v5_bridge import V5Bridge` 在某些环境下挂起（kernel → system → layers 导入链问题）
3. **AOS_KERNEL_TRAFFIC_PCT 默认 0** — 意味着 0% 流量走 kernel，实际未启用

### 结论

Kernel 切流**框架已搭好，但未通电**。`/api/v1/chat` 可以工作，但生产路径 `/api/chat` 仍 100% 走 brain.py。要真正切流，需要：
1. 修复 v5_bridge 导入稳定性
2. 将 `AOS_KERNEL_TRAFFIC_PCT` 从 0 逐步调高
3. 在真实流量下验证 kernel 路由的正确性

---

## 六、优先级排序（按影响/成本比）

### P0 — 立即修复（影响生产）

1. **ConnectionPool 同步/异步不匹配**
   - 文件: `src/memory/memory.py:230`
   - 影响: 6 处调用全部 AttributeError，所有记忆功能不可用
   - 成本: **中等** — `acquire()` 是 async，`_get_connection()` 是 sync，不能简单 rename。需要在 ConnectionPool 加同步包装或改 memory.py 为 async。

2. **清理 428 个过期 .pyc**
   - 命令: `find src/ -name "*.cpython-313.pyc" -delete`
   - 影响: 无功能影响，但减少混乱
   - 成本: 1 条命令

### P1 — 短期修复（影响测试通过率）

3. **修复 test_memory.py 7 个失败**
   - 依赖 Bug #1 修复
   - 注意：测试套件本身有 flaky 问题（SQLite 锁竞争导致异常类型不确定）

4. **修复 v5_bridge 导入挂起**
   - 根因: kernel/__init__.py 导入 14 个子模块，某些环境下 auth_bridge 导入慢（1.5s+）
   - 方案: 将 v5_bridge.py 的顶层 import 改为懒导入

5. **修复 41 处关键路径 silent except**
   - 文件: kernel/compliance.py, kernel/immunity.py, kernel/skills_bridge.py, kernel/v5_bridge.py, kernel/wiring.py
   - 成本: 每处加 1 行 logger.warning

### P2 — 中期改进

6. **kernel 切流通电**
   - 将 AOS_KERNEL_TRAFFIC_PCT 从 0 调到 10，验证 10% 流量走 kernel
   - 监控错误率和延迟

7. **Skills 瘦身**
   - 586 文件 / 55K 行占代码库 59.2%
   - 审计休眠技能，归档到 `src/skills/_archive/`

8. **硬编码路径清理**
   - 8 处 `D:/AOS` 硬编码
   - 改为环境变量或 `Path(__file__)` 相对路径

### P3 — 长期架构

9. **brain.py 退役计划**
   - brain.py 1978 行，仍是生产主路径
   - kernel 切流稳定后，逐步将逻辑迁移到 kernel

10. **web/app.py 拆分**
    - 4297 行单文件 Streamlit 应用
    - 拆分为路由 + 组件 + 状态管理

---

## 七、复核命令

以下命令可在任何环境复现本报告的核心数据：

```bash
# 代码规模
python -c "import pathlib; files=list(pathlib.Path('src').rglob('*.py')); print(f'{len(files)} files, {sum(len(f.read_text(encoding=\"utf-8\").splitlines()) for f in files)} lines')"

# 测试通过率
python -m pytest tests/test_kernel_compliance.py tests/test_skills.py tests/test_brain_smoke.py tests/test_security_middleware.py -q --tb=no

# ConnectionPool 方法列表
python -c "import ast; tree=ast.parse(open('src/core/pool/connection_pool.py').read()); print([n.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name=='ConnectionPool' for n in node.body if isinstance(n, ast.FunctionDef)])"

# 过期 .pyc 数量
find src/ -name "*.cpython-313.pyc" | wc -l

# silent except 数量
python -c "import pathlib; c=0
for f in pathlib.Path('src').rglob('*.py'):
    lines=f.read_text(encoding='utf-8',errors='replace').splitlines()
    for i,l in enumerate(lines):
        if l.strip()=='pass' and i>0 and 'except' in lines[i-1].strip(): c+=1
print(c)"
```

---

**报告结束**。所有数据均可通过上述命令复核，无虚报、无美化。
