## 在另一台机器上运行 AOS v5.0

本文档面向全新环境，目标：从 `git clone` 到 AOS 跑起来，中间不踩坑。

---

### 前置条件

- Python 3.11+（推荐 3.11.x，`python --version` 确认）
- pip / venv 可用
- Git
- （可选）Docker —— 如果走容器路线

---

### 1. 克隆仓库

```bash
git clone <your-repo-url> aos
cd aos
```

如果代码在 U 盘或本地目录，直接 `cd` 进去即可。

---

### 2. 创建虚拟环境

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

---

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

如果遇到编译错误（常见于 `psycopg2`、`bcrypt`、`grpcio`）：

- **Windows**: 确保安装了 [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- **macOS**: `xcode-select --install`
- **Linux**: `sudo apt install python3-dev build-essential`

如果 `psycopg2-binary` 编译失败，可临时替换为 `psycopg2-binary` (已在 requirements.txt 中)。

---

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，**至少填写以下字段**：

| 变量 | 说明 | 示例 |
|------|------|------|
| `UNIFIED_API_KEY` | 主 LLM 网关 API Key | 从 DeepRoute / OpenAI 等平台获取 |
| `UNIFIED_BASE_URL` | 主 LLM 网关地址 | `https://api.deeproute.com/v1` |
| `API_KEY` | AOS 自身 API 认证密钥 | 任意强随机字符串 |

其他 provider（智谱 / SiliconFlow / 百度 / 讯飞）按需填写。不填的 provider 会被自动跳过。

---

### 5. 初始化数据目录

```bash
make setup
# 或手动：
mkdir -p data/sqlite data/chroma outputs logs
```

---

### 6. 启动

**方式 A — 直接启动 API 服务**

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

验证：

```bash
curl http://localhost:8000/health
# 应返回 {"status": "healthy", ...}
```

**方式 B — Streamlit Web UI**

```bash
streamlit run src/web/app.py --server.port 8501
```

**方式 C — Docker 开发模式**

```bash
docker build -f Dockerfile.dev -t aos-dev .
docker run --rm -it -p 8000:8000 -p 8501:8501 --env-file .env -v .:/app aos-dev
```

**方式 D — 内核独立演示（aos_server.py）**

```bash
python aos_server.py
# 轻量模式：不依赖 brain.py，直接走 kernel
# 访问 http://localhost:8080
```

---

### 7. 验证

```bash
# 健康检查
curl http://localhost:8000/health

# 跑测试
make test

# 查看覆盖率
make coverage
```

---

### 常见问题

**Q: `ModuleNotFoundError: No module named 'xxx'`**
确认虚拟环境已激活（`which python` 应指向 `.venv`），然后 `pip install -r requirements.txt`。

**Q: `ImportError: cannot import name 'MCPMessage' from 'mcp'`**
确保 `mcp==1.28.0`：`pip install mcp==1.28.0`。

**Q: SQLite 报 `database is locked`**
关闭其他占用 `data/sqlite/aos.db` 的进程，或删除该文件重建。

**Q: 端口被占用**
改 `.env` 中的 `PORT`，或启动时指定 `--port 8001`。

**Q: Windows 上 `make` 命令不可用**
直接用等效命令：
```powershell
# make test
python -m pytest tests/ -v --tb=short

# make coverage
python -m pytest tests/ --cov=src --cov-report=term-missing --tb=short -q

# make lint
python -m ruff check src/ tests/
```

---

### 架构概览

详见 [docs/ARCHITECTURE.md](ARCHITECTURE.md)。

三轨并存：
- **supervisor** (`scripts/aos_supervisor.py`) — 轻量编排，调试用
- **v5 app** (`src/core/brain.py` + `src/api/main.py`) — 当前生产路径
- **v1 kernel** (`src/kernel/`) — 下一代内核，通过 `/api/v1/chat` 和渐进切流接入

渐进切流：设置 `AOS_KERNEL_TRAFFIC_PCT=10` 将 10% 的 `/api/chat` 流量路由到 kernel。
