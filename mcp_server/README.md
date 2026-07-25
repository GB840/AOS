# AOS 共享记忆 MCP 服务器（多 Agent 共享外脑）

本地优先、零外部依赖（仅标准库 + 官方 `mcp` SDK）的 MCP 服务器。
把"记忆"集中存进一个 SQLite 文件，任何接入本服务器的 MCP 客户端
（WorkBuddy / Claude Code / CherryStudio / 其它智能体）都能读 / 写同一份记忆
—— 这就是"多 Agent 共享外脑"。

## 能力（MCP tools）
- `store_memory(namespace, key, value, tags)` 存 / 更新一条记忆
- `get_memory(namespace, key)` 按命名空间 + 键取回
- `search_memory(query, namespace?, top_k?)` 全文检索（FTS5 trigram，中文友好；不支持时降级 LIKE）
- `list_namespaces()` 列出所有命名空间
- `list_keys(namespace)` 列出某命名空间下所有键
- `delete_memory(namespace, key)` 删除一条记忆

## 运行
- 传输：stdio（MCP 客户端以子进程方式拉起）
- 依赖：`pip install mcp`（已登记进 `~/.workbuddy/mcp.json`，命令指向已装好 mcp 的 Python）
- 存储：默认 `~/.aos/shared_memory.db`，可用环境变量 `AOS_SHARED_MEMORY_DB` 覆盖

## 真验（stdio 跨进程调用）
```powershell
pip install mcp
python -c "import mcp; print('ok')"
# WorkBuddy 已在 ~/.workbuddy/mcp.json 登记 aos-shared-memory，重启 WorkBuddy 即可在工具里看到上述 6 个工具
```

## 设计取舍（诚实说明）
- 这是"共享记忆 / 外脑"，不是"多 Agent 自治编排"；它提供可信、可检索、跨 Agent 的长期记忆层。
- 本地模式只做 SQLite + FTS 检索，不上云、不依赖任何密钥。
- 若日后要语义向量检索，可在存储层加 embedding，不影响 MCP 接口契约。
