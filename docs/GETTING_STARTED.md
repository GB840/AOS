# AOS 快速入门

> 5 分钟内从零到跑通第一个自主任务。

---

## 1. 前置条件

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.14+ | 系统 Python，路径 `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe` |
| pip | 最新 | 随 Python 附带 |
| Git | 最新 | 用于克隆仓库 |

**可选依赖**（增强能力，缺省不影响核心链路）：

- **Ollama**：本地 LLM/Embedding（`ollama serve` + `ollama pull qwen2.5:7b nomic-embed-text`）
- **Node.js v20+**：部分 MCP 芯粒（Desktop-Touch、video-use）需要
- **ffmpeg**：视频处理芯粒需要

---

## 2. 安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/AOS.git
cd AOS

# 2. 安装为可编辑模式（editable install）
pip install -e .
```

> **注意**：项目依赖在 `pyproject.toml` 中管理。如果某些可选依赖安装失败，不影响核心功能。
> 内核设计原则：缺失依赖的适配器会被优雅跳过，枢纽照常构建。

---

## 3. 最小启动示例

### 3.1 Python 代码方式

```python
from kernel.system import build_default_system

# 构建完整 AOS 系统实例（内核 + 四层架构 + 全部插件）
system = build_default_system()

# 打印通电自检：哪些引擎 live、哪些 dead、各引擎声明的能力
report = system.health_report()
print(f"总引擎: {report['total']}, 在线: {report['live']}")
for eid, info in report['adapters'].items():
    status = 'live' if info['live'] else 'dead'
    caps = ', '.join(info.get('capabilities', [])[:3])
    print(f"  {eid}: {status} [{caps}]")
```

### 3.2 Autopilot 自主闭环

Autopilot 是 AOS 的核心自主执行引擎，支持「规划 -> 执行 -> 反思 -> 续跑」完整闭环：

```bash
# 基础用法：一句话目标，系统自主完成
python -m kernel.autopilot "搜索最新的AI agent框架"

# 启用反思闭环（失败自动重设计，最多 3 轮）
python -m kernel.autopilot --reflect "对比 SQLite 与 PostgreSQL 的性能差异"
```

### 3.3 CLI 统一入口

```bash
# 一句话任务，自动走意图解读 -> 方案生成 -> 执行 -> 汇报
python -m kernel.aos "研究SQLite与PostgreSQL的区别，写对比要点到 _output/db_compare.md"

# 不交互，直接选推荐方案执行
python -m kernel.aos --auto "安装最新的 Node.js LTS 版本"

# 指定方案索引（从 LLM 生成的多套方案中选第 1 套）
python -m kernel.aos --plan 1 "搭建一个简单的 HTTP 服务"
```

### 3.4 API 服务

```bash
# 启动 FastAPI 服务（默认 0.0.0.0:8000）
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 后台运行
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

API 文档访问：`http://localhost:8000/docs`

### 3.5 Web 界面

```bash
# 启动 Streamlit 可视化界面
streamlit run src/web/app.py
```

---

## 4. 环境变量配置（.env）

在项目根目录创建 `.env` 文件（已 gitignore，不会提交）：

```env
# === 必选（按需配置） ===

# 智谱 API Key（闭源 LLM 兜底，默认可不配，走本地开源模型）
ZHIPU_API_KEY=your-zhipu-key-here

# === 记忆系统 ===

# 本地记忆模式（默认开启，零成本）
# AOS_MEM0_LOCAL=1       # 使用本地 ollama + chroma，无需付费 API
# AOS_MEM0_LOCAL=0       # 使用远程 mem0 服务（需 MEM0_API_KEY）

# === 推理策略 ===

# AOS_LOCAL_FIRST=1       # 对话时优先走本地 Ollama（数据不出本机）
# AOS_ZHIPU_OPTIN=1       # 显式启用智谱闭源兜底

# === 路由与蒸馏 ===

# AOS_ROUTE_STRATEGY=learned    # 路由预测策略（learned=基于历史数据训练）
# AOS_DISTILLER_ROUTE=1         # 启用白盒蒸馏路由（不可靠引擎自动降权）

# === 隔离与安全 ===

# AOS_MEM0_EMBEDDER=huggingface  # 使用 sentence-transformers 本地 Embedding
```

> **零成本启动**：不配任何 API Key，系统仍可运行。搜索走 AnySearch（免 key），
> 本地推理走 Ollama，记忆走本地 Chroma。配置 API Key 只是增强云端能力。

---

## 5. 验证安装

```bash
# 快速检查：内核能否正常构建
python -c "
from kernel.wiring import build_default_kernel
kernel = build_default_kernel(inject_brain=False)
report = kernel.fabric_health()
if report:
    print(f'内核构建成功: {report[\"live\"]}/{report[\"total\"]} 引擎在线')
else:
    print('内核构建成功（fabric 未登记）')
"

# 查看完整适配器列表
python -c "
from kernel.plugins.fabric_hub import get_fabric_hub
hub = get_fabric_hub()
report = hub.health_report()
print(f'适配器总数: {report[\"total\"]}, 在线: {report[\"live\"]}')
for eid, info in sorted(report['adapters'].items()):
    status = 'LIVE' if info['live'] else 'dead'
    print(f'  [{status:>4}] {eid}')
"
```

---

## 6. 常见问题

### Q1: 安装时某个依赖报错怎么办？

AOS 内核设计了优雅降级：`core/fabric/adapters/__init__.py` 对每个适配器用 `try/except` 包裹，
缺依赖的适配器自动跳过（置为 None），不阻断枢纽构建。你仍然可以使用其余在线的引擎。

### Q2: 不配任何 API Key 能跑吗？

能。系统支持零配置本地运行：
- **搜索**：AnySearch（免 key）+ 百度/Bing HTML 多源兜底
- **推理**：Ollama 本地（`ollama serve` + `ollama pull qwen2.5:7b`）
- **记忆**：本地 Chroma + sentence-transformers（`AOS_MEM0_LOCAL=1`）

### Q3: 启动时报 `'NoneType' object has no attribute '__name__'` 是什么问题？

这是 brain 层 fabric 链路的已知问题（brain.py 重型初始化失败）。不影响 kernel 层 FabricHub 的正常工作。
如需 brain 集成，确认 `ZHIPU_API_KEY` 已配置且网络可达。不需要 brain 时可传 `inject_brain=False` 跳过。

### Q4: 如何查看哪些引擎是 live 的？

```bash
python -c "
from kernel.plugins.fabric_hub import get_fabric_hub
hub = get_fabric_hub()
r = hub.health_report()
print(f'{r[\"live\"]}/{r[\"total\"]} live')
"
```

或通过 API：`GET http://localhost:8000/api/health`（需先启动 API 服务）。

### Q5: autopilot 反思闭环是什么？

反思闭环（reflex）是 AOS 自主执行的核心机制：每步执行后有「成没成」的硬判定，
失败时自动触发「质疑 agent」诊断根因，产出修正后的计划再执行，最多 3 轮。
详见 `AGENTS.md` 2.5 节「目标驱动 - 长程自主 - 反思闭环」。
