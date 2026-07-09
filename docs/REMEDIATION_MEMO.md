# AOS 整改备忘录（REMEDIATION MEMO）

> 汇总自 2026-07-09 ~ 07-10 三轮深度 review：架构违规 + 仓库卫生 + 安全审计。
> 所有条目均经代码实证核对（file:line）。执行顺序按严重度 P0→P1→P2，互不影响则并行。

---

## 一、执行总览（按严重度）

| 优先级 | 任务 | 内容 | 状态 |
|---|---|---|---|
| **P0** | #107 | 根除默认凭证 + 离线 JWT 伪造 (RS256+keystore) | ✅ `1b30e0c` |
| **P0** | #108 | 收回/加固免认证端点（G2/G3/G4） | ✅ `54ca738` |
| **P0** | #109 | 治理 `/api/sandbox/exec` 任意命令 | ✅ `0075c01` |
| **P0** | #113 | Docker 弱口令+无隔离 + 默认不强制 HTTPS | ✅ `a1672ee` |
| **P1** | #110 | shell=True 命令注入排查加固 | ✅ `9d5b18b` |
| **P1** | #111 | exec(user_code) RCE 隔离确认 | ✅ `f9aa868` |
| **P1** | #112 | eval() 规则执行去危险 | ✅ `6d5c8d6` |
| **P1** | #114 | 日志脱敏 + 恒定时间比较（G5 已含于 #107/#108） | ✅ `4a29e3d` |
| **P1** | #115 | CI + 安全中间件单测（含 #96） | ✅ `5546909` |
| P1 | #95/#96 | 环境可复现 + 测试可收集 | 🟡 执行中（产物已就绪，待测试确认后提交） |
| P1 | #98 | 删除自研 OpenClaw 废弃代码 | 🔲 待执行 |
| P1 | #100/#101 | 路由收编 fabric + brain.py 拆分 | 🔲 待执行 |
| P2 | #99/#102/#103 | 测试归位 / src/src 嵌套 / 运行时产物 | 🔲 待执行 |
| P2 | #104 | 补提交建立版本保护 | 🔲 待执行 |
| P2 | #105/#106 | 校正 README / 统一表数 | 🔲 待执行 |
| 待查 | #11 | 缺索引（表数实际 42，非 38） | 🔍 待核实 |
| 待查 | #13 | 依赖锁定（requirements.txt 有锁，pyproject 待确认） | 🔍 待核实 |

---

## 二、用户 15 项安全清单 — 核对结论

| # | 指控 | verdict | 证据 / 校正 |
|---|---|---|---|
| 1 | 硬编码默认凭证 | ✅ 坐实+升级 | `config.py:26-31,147`；HS256+已知密钥=离线自签管理员 JWT（G1） |
| 2 | .env 明文密钥 | ⚠️ 部分缓解+坐实一项 | `.env` 已被 `.gitignore:68` 排除、未入库、历史无 TK-；但 `API_KEY==UNIFIED_API_KEY`（复用）已确认 |
| 3 | shell=True 注入 | ✅ 坐实(条件) | `devops.py:33`，需查调用方 |
| 4 | exec(user_code) | ✅ 坐实 | `sandbox.py` executor 模板内子进程 exec，仍 RCE |
| 5 | eval() | ✅ 坐实 | `factory.py:141` / `composition.py:78` 正则白名单后 eval |
| 6 | 端点免认证 | ✅ 坐实+补充 | 漏列 /docs 等(G2)、/api/auth/token 免限流(G3)、我加的技能端点(G4) |
| 7 | /api/sandbox/exec | ⚠️ 部分校正 | 需 X-API-Key，但共享静态密钥+复用；local/docker 决定 RCE 范围 |
| 8 | HS256 | ✅ 坐实 | `security.py:27,124` → 改 RS256 |
| 9 | 日志未脱敏 | ⚠️ 部分校正 | 无 exc_info=True，但 detail=str(e) 回显内部异常 |
| 10 | DB 单连接+锁 | ✅ 坐实 | `memory.py:177-179`，可用性瓶颈 |
| 11 | 缺索引 | ❓ 待查 | 表数实际 42 |
| 12 | Rate limit 内存 | ✅ 坐实 | `security.py:240-275`，单进程 |
| 13 | 依赖未锁定 | ❓ 待查 | requirements.txt 有锁，pyproject 待确认 |
| 14 | Docker 安全 | ✅ 坐实 | 弱默认口令 + 无隔离 |
| 15 | CI/单测 | ✅ 坐实 | 无 .github/workflows |

---

## 三、自补扫描发现的遗漏（GAP）

- **G1 离线 JWT 伪造（最高危）**：HS256+默认密钥 → 离线自签任意身份 admin token。
- **G2 `/docs`、`/redoc`、`/openapi.json` 免认证**：API schema 全泄露（放大器）。
- **G3 `/api/auth/token` 免限流 + admin/admin**：中间件顺序导致豁免即跳过限流。
- **G4 我上轮加的 `/api/skills/deerflow`、`/api/skills/refresh` 免认证**：自我回退，必须收回。
- **G5 明文比较非恒定时间**：`authenticate_user` `==`(security.py:144)、API Key `!=`(security.py:212)。
- **G6 默认不强制 HTTPS**：`HTTPSRedirectMiddleware` 仅 production 启用，默认 development 明文。
- **G7 错误详情外泄**：多端点 `detail=str(e)`。
- **G8 `find_skills.py:70` 非注入**：仅展示字符串，不执行（非漏洞）。
- **G9 `POSTGRES_PASSWORD` 默认空串**（config.py:37）额外弱凭证。
- **G10 正面**：SecurityHeadersMiddleware 已加；SQL 注入 DB 层未见；密钥未进 git 历史；CORS 非通配。

---

## 四、执行纪律

1. 每次改动后必须热重载（kill supervisor master PID）→ 等稳定 → 验 `/health`(200) + 验认证 + 验聊天主链路不破。
2. 每个 P0/P1 任务独立 commit，信息明确；不批量混提交。
3. 架构类（#98/#100/#101）放在安全类之后，且分步验证不破冷启动。
4. 不删除任何仍在运行路径上的代码，除非先用 adapter 收编。

---

## 五、与既有 #95–#106 的关系

- #97(硬编码密钥) 已并入 #107。
- 本轮 #107–#115 为攻击面维度，与可运行性(#95/#96)/铁律(#98)/架构(#100/#101)/卫生(#99/#102/#103)/文档(#105/#106) 互不覆盖、并行。
- #100(路由收编) 修"绕过薄缝"架构违规；#108 修"绕过认证"安全违规，两件事。

---

## 六、#95/#96 环境可复现 + 测试可收集（执行记录）

**问题定位**：
- 运行时实际由 supervisor 经 `AOS_EXTRA_SITE`/`PYTHONPATH` 接入 `default` venv 的 site-packages，而非隔离 venv；`requirements.txt` 为人工精选清单，缺少全量锁定 → 可复现性缺口（#95 / #13）。
- 测试套件在 `tests/` + `conftest.py` 下已可被 pytest 完整收集（48 项），但部分旧断言与「新安全契约 / 真实 42 表 schema」不一致 → #96。

**已落地产物**（待独立提交）：
1. `requirements.lock` — 由真实运行时 venv（`default`）`pip freeze` 生成的确定性快照（149 项全量锁定，含 ag2/mcp/fastapi/pydantic/langgraph/chromadb 等）。配合 `requirements.txt` 使用：`pip install -r requirements.lock`。
2. `.env.example` — 补全缺失的运行时开关（AOS_ADMIN_PASSWORD / AOS_DEERFLOW_ADMIN_PASSWORD / OPENAI/DEEPSEEK/ZHIPU 网关 / QDRANT / CORS / 日志级别等），`cp .env.example .env` 即得可运行模板。
3. `docs/REPRODUCE.md` — 可复现重建手册：venv 创建 → 依赖安装（requirements.lock）→ `.env` 生成 → supervisor 启动 → 冒烟验证。
4. `tests/test_api.py` — `client` fixture 注入确定性 `API_KEY` + `X-API-Key` 头，使主链路在「已认证」前提下验证；`/health` 断言兼容新响应体 `{status,service,ts}`。对齐 #108 强制鉴权后的契约。
5. `tests/test_database.py` — 表数断言 `38 → 42`（#11/#106 校正：真实 ORM 注册物理表数为 42）。

**验证**：`test_security.py` 11 passed ✓；`test_database.py`(count/idempotent/seed/orm) 4 passed ✓；`test_api.py` 执行中。
