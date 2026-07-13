# codebase-memory-mcp（AOS 内置的「代码理解」工具）

> 把真实开源工具 **弄进 AOS**，让任何人 clone 本项目后都能用它直接审视整个代码库。
> 这不是 AOS 自研的玩具索引器，而是 [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) 原版二进制——AOS 只负责「接」（stdio MCP 适配器），不重写它的脑子。

## 它是什么

- **作者 / 协议**：DeusData，[MIT](https://github.com/DeusData/codebase-memory-mcp/blob/main/LICENSE)
- **实现**：纯 C、零依赖，内置 **158 种语言**的 tree-sitter 语法解析器
- **形态**：**MCP stdio server**——通过 stdin/stdout 走 JSON-RPC 2.0，日志走 stderr
- **能力**：把代码库解析成知识图谱（定义 / 调用 / 导入 / HTTP 链接 / 配置 / 测试），支持结构化搜索、调用链追踪、变更爆炸半径、架构概览、ADR 等
- **速度**：普通仓库毫秒级；Linux 内核（2800 万行）全量约 3 分钟；查询亚毫秒
- **隐私**：100% 本地处理，不联网、不上传代码

## 它暴露的工具（MCP + CLI）

二进制共提供 14 个工具，但**经 MCP stdio server 只暴露 8 个**（其余 6 个仅作为 `cli` 子命令可用）：

- **MCP stdio 暴露的 8 个**：`index_repository` `search_graph` `trace_path` `query_graph` `get_graph_schema` `get_code_snippet` `get_architecture` `search_code`
- **仅 CLI 可用的 6 个**（不进 MCP server）：`list_projects` `delete_project` `index_status` `detect_changes` `manage_adr` `ingest_traces`

## AOS 如何用它（已集成，无需改代码）

- AOS 新增 `code.understanding` 能力（`src/core/fabric/capability.py`）
- stdio MCP 客户端 `src/core/fabric/adapters/mcp_stdio_adapter.py` 起子进程、做 initialize 握手、列工具、调工具
- 适配工厂 `src/core/fabric/adapters/codebase_memory_mcp_adapter.py` 把 8 个 MCP 工具统一映射到 `code.understanding`
- `FabricHub` 在构建时自动探测并注册（`register_codebase_mcp` + `_register_env_codebase_mcp`）：
  - 读了 `AOS_CODEBASE_MCP_BIN` 就用它；
  - 否则探测 `third_party/codebase-memory-mcp/bin/codebase-memory-mcp.exe`；
  - **二进制不存在则静默跳过，绝不谎报 live**
- 调用示例（经能力路由）：

  ```python
  from core.fabric.plugins.fabric_hub import build_default_kernel
  from core.fabric.capability import Capability
  hub = build_default_kernel()
  # 索引整个 AOS 仓库
  hub.route(Capability.CODE_UNDERSTANDING,
            {"tool": "index_repository", "arguments": {"repo_path": "D:/AOS"}})
  # 查架构概览
  r = hub.route(Capability.CODE_UNDERSTANDING,
                {"tool": "get_architecture", "arguments": {"project": "AOS"}})
  print(r.data["text"])
  ```

## 别人怎么用这个工具审视 AOS

1. **装二进制**（只需一次，二选一）：
   - 一键：`powershell -ExecutionPolicy Bypass -File third_party/codebase-memory-mcp/install.ps1`
     （自动下载最新 Windows 发布物到 `bin/`；网络不通时按脚本提示手动放置）
   - 或任意官方渠道：`scoop install codebase-memory-mcp` / `winget install` / `npm i -g` / 从 [Releases](https://github.com/DeusData/codebase-memory-mcp/releases/latest) 下载，再设 `AOS_CODEBASE_MCP_BIN=路径`
2. **索引 AOS**（生成图，只需一次，可提交共享）：
   - `powershell -ExecutionPolicy Bypass -File scripts/index_aos_codebase.ps1`
   - 产物落在 `.codebase-memory/graph.db.zst`，**可 `git add` 提交**，别人 clone 后直接加载、免全量重索引
3. **直接查询**（无需 AOS 运行时，纯 CLI）：
   ```bash
   codebase-memory-mcp cli index_repository '{"repo_path":"D:/AOS"}'
   codebase-memory-mcp cli get_architecture '{"project":"AOS"}'
   codebase-memory-mcp cli search_graph '{"name_pattern":".*Adapter.*"}'
   ```
4. **经 AOS 运行时查询**：见上「AOS 如何用它」。

## 为什么是 vendored reference 而非 git submodule

完整 C 源码含 158 个 tree-sitter 子解析器（多为 submodule/大体积），整仓入 AOS 会撑爆仓库、拖垮 push（参考 `references/ecosystem/` 已 gitignore 的教训）。故本目录只放**文档 + 安装脚本 + 忽略规则**，二进制按需拉取（不入库），与本项目「磁盘完整 + 一键复现」的既定策略一致。真要锁版本，可在 `install.ps1` 指定 release tag。

## 历史注记（诚实）

AOS 早期有两个**自研的、冒用 codebase-memory-mcp 之名**的 skill（`src/skills/codebase_memory.py` 与 `src/skills/codebase_memory_mcp.py`），实际只是正则粗糙索引，并未调用本真实工具。现已将 `codebase_memory_mcp.py` 改造为真实后端的薄代理（可用时走真工具，不可用时诚实报错，不再偷偷造假），`codebase_memory.py` 也已纠正其冒充 DeusData 的声明。真正的集成在这里——以 stdio MCP 接原版二进制。
