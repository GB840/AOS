# AOS v5.0 全量深度审计报告 v3

**日期**: 2026-07-15
**范围**: D:\AOS 全仓库（src/ 759 文件 / 98,154 行）
**方式**: 5 路并行扫描（安全 / 架构 / 运行时 / 代码质量 / 测试覆盖），全部结论带文件:行号

---

## 〇、本次修复后基线（2026-07-15 修了什么）

| 项目 | 修复前 | 修复后 | 验证 |
|------|--------|--------|------|
| ScriptsAdapter NameError | fabric_hub.py:125 崩溃 | import 补全 + `__all__` 更新 | test_fabric_hub 5/5 全绿 |
| 过期 .pyc | 444 个 cpython-313 | 0 | 已删 |
| silent except: pass | 82 处 | 0（已加 logger.warning） | 32 文件 py_compile 全通过 |
| 硬编码 D:/AOS | 4 处代码 + 5 处注释 | 代码改 Path(__file__)，注释未动 | ruff 无新错 |
| test_fabric_hub 断言 | 期望 13 引擎 | 更新为 19 引擎 | 5/5 全绿 |
| 核心测试 | 76 passed | 102 passed, 0 failed | 4m45s |

---

## 一、安全问题（4 CRITICAL / 4 HIGH / 10 MEDIUM / 2 LOW）

### CRITICAL

**S-1: execution/sandbox.py 无限制 RCE**
`src/execution/sandbox.py:113-140` — `_execute_python()` 写任意代码到临时文件再 `subprocess.run`，零 AST 检查、零 import 限制。与 `skills/sandbox.py`（至少有 AST deny list）不同，这里完全没有防护。

**S-2: /api/sandbox/exec 端点**
`src/api/main.py:1042-1066` — 当 `AOS_SANDBOX_API_ENABLED=true` 时，任何持有效 API key 的调用方可执行任意宿主命令。虽然默认关闭，但开启后是未受限 RCE。

**S-3: sandbox.py f-string 模板注入**
`src/skills/sandbox.py:417-424` — `skill_name` 和 `context` 直接拼入 Python 代码 f-string，无转义。外部输入可注入任意代码。

**S-4: FabricHub HTTP 服务器零认证**
`src/core/fabric/http_server.py:141-836` — 独立 `ThreadingHTTPServer` 绑定 `0.0.0.0:8123`，暴露 `/api/chat`、`/api/run_task`、`/api/mcp`、语音等全部端点，无任何认证中间件。网络可达的任何人都能调用完整 AOS 内核。

### HIGH

**S-5: .env 含 6 个服务真实 API key**
`D:\AOS\.env:13-46` — 智谱/SiliconFlow/百度/讯飞/Agnes 等真实 key 在磁盘上。.gitignore 已排除 .env，但任何意外提交或磁盘泄露将同时暴露所有服务。

**S-6: 弱管理凭据**
`D:\AOS\.env:6-7` — `ADMIN_USERNAME=testadmin` / `ADMIN_PASSWORD=testpass123`，可暴力猜测。

**S-7: DEBUG=True 默认值**
`src/utils/config.py:48` — 生产模式下 `/docs`、`/redoc` 暴露，异常详情返回给客户端（`exceptions.py:280-284`）。

**S-8: web/app.py 路径遍历**
`src/web/app.py:2033` 和 `4076` — 用户输入的文件路径未经规范化和目录边界检查，可读取 `../../.env` 等任意文件。

### MEDIUM（摘要）

| # | 位置 | 问题 |
|---|------|------|
| S-9 | `config.py:228` | DEERFLOW_ADMIN_USER 默认 "admin" |
| S-10 | `security.py:263-272` | /web /openclaw /deerflow 路径免认证 |
| S-11 | `security.py:260` | /api/auth/token 公开 + 弱凭据 = 暴力路径 |
| S-12 | `exceptions.py:280-284` | DEBUG 模式下异常详情返回客户端 |
| S-13 | `sandbox.py:417-424` | f-string 模板注入（已列 CRITICAL） |
| S-14 | `task_fingerprint.py:70` | MD5 用于指纹（非密码但已过时） |
| S-15 | `tts_adapter.py:118` | SHA-1 用于缓存键 |
| S-16 | `subprocess_iso.py:101` | 非密码学 random 选 IPC 端口 |
| S-17 | `subprocess_iso.py:111` | 完整 os.environ 传给子进程（含 API key） |
| S-18 | `requirements.txt` | aiohttp>=3.9.0 包含已知 SSRF CVE 版本 |

### 安全亮点（做得好的）

CORS 配置严谨（生产拒绝通配符）、JWT RS256 非对称签名、bcrypt 密码哈希 + 恒定时间比较、速率限制滑动窗口、沙箱环境变量剥离、生产错误消息脱敏、HTTPS 重定向中间件。

---

## 二、架构问题

### A-1 [HIGH] brain.py 退役未执行

AGENTS.md 声明 brain.py 是"待退役老栈"，但实际：
- `src/core/brain.py` 仍是 2021 行的生产主路径
- `api/main.py:23`、`web/app.py:92` 全部调 `get_brain()`
- 近期 commit 持续往 brain.py 加新功能（L6 DeerFlow 技能路由、子 Agent 委派、2.x API 适配）
- **估计 95%+ 流量仍走 brain.py**，FabricHub 路径是并行轨道未替代主路径

### A-2 [MEDIUM] 循环依赖

真实存在的双向循环：
- `core/ → kernel/`：`core/fabric/http_server.py:53` 顶层 import `kernel.wiring`（硬循环）
- `kernel/ → core/`：`kernel/plugins/` 的接缝层导入（设计上可接受）
- `skills/ → core/`：12 个 skill 文件 lazy import `get_brain()`（被 lazy `core/__init__.py` 缓解）
- 三方循环：`kernel → core → brain → skills → kernel`

缓解：大部分用 lazy import。但 `http_server.py:53` 是硬循环，仅靠 Python 缓存半初始化模块才工作。

### A-3 [MEDIUM] kernel/__init__.py 重量级导入

`src/kernel/__init__.py` 在包级别 eager import 55 个符号，来自 10 个子模块。与已改为 lazy 的 `core/__init__.py` 不同，kernel 仍全量加载。任何 `import kernel.types` 都会拉入全部子模块。

### A-4 [LOW] 11 个死模块（从未被导入）

| 文件 | 说明 |
|------|------|
| `common/mcp_control_plane_pb2_grpc.py` | 废弃的 gRPC stub |
| `core/fabric/http_server.py` | 未被任何代码引用 |
| `deerflow/aos_assets.py` | legacy |
| `deerflow/echo_workflow.py` | legacy |
| `kernel/isolation/_bench_adapter.py` | 未使用 |
| `kernel/live.py` | 未使用 |
| `kernel/plugins/failure_monitor.py` | 定义了类但无人调用 |
| `persistence/state_backend.py` | ABC + 实现但无人导入 |
| `utils/cache.py` | 未使用 |
| `utils/cache_manager.py` | 未使用 |
| `utils/db_pool.py` | 未使用 |

### A-5 [LOW] 接口一致性问题

- `SearchAdapter`（`search_adapter.py:53`）：`engine_id` 是类属性而非 `@property`（运行时能工作但与其他 21 个适配器不一致）
- `ScriptsAdapter`（`scripts_adapter.py:114`）：`advertise_capabilities()` 混用 raw string 和 `Capability` enum

---

## 三、运行时 / 性能问题

### R-1 [CRITICAL] asyncio.run() 在已运行事件循环中

| 位置 | 代码 |
|------|------|
| `aci_browser_adapter.py:52` | `asyncio.run(agent.run())` — 从 sync invoke() 调用，若已在 asyncio 上下文中必崩 |
| `tts_adapter.py:217` | `asyncio.run(_save())` — 同上 |
| `agent_runtime_layer.py:237` | `asyncio.run(self.run_workflow_async(...))` — 无条件 |
| `loop_engineering.py:397` | `asyncio.run(loop.run(input_data))` — 同上 |

### R-2 [CRITICAL] async 处理器中直接调用 sync 阻塞

`src/api/main.py` 中 async handler 直接调用 sync brain 方法（无 `asyncio.to_thread` 包装），阻塞整个事件循环：

| 行号 | 调用 |
|------|------|
| 722 | `brain.add_memory(...)` |
| 729 | `brain.memory.sqlite_conn.execute(...)` |
| 741 | `brain.search_memory(...)` |
| 744 | `brain.export_memory()` |
| 766-809 | 会话/任务管理的 6 个端点 |
| 843-876 | meta_route/classify/priority/propose |
| 1389 | `requests.get("http://localhost:11434/api/tags")` |
| 1670-1719 | 语音识别/合成/对话 |

这意味着**一个慢请求会阻塞所有并发请求**（包括 /health）。

### R-3 [HIGH] 无限递归风险

`src/router/llm_router.py:334-337` — `_call_baidu()` token 过期时递归调用自身刷新 token 再重试。若刷新持续失败（如凭据无效），无限递归直到栈溢出。无重试上限。

### R-4 [HIGH] 无界内存增长

| 位置 | 问题 |
|------|------|
| `fabric_hub.py:55` | `_SESSIONS` dict — session 数无限增长，无 TTL/驱逐 |
| `task_runner.py:45` | `self._tasks` — 完成的任务永不清理 |
| `brain.py:379` | `self._tasks` — 同上 |
| `agency_agents.py:735` | `self._tasks` — 同上 |

### R-5 [HIGH] 竞态条件

| 位置 | 问题 |
|------|------|
| `gateway.py:99-105` | `get_session()` — 两个并发 async task 可能同时创建 session，泄漏一个 |
| `main.py:1766-1771` | `_fabric_hub_cache` — 两个并发请求可能各创建一个 FabricHub（重构造） |
| `llm_router.py:474,478` | `providers[provider]["available"]` — 无线程保护的可用性标记修改 |
| `brain.py:589-607` | `self._tasks` — worker 线程和主线程无锁并发修改 |

### R-6 [HIGH] 单例线程不安全

- `SkillRegistry.__new__()`（`skills/base.py:113-133`）：check-and-set 无锁，并发创建可能双实例
- `get_brain()`（`brain.py:2013-2021`）：同上。且 `UnifiedBrain.__init__` 内部用 `ThreadPoolExecutor`（`brain.py:683`），竞态窗口大

### R-7 [MEDIUM] 资源泄漏

| 位置 | 问题 |
|------|------|
| `brain.py:58` | `requests.Session()` 创建但从未 close |
| `jina_reader.py:73` | 同上 |
| `marketplace.py:274` | `requests.get(url)` 无 timeout，可能永久挂起 |
| `openclaw_adapter.py:357` | `subprocess.Popen` 启动但无对应 terminate/wait 清理 |
| `tts_adapter.py:163-179` | `new_event_loop()` 关闭时 async generator 未 `aclose()` |

---

## 四、代码质量

### Q-1 [HIGH] F821 未定义名（运行时必崩）

**src/ 中 13 处：**

| 文件 | 行 | 未定义名 |
|------|-----|---------|
| `voice_chiplet.py` | 146,147,175,373 | `Iterator` 未导入（4处） |
| `litellm_adapter.py` | 144 | `Iterator` 未导入 |
| `stt_adapter.py` | 200 | `Iterator` 未导入 |
| `tts_adapter.py` | 136 | `Iterator` 未导入 |
| `openclaw_adapter.py` | 57 | `Optional` 未导入 |
| `persona.py` | 175 | `ensure_default_template` 未定义 |
| `kernel.py` | 99 | `permissions` 未定义 |
| `wiring.py` | 34,64 | `Dict` 未导入（2处） |

### Q-2 [MEDIUM] Ruff 统计

**src/**: 538 个错误

| 规则 | 数量 | 说明 |
|------|------|------|
| E402 | 349 | 模块级 import 不在文件顶部（77% 在 `agency_roles/__init__.py`） |
| F401 | 117 | 未使用 import（68 在 `skills/__init__.py`，16 在 `kernel/__init__.py`） |
| E702 | 25 | 一行多语句（`companion.py` 265 个分号占大头） |
| F841 | 23 | 未使用局部变量 |
| F821 | 13 | **未定义名**（见 Q-1） |

**tests/**: 76 个错误（20 个 F821，主要在 test_e2e.py 和 test_final.py）

### Q-3 [LOW] 重复逻辑

- `try/except/logger.warning` 模式在 50 个文件中重复 200+ 次，可提取为 `@safe_call` 装饰器
- 22 个适配器类重复相同的 `BaseAgentAdapter` 骨架方法签名
- 24 个文件独立 `json.load()` 配置文件，4 个文件独立 `load_dotenv()`，16 个文件散列 `os.environ.get()`

### Q-4 [LOW] 类型标注缺失

参数标注良好（83-100%），但**返回类型标注严重不足**：
- `api/main.py`: 121 个函数仅 2% 有返回类型
- `compliance/audit.py`: 33%
- `memory/memory.py`: 57%

---

## 五、测试覆盖

### 总体覆盖率：5%

80 个可运行测试通过，覆盖 38,213 条语句中的 1,814 条。

### 关键 0% 覆盖模块

**kernel/ 全盲：**

| 文件 | 语句数 | 重要性 |
|------|--------|--------|
| `plugins/fabric_hub.py` | 386 | 唯一能力路由枢纽 |
| `v5_bridge.py` | 164 | 主 API 桥接层 |
| `system.py` | 71 | 系统装配入口 |
| `wiring.py` | 122 | 插件装配 |
| `isolation/subprocess_iso.py` | 297 | 核心故障隔离机制 |
| `plugins/orchestration_chiplet.py` | 121 | 流水线执行器 |
| `layers/*` | ~450 | 四层结构全部 |

**core/fabric/ 全盲：**
- 20 个适配器文件（~2,900 语句）全部 0%
- `resilience.py`（guarded_import L1 稳定性机制）0%

### 覆盖较好的模块

| 文件 | 覆盖率 |
|------|--------|
| `kernel/types.py` | 98% |
| `kernel/compliance.py` | 90% |
| `core/fabric/registry.py` | 90% |
| `core/fabric/capability.py` | 100% |
| `api/security.py` | 60% |

### Flaky 测试根因

1. **真实网络调用**：`test_kernel.py` → `wiring.py:124` → `cloud.health()` → OpenAI API（超时）
2. **原生扩展崩溃**：zvec/cognee/rocksdb 触发 0xC0000005（conftest 已排除）
3. **共享 SQLite**：`test_database.py` 跨运行数据碰撞（xfail 已标记）
4. **重型导入链**：`test_fabric_hub.py` 的 `FabricHub()` 触发 18 个适配器的 guarded_import

### 完全缺失的测试类型

- 性能/延迟基准测试
- 并发/竞态测试
- 端到端集成测试（script-style 的 test_e2e.py 不兼容 pytest）
- MCP 协议测试（`mcp/protocol.py` 293 语句 0%）
- 子进程隔离测试（核心故障隔离功能 0%）

### test_kernel_units.py 质量评估

- **优点**：纯数据结构测试真实（ModuleVersion 解析/比较/哈希）、ABC 契约用真实 Stub 验证
- **问题**：`test_build_default_kernel` 触发真实 OpenAI 调用；V5Bridge 测试 4 层 mock 测的是 mock 而非真实路由；缺少错误路径测试

---

## 六、优先级排序

### P0 — 立即修复（安全 / 运行时崩溃）

| # | 问题 | 位置 | 成本 |
|---|------|------|------|
| 1 | F821 未定义名 | 13 处（见 Q-1） | 每处加 1 行 import |
| 2 | http_server.py 零认证 | `http_server.py:141` | 绑定 127.0.0.1 或加 API key 检查 |
| 3 | DEBUG=True 默认值 | `config.py:48` | 改为 `False` |
| 4 | asyncio.run() 双循环 | 4 处（见 R-1） | 改用 `asyncio.to_thread` 或检测现有 loop |
| 5 | _call_baidu 无限递归 | `llm_router.py:334` | 加 max_retry 参数 |

### P1 — 短期修复（稳定性 / 数据完整性）

| # | 问题 | 位置 | 成本 |
|---|------|------|------|
| 6 | async handler 调用 sync 阻塞 | `api/main.py` ~20 处 | 包 `await asyncio.to_thread(...)` |
| 7 | 无界内存增长 | `_SESSIONS` / `_tasks` 等 4 处 | 加 TTL 驱逐或 LRU |
| 8 | 单例竞态 | `SkillRegistry` / `get_brain()` | 加 `threading.Lock` |
| 9 | kernel/__init__.py lazy 化 | `kernel/__init__.py` | 套用 `core/__init__.py` 的 `__getattr__` 模式 |
| 10 | `subprocess_iso.py` 环境变量泄露 | `subprocess_iso.py:111` | 仿 `SkillSandbox._safe_env()` 剥离密钥 |

### P2 — 中期改进（架构债 / 可维护性）

| # | 问题 | 位置 | 成本 |
|---|------|------|------|
| 11 | brain.py 退役计划 | 全局 | 架构级，需要切流验证 |
| 12 | 11 个死模块归档 | 见 A-4 | 移到 `_archive/` |
| 13 | 适配器测试覆盖 | 20 个适配器 0% | mock 外部依赖 + 单元测试 |
| 14 | FabricHub 测试提速 | `test_fabric_hub.py` | mock guarded_import 或 lazy 初始化 |
| 15 | aiohttp 版本锁定 | `requirements.txt` | `aiohttp>=3.10.0` |

### P3 — 长期（代码质量 / 技术债）

| # | 问题 | 位置 |
|---|------|------|
| 16 | 200+ 处 try/except/logger 重复 | 50 个文件 |
| 17 | 返回类型标注补全 | `api/main.py` 2% |
| 18 | E402 / F401 ruff 清理 | 349 + 117 处 |
| 19 | `http_server.py` 硬循环依赖 | `http_server.py:53` |
| 20 | mypy 安装并跑通 | 环境 |

---

## 七、复核命令

```bash
# F821 未定义名
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m ruff check src/ --select F821

# 安全扫描：asyncio.run 在 sync 函数中
python -c "import pathlib
for f in pathlib.Path('src').rglob('*.py'):
    lines=f.read_text(encoding='utf-8',errors='replace').splitlines()
    for i,l in enumerate(lines):
        if 'asyncio.run(' in l:
            print(f'{f}:{i+1}: {l.strip()}')"

# 无界 dict 增长（模块级 Dict[str, ...] 无 maxsize/TTL）
python -c "import pathlib
for f in pathlib.Path('src').rglob('*.py'):
    text=f.read_text(encoding='utf-8',errors='replace')
    if 'Dict[str' in text and ('_SESSIONS' in text or '_tasks' in text):
        print(f)"

# 覆盖率
"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_kernel_compliance.py tests/test_skills.py tests/test_security_middleware.py tests/test_brain_smoke.py tests/test_route_failover.py --cov=src --cov-report=term-missing --tb=no -q

# 死模块检测
python -c "import pathlib,re
for f in pathlib.Path('src').rglob('*.py'):
    mod=f.stem
    if mod.startswith('_'): continue
    refs=sum(1 for g in pathlib.Path('src').rglob('*.py') if g!=f and re.search(rf'\b{mod}\b',g.read_text(encoding='utf-8',errors='replace')))
    if refs==0: print(f'{f}: 0 importers')"
```

---

**报告结束**。5 路扫描全量结论，所有数据带文件:行号可复核。
