# AOS 生产运行与运维指南

> 目标：**一个命令拉起全栈、重启不破、进程守护、稳定驻留。**
> 不要再用零散的 `uvicorn` / `streamlit` / `node` 手动起各服务。

---

## 1. 架构一览

AOS 由四个常驻服务组成，对外只暴露 **单端口网关 `:8000`**（AOS 网关把
`/web`、`/openclaw`、`/deerflow` 反代到下游）。

| 服务 | 端口 | 职责 | 启动器 |
|------|------|------|--------|
| DeerFlow 网关 | 2026 | 子智能体运行时（真实 `assistant_id` 路由） | `scripts/run_deerflow.py` |
| AOS API+网关 | 8000 | 统一入口 / 编排 / 单端口反代 | `uvicorn src.api.main:app` |
| Web 控制台 | 8501 | Streamlit（`/web` 下） | `streamlit run web/console.py` |
| OpenClaw 网关 | 18789 | 个人 AI 助手框架（node） | `openclaw.mjs gateway run` |

依赖顺序：**DeerFlow → AOS**（AOS 在 DeerFlow 健康后才以 REAL 模式启动）；
Web / OpenClaw 相互独立。

---

## 2. 唯一入口（推荐）

```bash
# 方式 A（跨平台，推荐）
python scripts/aos_supervisor.py

# 方式 B（Windows PowerShell 包装）
.\scripts\start_aos.ps1
```

`aos_supervisor.py` 会：
1. 按依赖顺序拉起四个服务；
2. 每个服务启动后**健康检查门**（HTTP 200 / TCP 连通）才继续；
3. **进程守护**：任何服务进程死亡会自动拉起（带退避，5 次/分钟内触发指数退避至 30s）；
4. **优雅停止**：收到 `Ctrl+C` / `SIGTERM` 时逐个 `terminate`，超时则 `kill`；
5. 把 PID 写入 `logs/aos_pids.json`。

---

## 3. 常用命令

```bash
# 启动全栈并常驻（默认：监督模式，死了自动拉起）
python scripts/aos_supervisor.py

# 仅查看各服务健康状态后退出（不修改任何进程）
python scripts/aos_supervisor.py --check

# 停止本监管器启动的全部服务
python scripts/aos_supervisor.py --stop

# 只起某个服务 / 跳过某个服务
python scripts/aos_supervisor.py --only aos
python scripts/aos_supervisor.py --skip web

# 启动一次即脱离（服务继续后台运行，监管器退出，不守护）
python scripts/aos_supervisor.py --no-supervise
```

环境覆盖（可选）：`AOS_VENV`、`DEERFLOW_VENV`、`NODE_BIN`、`OPENCLAW_TOKEN`、
`OPENCLAW_MJS`。默认已按本机路径解析。

---

## 4. 三个「重启不破」的关键修复

### 4.1 DeerFlow 认证 401（dotenv / CWD 错位）
DeerFlow 认证中间件在**请求时直接读 `os.environ["DEER_FLOW_AUTH_DISABLED"]`，
但其 `.env` 由 `load_dotenv()` 按**进程 CWD** 解析。若从 `backend/` 裸起
`uvicorn app.gateway.app:app`，`load_dotenv()` 找不到仓库根 `.env` → 认证标志
永不进 `os.environ` → 每个 `/api/*` 返回 401，而 `config.yaml` 仍因 legacy 路径
搜索正常加载（表现就是"DeerFlow 看着健康却处处 401"）。

**修复**：必须用 `scripts/run_deerflow.py` 启动——它先显式
`load_dotenv(repo_root/.env, override=True)` 灌入 `os.environ`，再 `chdir` 到仓库根，
最后才起 uvicorn。**不要裸跑 `uvicorn app.gateway.app:app`。**

### 4.2 `agents_api` 配置自愈（可重现）
子智能体的真实 `assistant_id` 路由依赖 DeerFlow `config.yaml` 的
`agents_api.enabled=true`。该文件位于 `external/`（gitignored），重 vendoring 即丢。

**修复**：`run_deerflow.py` 启动时调用 `_ensure_agents_api_enabled()`，若未开启则
自动写入 `enabled: true`（yaml 优先 + 文本兜底）。**每次启动自动生效，无需手动改。**

### 4.3 依赖自洽（aos venv 不崩）
AOS `main.py` 顶层 `import mcp`，此前 `mcp` 仅靠 `AOS_EXTRA_SITE` 从 default venv
借入——干净用 aos venv 重启即崩。现已把 `mcp/ag2/litellm/PyJWT/psycopg2-binary`
显式装进 aos venv。

⚠️ **依赖冲突已修正**：`mcp==1.28.0` 要求 `pyjwt>=2.10.1`，而 `zhipuai` 要求
`pyjwt<2.9.0`——二者硬冲突。因 AOS 不直接 `import zhipuai`（智谱走 litellm 的
OpenAI 兼容透传），已将 `zhipuai` 移出必需依赖、`PyJWT` 升到 `>=2.10.1`。
`pip install -r requirements.txt` 现在可干净成功。

```bash
# 装机 / 换新 venv 后，一键装齐生产依赖
<your-aos-venv>\Scripts\python.exe -m pip install -r requirements.txt
```

### 4.4 聊天拖垮全 API（跨 `await` 持锁死锁）—— 致命并发 bug

**症状**：一旦发起 `/api/chat`，整个 API 冻结——`/health` 全部超时、聊天
`>180s` 不返回，连 handler 第一行日志都不打。重启后复现。

**根因**（py-spy 进程栈 dump 一发命中）：`RateLimitMiddleware.dispatch` 把
`await call_next(request)` 写在了 `with self._lock:`（`threading.Lock`）块内。
单 worker uvicorn 下的死锁链：
1. 请求 A 持锁，`await` 长耗时的 `brain.chat` 下游；
2. 事件循环转去处理请求 B（如 `/health` 轮询），B 进入 `dispatch` 执行
   `with self._lock` —— 这是**同步 acquire，直接阻塞事件循环线程本身**；
3. 事件循环再也回不到 A 的续体去释放锁 → **全进程冻结**。

**修复**：`threading.Lock` 只保护限流簿记（deque 读写），锁内算出 `remaining`，
**`await call_next(request)` 移到锁外**。详见 `src/api/security.py:286-320`。

> 铁律：**任何 asyncio 中间件/handler，绝不可在持有 `threading.Lock` 期间
> `await`。** 单 worker 下这必然死锁整个事件循环。

**配套加固（探针分层，防止监管器误杀）**：
- `/health` 改为**轻量存活探针**（秒回 `{"status":"alive"}`，不做任何组件检查），
  聊天满载时事件循环仍能瞬间应答，监管器不会误判 AOS 死亡而重启；
- `/health/deep` 为**完整就绪探针**：`asyncio.to_thread(brain.health_check)`
  跑 21 组件深检 + 5s 结果缓存，且已加入中间件公开路径豁免；
- `/api/chat` 的 `route_intent` 与 `brain.chat` 均用 `asyncio.to_thread` 包裹，
  把同步重活移出事件循环，聊天期间 `/health` 延迟稳定在 `~20ms`。

---

## 5. 排障：进程活着但请求全卡

当"进程在、端口开、但所有请求超时"时，日志往往什么都看不到（handler 没进去）。
用 **py-spy** 抓运行进程的线程栈，是定位事件循环死锁/阻塞的决定性手段：

```bash
pip install py-spy
py-spy dump --pid <AOS_PID>      # PID 见 logs/aos_pids.json
```

- 若 `MainThread` 死堵在某个 `with self._lock:` / 同步 IO，而 `asyncio_0`
  线程池空闲 → 事件循环被同步阻塞（本次 bug 的指纹）。
- 若卡在下游网络 recv → 是下游服务慢，不是本地死锁。

---

## 6. 日志

所有日志在 `logs/`：
- `supervisor.log` —— 监管器自身（启动顺序、健康门、重启、停止）
- `<service>.log` —— 各服务 stdout/stderr（deerflow / aos / web / openclaw）

---

## 7. 已知边界（上线前请自行补齐）

- **单节点**：监管器在本机进程级守护，无跨机故障转移。生产多副本请外包给 systemd /
  supervisor / K8s，把 `aos_supervisor.py` 当成 `ExecStart` 的进程即可。
- **认证为本地开发态**：DeerFlow 经 `DEER_FLOW_AUTH_DISABLED=1` 关闭了网关认证；
  AOS 自身 API 有 `X-API-Key` 校验。对外暴露 `:8000` 前请加 **TLS 反向代理** 与
  真实鉴权，不要裸暴露内网。
- **配置持久**：`external/deer-flow/config.yaml` 受 gitignore 保护（避免 vendored
  冲突），其 `agents_api` 由监管器自愈；其余 DeerFlow 配置改动需在本地维护。
- **OpenClaw**：node 全局包，版本跟随 npm；监管器自动定位 `openclaw.mjs`。
