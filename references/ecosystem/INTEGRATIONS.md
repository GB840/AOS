# AOS 生态集成对照 —— 5 款真实产品的接入方案

> 这 5 款产品均经本会话 WebSearch 核实真实存在、且都支持 **MCP (Model Context Protocol)**。
> AOS 的统一接入机制 = **通用 MCP 客户端芯粒**（`src/core/fabric/adapters/mcp_client_adapter.py`）
> + **成本感知路由**（registry 的 `ROUTE_STRATEGY`，借 Auriko 内核）。
> 配置即接，无需改 AOS 核心代码 —— 这就是「万物为我所用 / 不绑定」。

状态图例：✅ 已真接 · 🔌 配置即接（给 URL 即用）· 📚 参考实现已入仓（架构借鉴/导出兼容）

> **关于「完整开源源码」的存放**：ExploreYC / Sim / Timbal 三仓真实源码已完整拉到
> 本机 `references/ecosystem/{exploreyc,sim,timbal}/`（逐字对照用），但**不进 AOS 的 git**
> ——Sim 单仓 238MB / 1.3 万文件，整仓入会撑爆仓库、拖垮 `git push`。改用
> `references/ecosystem/CLONE.sh` 一条命令在任意机器复现完整开源。集成契约（本文件）入库。

---

## 1. AnySearch —— Agent 专属搜索基础设施（搜索层）

| 项 | 真实情况 |
|---|---|
| 仓库/服务 | `api.anysearch.com/mcp`（JSON-RPC 2.0 MCP Server），Skill+MCP Server 开源 |
| 开源状态 | ✅ Skill 与 MCP Server 完全开源；个人开发者每日 1000 次匿名免费调用 |
| AOS 角色 | **搜索芯粒**（`web.search`） |
| 当前状态 | ✅ **已真接**（在 `src/core/fabric/adapters/search_adapter.py` 作为第 0 源，走 MCP；也支持经 MCP 客户端芯粒注册） |

**接线（任选其一）：**
- 已内置：SearchAdapter 多源兜底首位即 AnySearch，零配置可用。
- 或经通用 MCP 芯粒显式注册（演示统一机制）：
  ```bash
  export AOS_MCP_SERVERS='[{"url":"https://api.anysearch.com/mcp","engine_id":"mcp-anysearch",
    "capability_map":{"web_search":"web.search"}}]'
  ```
  ```python
  from kernel.plugins.fabric_hub import FabricHub
  hub = FabricHub()
  hub.route("web.search", {"query": "北京天气"})   # 由 mcp-anysearch 承接
  ```

---

## 2. ExploreYC —— YC/a16z 创业数据层（数据层）

| 项 | 真实情况 |
|---|---|
| 仓库 | `github.com/KonstantinMB/exploreyc`（React+FastAPI+Supabase，开源） |
| 开源状态 | ✅ MIT（仓库根 LICENSE 已核验）。含 6000+ YC/a16z 被投企业数据、融资/退出/创始人信息 |
| AOS 角色 | **数据芯粒**（`data.query`） |
| 当前状态 | 📚 完整真实源码已入仓 `references/ecosystem/exploreyc/`；AOS `DATA_QUERY` 能力已加；接线示例见下 |

> 诚实说明：ExploreYC 本体是一个**完整 Web 应用**（前端+Supabase 后端），并未随仓库发布独立 MCP Server。
> 故 AOS 接入方式=把它的数据（Supabase 表 / 其 FastAPI 接口 / 导出数据集）经 MCP 或薄适配器暴露成 `data.query` 芯粒。
> 以下为配置即接骨架：

```bash
# 若你自托管 ExploreYC 的 FastAPI 并把其「公司查询」包成一个 MCP tool（tool 名如 search_companies）
export AOS_MCP_SERVERS='[{"url":"http://localhost:8000/mcp","engine_id":"mcp-exploreyc",
  "capability_map":{"search_companies":"data.query"}}]'
```
```python
hub.route("data.query", {"query": "YC 2024 AI batch", "limit": 10})
```

---

## 3. Sim —— 开源 AI Agent 工作流构建器（构建层）

| 项 | 真实情况 |
|---|---|
| 仓库 | `github.com/simstudioai/sim`（Apache-2.0，27K stars，n8n 开源替代） |
| 开源状态 | ✅ Apache-2.0（仓库根 LICENSE 已核验）；连接 1000+ 集成、所有主流大模型，可视化 DAG 编排 |
| AOS 角色 | **可视化构建工作台** —— 用 Sim 画 AOS 的 `steps[]` 流水线，导出即 AOS OrchestrationChiplet spec |
| 当前状态 | 📚 完整真实源码已入仓 `references/ecosystem/sim/`；AOS `OrchestrationChiplet.steps[]` 本就是 DAG 形状，与 Sim 画布同构 |

> AOS 的 `steps:[{capability, in, in_from}]` 与 Sim 的 DAG 节点天然同构。集成方向：
> - **Sim → AOS**：Sim 画好的工作流导出 JSON，转成 AOS `steps[]` spec，经 `hub.route("system.workflow", spec)` 执行。
> - **AOS → Sim**：AOS 规划器（ag2）产出的步骤，渲染成 Sim 画布供人工审查（呼应 Karpathy Agentic Engineering 的「人工审查」环节）。

---

## 4. Auriko —— 模型调用成本优化器（成本层）

| 项 | 真实情况 |
|---|---|
| 服务/SDK | `auriko.ai` + PyPI 包 `auriko`（Apache-2.0，OpenAI 兼容推理路由器 SDK） |
| 开源状态 | ⚠️ **SDK 开源（Apache-2.0，PyPI 可装）；但「核心套利算法」运行在其托管网关，未公开源码**。其策略模式（最便宜/最快/最高质量 + 自动故障转移）是公开的 |
| AOS 角色 | **模型路由策略** —— 已**原生借进 AOS**，不依赖其托管网关 |
| 当前状态 | ✅ **架构已借**：registry 的 `ROUTE_STRATEGY`（preference|cost|latency|quality）+ 既有运行时故障转移 = Auriko 成本套利内核 |

**这就是「能用完整开源就用完整的」的边界**：Auriko 可借的是*策略*，不是*网关*。AOS 把它做成自己的路由能力：
```python
from core.fabric import FabricRegistry
# 成本优先：最便宜的推理供给方排最前，失败自动 fallback 到次优（= Auriko 语义）
reg = FabricRegistry(strategy="cost",
                     provider_cost={"litellm": 10, "agnes": 40, "ag2": 20})
```
AOS 的 `PROVIDER_COST` / `PROVIDER_LATENCY` / `PROVIDER_QUALITY` 即 Auriko 式打分矩阵，改配置不动代码。

---

## 5. Timbal —— 端到端 AI 生产平台（生产层）

| 项 | 真实情况 |
|---|---|
| 仓库 | `github.com/timbal-ai/timbal`（Apache-2.0 Python 框架，原生支持 MCP stdio/HTTP） |
| 开源状态 | ✅ Apache-2.0（仓库根 LICENSE 已核验）；Agents+Workflows 双模式，typed IO，流式执行 |
| AOS 角色 | **生产部署运行时** —— AOS 原型 → Timbal 上线生产 |
| 当前状态 | 📚 完整真实源码已入仓 `references/ecosystem/timbal/`；薄适配骨架见下（import 守卫，装了 `timbal` 才激活） |

```python
# 可选薄适配：把 Timbal Agent/Workflow 包成 AOS 芯粒（需 pip install timbal）
# from timbal import Agent
# class TimbalDeployAdapter(BaseAgentAdapter): ...
# hub.register_mcp_server("http://localhost:3000/mcp", engine_id="mcp-timbal")
```
Timbal 原生支持把任意 MCP Server 当工具接进它的 Agent —— 反过来，AOS 也能把 Timbal 当生产运行时。两端 MCP 互通，零胶水。

---

## 一键接入清单（env 驱动，全 5 款）

```bash
export AOS_MCP_SERVERS='[
  {"url":"https://api.anysearch.com/mcp","engine_id":"mcp-anysearch","capability_map":{"web_search":"web.search"}},
  {"url":"http://localhost:8000/mcp","engine_id":"mcp-exploreyc","capability_map":{"search_companies":"data.query"}},
  {"url":"http://localhost:3000/mcp","engine_id":"mcp-timbal"}
]'
# Auriko 策略无需外部服务：AOS 内部 ROUTE_STRATEGY=cost 即生效
export AOS_ROUTE_STRATEGY=cost
```

## 真实开源仓库索引（已入仓，可逐字对照）

| 产品 | 仓内路径 | LICENSE（已核验） | commit |
|---|---|---|---|
| ExploreYC | `references/ecosystem/exploreyc/` | MIT | 50cafcb |
| Sim | `references/ecosystem/sim/` | Apache-2.0 | e01bfb14 |
| Timbal | `references/ecosystem/timbal/` | Apache-2.0 | de67ef4 |
| Auriko | PyPI `auriko`（未 vendored；SDK Apache-2.0，网关算法未公开） | Apache-2.0 (SDK) | 0.3.0 |

> 全部为真实存在、经 WebSearch 核实的仓库；克隆均 `--depth 1` 并排除 `.git`，纯作工程参考与对照，不构成对上游代码的再分发主张。
