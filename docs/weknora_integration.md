# WeKnora 接入 AOS（MCP 即插即用）

> 状态：已落地代码集成（复用 AOS 现有 HTTP MCP 客户端，零新组件）。
> 运行时依赖用户主机先部署 WeKnora（Docker），沙箱无法跑 Docker，故未做真机端到端验证。

## WeKnora 是什么（已联网核实）

- 仓库：`github.com/Tencent/WeKnora`（腾讯官方开源，**MIT 许可证，可商用**）
- 本质：Go 写的独立知识框架，核心能力 = **RAG 快速问答 + ReAct Agent 智能推理 + 自动 Wiki**
- 覆盖 PDF / Word / 图片 / Excel / PPT 等十余种格式；兼容 20+ 大模型（智谱 / 混元 / DeepSeek / Qwen / Ollama 等）
- 多租户 RBAC、私有化部署、Langfuse 可观测
- **自带 MCP Server**（`mcp-server/` 目录，Python 实现），支持 `stdio` / `sse` / `http` 三种传输

AOS 走 **http（Streamable HTTP）** 模式接它的 MCP Server，直接复用 `MCPClientAdapter`，
不写任何新适配器——这正是 AOS「万物为我所用」的协议级落点。

## WeKnora MCP 暴露的核心工具（27 个，节选）

| MCP 工具 | 说明 | 映射到 AOS 能力 |
|----------|------|----------------|
| `hybrid_search` | 向量+关键词混合检索（跨知识库） | `data.query` |
| `chat` | RAG 问答（基于知识库） | `memory.knowledge` |
| `agent_chat` | ReAct Agent 多步推理 | `cognition.reasoning` |
| `wiki_search` / `wiki_read_page` / `wiki_index_view` | 自动 Wiki 检索/阅读 | `memory.knowledge` |
| `create_knowledge_from_file` / `create_knowledge_from_url` | 导入文档/网页 | `action.tool_use` |
| `create_knowledge_base` / `list_knowledge_bases` / `get_knowledge_base` | 知识库管理 | `action.tool_use` |
| `create_tenant` / `list_tenants` | 多租户 | `action.tool_use` |
| 其余（sessions / models / chunks 管理） | 运维类 | `action.tool_use` |

未显式映射的工具默认按 `action.tool_use`（通用工具）暴露，仍可被 `hub.invoke_engine("weknora", ...)` 精确调用。

## 用户主机部署步骤

### 1. 起 WeKnora 核心（REST :8080）

```bash
git clone https://github.com/Tencent/WeKnora.git
cd WeKnora
cp .env.example .env          # 按注释填 LLM / 向量库 / 对象存储等
docker compose up -d          # 核心服务起来后 REST API 在 http://localhost:8080/api/v1
```

在 WeKnora Web UI（http://localhost）创建账号，拿到 **API Key**（用于 `WEKNORA_API_KEY`）。

### 2. 起 WeKnora MCP Server（http 模式，:8081）

```bash
cd WeKnora/mcp-server
pip install -r requirements.txt        # 或 uv pip install -r requirements.txt
export WEKNORA_BASE_URL=http://localhost:8080/api/v1
export WEKNORA_API_KEY=<上一步拿到的 WeKnora API Key>
export MCP_SERVER_AUTH_TOKEN=<自定义一个共享密钥，如 weknora-mcp-secret>
python weknora_mcp_server.py --transport http --host 0.0.0.0 --port 8081
```

> MCP Server 进程需要通过 REST 调 WeKnora 核心，所以 `WEKNORA_API_KEY` / `WEKNORA_BASE_URL` 是给它用的；
> `MCP_SERVER_AUTH_TOKEN` 是 MCP 网络传输本身的鉴权，AOS 侧需填一样的。

### 3. 配置 AOS（`.env`）

```bash
WEKNORA_MCP_URL=http://localhost:8081/mcp
WEKNORA_MCP_AUTH_TOKEN=weknora-mcp-secret     # 须与步骤 2 的 MCP_SERVER_AUTH_TOKEN 一致
WEKNORA_MCP_ENGINE_ID=weknora                # 可选，默认 weknora
```

> 注：`WEKNORA_MCP_URL` 的 `/mcp` 路径是 `StreamableHTTPSessionManager` 的默认挂载点；
> 若你的 WeKnora 版本挂在不同路径，按实际改。

### 4. 启动 AOS

AOS 启动时 `FabricHub.__init__` 会读 `WEKNORA_MCP_URL` 并自动注册 `weknora` 引擎；
不可达时静默跳过，**绝不谎报 live**。

验证：

```python
from kernel.plugins.fabric_hub import FabricHub
hub = FabricHub()
print(hub.resolve_engine("data.query"))   # 期望输出 weknora（当 WeKnora 在线时）
r = hub.route("data.query", {"query": "年假申请流程", "kb_ids": ["..."]})
print(r.data["text"])
```

## 与 IMA 的关系（不冲突）

- **IMA** = 腾讯 IMA 个人/团队知识库（轻量、OpenAPI 直连），AOS 已接成「结构化交接后端」（HandoffEnvelope 存 IMA）。
- **WeKnora** = 企业级 RAG/知识引擎（重、可私有化、多租户、多格式解析强），AOS 经 MCP 把它变成「知识检索/问答/RAG 供给方」。

两者是**不同层**：IMA 偏「交接存档」，WeKnora 偏「海量文档 RAG 检索」。能力路由里 `memory.knowledge` 由二者按 health 与档位共同竞争，互不替代。

## meetily 说明（刻意不接）

AOS 源码里**没有真实接入的 meetily subagent**，只有 `agency_roles/` 下的「会议纪要专家 / 会议效率专家」等**角色 skill**（是角色不是 subagent）。
按铁律「禁止为外部愿景凭空造组件」，不伪造 meetily 组件接入——若未来 meetily 真有可对接的 MCP/API，再接。
