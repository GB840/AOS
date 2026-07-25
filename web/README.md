# 单创OS · Web 网关层（Node 网关 + Python 微服务）

本目录是单创OS「Node 网关 + Python 微服务」架构的**前端/网关层**（对齐 TS/Node AI 全栈综述的核心原则）：
前端**绝不直连**大模型或 Python 内核，所有 `/api/aos/*` 请求统一经 Node 网关反向代理到 Python AOS 内核（FastAPI，默认 `:8000`）。

## 目录

| 应用 | 端口 | 定位 | 登录凭据 env |
|------|------|------|--------------|
| `web/admin` | 3001 | 商户后台（多租户商用 SaaS 控制台） | `AUTH_USERNAME` / `AUTH_PASSWORD` |
| `web/tenant` | 3002 | 自用工作台 / 租户后台（派发任务给内核） | `TENANT_USERNAME` / `TENANT_PASSWORD` |

两应用**同构**：各自独立 Next.js 14 + TypeScript，含 `/api/aos/[...path]` 反向代理 + `/api/auth/{login,logout,session}` 网关鉴权。

## 架构与鉴权（对齐 AGENTS.md §5「权限即边界」）

```
浏览器 ──(session cookie)──> Node 网关(:3001/:3002)
                                 │ 校验 session（HMAC 自签，httpOnly）
                                 │ 通过 → 注入内部 AOS_API_KEY
                                 ▼
                           Python AOS 内核(:8000, FastAPI)
```

- **前端不持有任何系统密钥**：`AOS_API_KEY` 仅存于网关 env，转发后端时由网关注入 `X-API-Key` 头。
- **公开白名单**：`/api/aos/status` 免登录（人人可探活）；其余受保护路由无有效 session 即返回 `401`。
- **session 机制**：登录成功签发 HMAC-SHA256 签名令牌（cookie `aos_admin_session` / `aos_tenant_session`，httpOnly，8h 过期）。无需引入 `jsonwebtoken` 依赖，用 Node 内置 `crypto`。
- **诚实边界**：当前登录为 **demo 本地校验**（env 凭据）。生产应把 `app/api/auth/login/route.ts` 改为转发后端 `/api/auth/token` 或查 DB/OIDC，再签发网关 session。

## 本地启动（需先通电 Python 后端）

```bash
# 0) 启动 Python AOS 内核（在仓库根目录，默认监听 :8000）
#    start_all.sh  或  python -m src.api.main
#    确认 http://127.0.0.1:8000/api/status 返回 ok

# 1) 商户后台
cd web/admin
cp .env.example .env.local      # 改 AUTH_SECRET 为随机长串，按需改凭据
npm install
npm run dev                     # 打开 http://localhost:3001

# 2) 自用工作台（另开终端）
cd web/tenant
cp .env.example .env.local      # 改 AUTH_SECRET 为随机长串，按需改凭据
npm install
npm run dev                     # 打开 http://localhost:3002
```

> 注意：Next.js 默认读取 `.env.local`（已 gitignore）。`.env.example` 仅为模板，勿提交真实密钥。

## 验证矩阵

| 层 | 已验证 | 未验证 |
|----|--------|--------|
| ① 代码改动真 | ✅ `next build` 编译 + 类型校验通过 | — |
| ② 网关逻辑真跑 | ✅ 路由/登录/logout/session 编译通过；session 签名校验可单测 | 浏览器交互需手动 |
| ③ 端到端闭环 | — | ⚠️ 需主机 `start_all.sh` 拉起后端后，浏览器登录→转发→后端返回，方为真验 |

> 沙箱内无通电的 Python 后端，故 ③ 未验；上述 build 仅证明"代码能编译"，非"能跑通联调"。

## 关键文件

- `web/<app>/app/api/aos/[...path]/route.ts` —— 反向代理 + 鉴权门控
- `web/<app>/lib/session.ts` —— session 签发/校验（HMAC）
- `web/<app>/app/api/auth/{login,logout,session}/route.ts` —— 网关登录态
- `web/<app>/lib/aos-client.ts` —— 前端 typed client（只调同源 `/api/aos/*`）
