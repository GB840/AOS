# AOS 全项目审计报告（2026-07-11）

> 范围：D:\AOS 全仓（src/、scripts/、web/、external/、配置）。触发：用户 `/web/` 出现
> `bad_gateway` 502，要求"全项目检查、全方位审视，把漏洞和优化项理出来"。
> 方法：双探查代理宽扫 + 关键项亲自 runtime 核实（含"信任但验证"纠正一处误报）。
> 危险等级：🔴高 🟠中 🟡低 ✅正面。

---

## 0. 本次 bad_gateway 专项（用户直接痛点）

**现象**：`{"error":"bad_gateway","detail":"Cannot connect to host 127.0.0.1:8501 ...","upstream":"http://127.0.0.1:8501/web/"}`

**根因（已核实）**：`src/api/gateway.py:40` 把 `/web/*` 反向代理到 `http://127.0.0.1:8501/web/`（Streamlit 控制台）。该上游**未运行** → 连接被拒 → 502。**不是网关代码 bug**，是上游（web 服务）没起。
- 本会话中是我用 `uvicorn` 直起 AOS、没带起 web 服务所致（supervisor 才会自动拉 web）。
- `scripts/aos_supervisor.py:166` 确实把 web 列为 `required` 自动拉起——只要走 supervisor 就正常。

**连带发现（真问题）**：
- 🟠 `gateway.py` 无**存活门控/重试/熔断**：上游挂即瞬时 502，且错误体直接把内部 `host:port/path` 回给客户端（见下"信息泄露"）。建议加 `/web/` 启动探测 + 友好降级页。

---

## 1. 安全漏洞

### 🔴 [HIGH] 鉴权门只认 `API_KEY`、不认 `API_KEY_HASH` —— 安全配置反而关鉴权
- 位置：`src/api/security.py:321`（`if config.API_KEY:`）+ `src/utils/config.py:51-52`
- 机制：中间件仅当 `config.API_KEY` 非空才要求密钥；`config.API_KEY_HASH`（官方推荐的哈希口令，生产强制）**完全不被中间件读取**。
- 后果：运维按文档只配 `AOS_API_KEY_HASH`（不配 `AOS_API_KEY`）→ `config.API_KEY=None` → `if config.API_KEY:` 跳过 → **全站匿名可访问**。
- 核实纠正：安全代理原报"当前已全匿名"——**误报**。本环境 `.env` 有 `API_KEY=TK-...` 且 runtime 实测 `config.API_KEY='TK-...'` 已加载、无 key 实测返回 401，鉴权**当前生效**。但上述潜伏缺陷对"只配哈希"的部署是真实可利用的 HIGH。
- 修复：中间件同时校验 `API_KEY`（恒定时间比较原文）与 `API_KEY_HASH`（bcrypt 校验）；二者至少其一必须配置，否则启动 fail-fast（与 keystore 铁律一致）。

### 🔴 [HIGH] 502 错误泄露内部地址（信息泄露）
- 位置：`src/api/gateway.py:146` → `{"error":"bad_gateway","detail":str(e),"upstream":target}`
- 客户端可触发 502 即拿到内部 `http://127.0.0.1:8501/...`、host、port、路径。属低成本的架构/部署信息泄露。
- 修复：仅返回 sanitize 后的通用信息（如 `{"error":"bad_gateway","upstream":"web"}`），内部细节写日志。

### 🟠 [MED] 上游鉴权"有头即放行"
- 位置：`src/api/security.py:315-317` `_validate_upstream_auth`：只要请求带任意 `Authorization` 头即返回 `True`。伪造头即可过上游校验。
- 修复：改为校验**有效令牌**（与 `API_KEY_HASH`/JWT 同一套），而非"存在即放行"。

### 🟠 [MED] 密钥比较非恒定时间（时序侧信道）
- 位置：`src/api/security.py:321` `api_key == config.API_KEY`。应改用 `hmac.compare_digest`（与项目"凭据铁律"一致，个人级 API-Key 比较也应收敛到此）。

### 🟠 [MED] CORS 条件性危险组合
- 位置：`src/api/main.py:96-103` `allow_credentials=True` + `allow_origins`。当前 `ALLOWED_ORIGINS=localhost:8501,8000`（安全）；但若部署者把 `ALLOWED_ORIGINS=*`，即构成"带凭据的通配符跨域"。建议：`allow_credentials=True` 时硬性拒绝 `*`。

### 🟠 [MED] `kernel/router.py:103` `exec(..., {"__builtins__":__builtins__})` —— RCE 原语（疑似遗留死代码）
- 用户输入代码经 `exec` 以**完整 builtins** 执行。经追溯该 `register_builtins/get_router` 未被活路由 `src/router/llm_router.py` 导入，疑为 v1 遗留。当前未接入 → 非活跃漏洞；**一旦被接线即 Critical**。建议：删除或严格沙箱（禁用 builtins + 白名单）。

### 🟡 [LOW] `.secrets/` 明文口令/私钥 + Windows `chmod 0o600` 被忽略
- 位置：`src/utils/keystore.py:45`（注释已承认 Windows 忽略 0o600）；`.secrets/jwt/private.pem`、`.secrets/deerflow_admin_password` 依赖默认 ACL。已 gitignore，仅落盘风险。

### ✅ 正面确认（非问题）
- 仓库**未提交任何密钥**：`git ls-files` 仅跟踪 `.env.example`；`.env`/`.env.*`/`cookies.txt`/`.secrets/` 全在 `.gitignore`（第68-72行）。
- JWT 用 **RS256 非对称**（keystore.py，生产缺密钥 fail-fast）；`/api/sandbox/*` 默认 `SANDBOX_API_ENABLED=False` → 403 关闭。
- `kernel/router.py:88` 的 `eval` 输入经正则剥离且禁 builtins，仅做数学求值，低风险。

---

## 2. 稳定性 / 可靠性

### 🔴 [HIGH] `aiosqlite` 不在依赖清单 → 缺包即启动崩溃
- 位置：`src/core/pool/connection_pool.py:15` `import aiosqlite`；但 `requirements*.txt`/`pyproject.toml` 未见该依赖（仅 streamlit 在列）。本会话实测缺它 AOS 直接 ImportError 起不来（已临时 `pip install` 修复）。
- 修复：把 `aiosqlite`（及所有 core 期导入的库）补进 `requirements.txt`/lock，避免"换环境即崩"。

### 🟠 [MED] `brain.py` 1965 行单体 + 重型导入期初始化 → 冷启 ~2min
- 位置：`src/core/brain.py:1`。`UnifiedBrain.__init__` 同步加载 mem0/ChromaDB/Hermes(51插件)/AG2/router，单 worker uvicorn 绑定 8000 需 ~2min（supervisor `START_TIMEOUT aos=300`）。
- 风险：长 chat 期间事件循环被占时 `/health` 超时 → 误杀（已知死锁铁律已修，但冷启/重载仍脆弱）。
- 优化：惰性初始化（首次请求才建重组件）、或拆子进程；与 v1.0 内核"薄缝"+ 双轨渐进接管方向一致（见 #173）。

### 🟠 [MED] `aos_bridge.py` 死代码（误导）
- 位置：`src/kernel/aos_bridge.py` 全文件仅被自身引用；`src/api/main.py:226` 实际挂载的是 `v5_bridge.V5Bridge`。建议删 `aos_bridge.py`，保留一个桥。

### 🟠 [MED] 内核 31 模块多数未接线（仅 standalone 单测）
- 位置：`src/kernel/`（除 `system.py`/`wiring.py`/`v5_bridge` 外）。见 `docs/KERNEL_RECONCILIATION.md` —— 这是 v1.0 主线待办（#172 已接 ModelGateway + 双轨路由，余下待 #173 下沉）。

### 🟡 [LOW] 网关无重试/熔断，探活仅启动期
- 位置：`src/api/gateway.py:249` `probe_upstreams` 只在启动时跑一次。运行时上游抖动无感知。建议加周期探活 + 上游失败友好页。

---

## 3. 代码质量 / 架构

### 🟠 [MED] `gateway.py:91-92` `_rewrite_location` 幻影逻辑
```python
if not new.path.startswith(request.url.path.split("/")[1:2] and "/"):
    pass   # 列表恒真→"/"，绝对路径必以/开头，且块内仅 pass —— 死代码
```
- 无功能影响但是误导。应删除或补全真实重写逻辑。

### 🟠 [MED] `kernel/router.py` 疑似 v1 遗留 RCE 代码（见安全 §MED）
- 与活路由无关，建议清理或隔离。

### ✅ 正面确认
- 已知 RateLimitMiddleware 死锁**已修复**（锁仅包记账段，`await call_next` 在锁外，注释明确）。
- 仓库无 FIXME/XXX/HACK 堆积（仅少量 TODO）。
- 目录无显著冗余（顶层无 `aos_deerflow/`/`common/`；`src/deerflow` vs `external/deer-flow` 是 vendor 分工）。

---

## 4. 优化项汇总（可行动）

| # | 类别 | 优化 | 优先级 |
|---|------|------|--------|
| O1 | 安全 | 中间件同时校验 `API_KEY`+`API_KEY_HASH`，缺则 fail-fast | 🔴 |
| O2 | 安全 | 502 错误体 sanitize，内部细节仅入日志 | 🔴 |
| O3 | 依赖 | `aiosqlite` 等补进 requirements/lock | 🔴 |
| O4 | 稳定 | 网关加存活门控 + 重试 + 上游失败友好页 | 🟠 |
| O5 | 性能 | brain.py 惰性初始化 / 拆子进程，降冷启 | 🟠 |
| O6 | 质量 | 删 `aos_bridge.py` 死代码，统一用 `v5_bridge` | 🟠 |
| O7 | 质量 | 修/删 `gateway.py:91-92` 幻影逻辑 | 🟠 |
| O8 | 安全 | `api_key == config.API_KEY` → `hmac.compare_digest` | 🟠 |
| O9 | 安全 | 上游鉴权校验有效令牌而非"有头即放行" | 🟠 |
| O10 | 安全 | CORS `allow_credentials=True` 时拒绝 `*` | 🟠 |
| O11 | 架构 | 内核接线推进（#173 brain.py 渐进下沉） | 🟠 |
| O12 | 安全 | 清理/沙箱 `kernel/router.py` 的 `exec` 遗留 | 🟠 |

---

## 5. 总体评级

- **安全**：🟠 中偏高。本环境鉴权生效（已核实纠正误报），但存在"只配哈希即关鉴权"的潜伏 HIGH 与 502 信息泄露 HIGH，须修。
- **可靠性**：🟠 脆弱。依赖清单缺失 + 单体冷启是主要风险；已知死锁已修、网关逻辑正确。
- **代码质量**：🟢 良好。无大规模失控，少量死代码/幻影逻辑待清。
- **架构**：🟠 进行中。v1.0 内核已立项并部分接线（#171/#172），brain.py 下沉（#173）待续。

**建议立即处理**：O1、O2、O3（三个 🔴，均为低风险高收益的确定性修复）。其余按优先级排期。
