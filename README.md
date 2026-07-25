# 单创OS（AOS · Agent OS）

> **一套代码，双模式运行**：自用创业执行 + 多租户商用 SaaS。
> 对外品牌「单创OS」，代码仓库名 `AOS`。本质：**Verifiable Self-Evolving Agent OS（诚实可验证的自进化 agent 操作系统）**，不是聊天工具。

---

## 它是什么（诚实版）

- **内核（Python）**：一套零重型依赖的可自进化 agent 内核——物种动力学（自愈/DNA变异/适应度选择/资源经济）、双轨可信记忆（Hippo-Scroll）、电路熔断与自修复。详见 `src/kernel/`。
- **Fabric 适配器层**：统一路由/记忆/上下文主权的芯粒架构。两套栈并存：
  - `src/kernel/plugins/fabric_hub.py` —— 内核层 FabricHub，`_ADAPTERS` 注册 **27** 个引擎（含 orchestrator）。
  - `src/core/fabric/adapters/` —— 新栈，**36** 个适配器文件 / **34** 个适配器类（含 img2threejs、mediakit、content_marketer 等）。
- **OPC 五岗位数字组织**：产品研发 / 市场调研 / 内容营销 / 客户服务 / 财务核算。
- **调度引擎**：autopilot + opc_loop，目标驱动长程自主反思（§2.5）。
- **双模式前端（Next.js + TypeScript 网关）**：
  - `web/admin` —— 商户后台（:3001）
  - `web/tenant` —— 自用工作台 / 租户后台（:3002）
  - 前端**绝不直连大模型**：所有 `/api/aos/*` 经 Node 网关反向代理到 Python AOS 内核（FastAPI :8000），契约见 `src/api/main.py`。

> ⚠️ **诚实边界（务必读）**：本项目按「可验证即真理」纪律运作。
> - 适配器/测试数量由 `tools/baseline_snapshot.py` **真跑测算**写入 `AGENTS.md §0.5`，非手抄。
> - 自进化闭环 **mock 端到端已验证 PASS**（机制+教训注入可用），但 **真 LLM 端到端（--real 模式）尚未在沙箱验证**，需主机 `--real` 跑（见 `scripts/self_evo_loop_verify.py`）。
> - 全量 `pytest` 在沙箱未单轮跑绿（受超时限制），需主机首跑；覆盖率门槛 50% 待 HEAVY 模式实测。
> - 部分引擎（openclaw/ag2/litellm/mem0/lfm2 等）在无 API key 环境为 dead 态，已在 `STATUS.md §7` 诚实登记。
> 详见 `STATUS.md`（项目真值表）与 `AGENTS.md`（项目宪法）。

---

## 四层架构

```
① 多租户隔离底座      （ZERO / 当前基座）
② OPC 5 岗位数字组织   （产品研发/市场调研/内容营销/客户服务/财务核算）
③ 创业目标调度引擎     （autopilot + opc_loop，长程自主反思）
④ 双模式前端          （web/admin 商户后台 + web/tenant 自用工作台）
```

## 快速开始

### 1. 后端（Python AOS 内核，FastAPI :8000）
```bash
# 需要 Python 3.14，依赖装在系统 Python
pip install -r requirements.txt        # 或 pyproject 装配
python start_all.sh                   # 拉起 API + 相关服务（详见仓库脚本）
# 健康检查
curl http://127.0.0.1:8000/api/status
# 团队登录换 JWT（网关登录即转发到此）
curl -X POST http://127.0.0.1:8000/api/auth/token -H 'content-type: application/json' -d '{"username":"<你>","password":"<你>"}'
```

### 2. 前端（Node 网关层）
```bash
cd web/admin  && cp .env.example .env && npm install && npm run dev   # :3001 商户后台
cd web/tenant && cp .env.example .env && npm install && npm run dev   # :3002 自用工作台
```
浏览器打开对应端口，先 `POST /api/auth/login`（网关转发后端 `/api/auth/token` 换 JWT），登录后状态条变绿即代表网关↔内核连通。

### 3. 鉴权模型（对齐 `AGENTS.md §5`「权限即边界」）
- 网关**不存用户密码**，登录凭据直交后端 `/api/auth/token` 换取 JWT；
- 网关 session 仅持有后端签发的 JWT（HMAC 自签防篡改，httpOnly cookie）；
- 代理转发时由网关注入 `Authorization: Bearer <jwt>`，**前端从不接触系统密钥**；
- `/api/aos/status` 为公开探活白名单，免登录。

---

## 文档导航
| 文件 | 作用 |
|------|------|
| `AGENTS.md` | 项目宪法（九大核心理念 + 七级决策阶梯 + §0.5 基线真值表） |
| `STATUS.md` | 项目真值表（规模/能力/live-dead/诚实校准），任何改动前先读 |
| `docs/SHANCHUANG_OS_PRODUCT_VISION.md` | 单创OS 产品愿景（双模式 SaaS 战略） |
| `docs/research/` | 外部项目借鉴核实文档（waoowaoo / OpenWorker / img2threejs / ts_node 映射等） |
| `web/README.md` | 前端网关层启动与鉴权细节 |

## License
MIT（内核）。外部 vendored 项目（如 `ViMax/`）以其自带 LICENSE 为准，已登记于 `references/ecosystem/INTEGRATIONS.md §6`。
