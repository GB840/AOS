# AOS 环境可复现指南（REPRODUCE）

> 对应整改项 **#95 环境可复现** 与 **#13 依赖锁定**。
> 目标：任意干净机器（同平台 Windows / Python 3.13）按本指南可重建出
> 与当前线上一致的 AOS 运行环境，并跑通测试套件。

---

## 0. 运行时拓扑（必读）

AOS 不是「一个 venv 装所有依赖」，而是采用**分层可复现**设计：

| 组件 | 解释 |
|---|---|
| 解释器 | 受管 Python `3.13.12`（由 supervisor 的 `AOS_VENV` 指定） |
| 依赖来源 | `default` venv 的 `site-packages`（经 `AOS_EXTRA_SITE` + `PYTHONPATH` 接入） |
| 配置 | 仓库根 `.env`（由 `.env.example` 复制而来，**不入库**） |
| 启动 | `python scripts/aos_supervisor.py`（单入口，含健康检查+自愈） |

`scripts/aos_supervisor.py` 的 `_aos_env()` 会**重建** `PYTHONPATH`，只保留：
`D:\AOS`、`D:\AOS\src`、`<default venv>/Lib/site-packages`，并把
`AOS_EXTRA_SITE` 指向 default venv。这是「可复现」的关键：依赖集中在
default venv，业务代码在仓库内，二者解耦。

---

## 1. 前置条件

- Python `>=3.10`（建议 3.13，与线上一致）
- Node.js `>=20`（OpenClaw 网关与前端需要）
- Git

---

## 2. 依赖安装（确定性）

仓库提供两份依赖清单，配合使用：

- `requirements.txt` —— **人工维护的精选清单**（直接依赖 + 关键版本引脚）。
- `requirements.lock` —— **`pip freeze` 确定性快照**（含全部传递依赖，
  由 default venv 生成，见 #13）。用于逐字节复现。

```bash
# 2.1 创建并激活运行时 venv（与线上一致的 default venv）
python -m venv <your_venv>
source <your_venv>/Scripts/activate      # Windows: <your_venv>\Scripts\activate

# 2.2 先装锁文件（确定性全量），再装项目自身（可编辑，便于改码）
pip install -r requirements.lock
pip install -e .

# 2.3 （可选）开发/测试依赖
pip install -e ".[dev]"
```

> 跨平台提示：`requirements.lock` 锁定的是 Windows wheel。若在 Linux/macOS
> 复现，请于目标平台重新 `pip freeze > requirements.lock`，或改用
> `requirements.txt` 由解析器重新求解。

---

## 3. 配置文件

```bash
cp .env.example .env
# 然后至少填写以下真实密钥（其余可留空走默认/本地引擎）：
#   API_KEY            个人级静态密钥（X-API-Key 鉴权）
#   UNIFIED_API_KEY   统一 LLM 网关密钥
#   ZHIPU_API_KEY / SILICONFLOW_API_KEY / ...  各 provider key
#
# ⚠️ .env 含敏感密钥，已被 .gitignore 排除，严禁提交。
```

`.env.example` 已与线上 `.env` 对齐（含 `APP_NAME`、`EMBEDDING_*`、
`VECTOR_ENABLED`、`OPENCLAW_GATEWAY_TOKEN`、`LITELLM_DEFAULT_MODEL` 等），
`cp` 后即是一份可运行模板。

---

## 4. 验证环境

```bash
# 依赖自检
make deps

# 首次初始化（建数据目录等）
make setup

# 完整启动自检（不常驻）
python scripts/verify_setup.py
```

---

## 5. 运行测试（#96 测试可收集）

测试套件位于 `tests/`，由 `pyproject.toml` 的 `testpaths=["tests"]` 自动收集，
`conftest.py` 已注入 `src` 到 `sys.path` 并设置 `APP_ENV=testing`。

```bash
# 收集并运行全部单元/集成测试（不含 integration/e2e 标记）
make test
# 等价于：
python -m pytest tests/ -m "not integration and not e2e"

# 仅安全中间件单测（#107–#115 整改覆盖）
python -m pytest tests/test_security.py -v

# 数据库单一真相层 smoke（不依赖完整 AOS 依赖）
make smoke
```

> 若用隔离 venv 运行测试，请确保该 venv 同时具备 `requirements.lock` 中的
> 运行时依赖（`ag2` / `mcp` / `fastapi` 等），否则需在 `PYTHONPATH` 中
> 追加 default venv 的 `site-packages`（与 supervisor 一致）。

---

## 6. 启动平台

```bash
# 单入口拉起全部组件（aos / web / openclaw / deerflow），含自愈
python scripts/aos_supervisor.py

# 仅启动 AOS API
python scripts/aos_supervisor.py --only aos

# 健康检查
python scripts/aos_supervisor.py --check
```

启动后访问：
- API：`http://localhost:8000/health`（公开探针）
- 文档：`http://localhost:8000/docs`（仅 development 放开，production 需鉴权）
- 控制台：`http://localhost:8501/web`

---

## 7. 复现检查清单（CI 视角）

CI（`.github/workflows/ci.yml`）执行：`make check`（ruff + AST 重复定义）、
`make smoke`（DB 层）、`make test`（收集 `tests/`）。本地逐条跑通即等价于
CI 绿色。

| 项 | 命令 | 预期 |
|---|---|---|
| 静态检查 | `make check` | 无 error |
| DB smoke | `make smoke` | 42 表就绪、种子 agent 存在 |
| 测试收集 | `make test` | 全部 `tests/*` 被收集 |
| 安全单测 | `pytest tests/test_security.py` | 全绿 |
| 启动 | `python scripts/aos_supervisor.py --check` | 各服务 HEALTHY |

---

## 8. 已知限制

- `tests/test_memory.py` 在**线上服务占用 `data/sqlite/aos.db`** 时可能因文件锁
  报 `PermissionError`；属环境冲突，非代码缺陷。CI/干净环境不受影响。
- `tests/test_skills.py` 中若干断言依赖运行时已加载的技能清单数量，环境差异下
  可能计数不符；属测试用例与运行态耦合，已记录待 #99/#102 卫生清理时修正。
- 以上两项不影响「测试可收集」(#96) 结论——套件可正常导入、收集、执行。
