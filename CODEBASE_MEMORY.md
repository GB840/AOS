# 用 codebase-memory-mcp 审视 AOS

AOS 把真实开源工具 [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
（DeusData，纯 C / 零依赖 / MIT，158 种语言 tree-sitter）**内置进仓库**，让你 clone 后
直接用它理解整个代码库。它不是 AOS 自研的玩具索引器，而是原版二进制，由 AOS 新栈以
stdio MCP 接入（`code.understanding` 能力）。

## 最快：一键脚本（推荐）

```powershell
# 在仓库根目录 D:\AOS 下，一条命令完成"下载二进制 + 索引整个仓库"
powershell -ExecutionPolicy Bypass -File setup_codebase_memory.ps1
```

跑完 AOS 即自动通电 `code.understanding` 能力，并生成可提交的
`.codebase-memory/graph.db.zst`。脚本内部就是下面第 1、2 步的组合；若你想分步或手动
安装，见下文。

## 三步上手

```powershell
# 1) 装二进制（装到 third_party/codebase-memory-mcp/bin/）
powershell -ExecutionPolicy Bypass -File third_party/codebase-memory-mcp/install.ps1
#   网络不通时按脚本提示手动放置，或 scoop/winget/npm 安装后设 AOS_CODEBASE_MCP_BIN

# 2) 索引整个 AOS（产物 .codebase-memory/graph.db.zst 可提交，别人免重索引）
powershell -ExecutionPolicy Bypass -File scripts/index_aos_codebase.ps1

# 3) 直接查（无需 AOS 运行时）
codebase-memory-mcp cli get_architecture '{"project":"AOS"}'
codebase-memory-mcp cli search_graph '{"name_pattern":".*Adapter.*"}'
codebase-memory-mcp cli trace_path '{"symbol":"FabricHub"}'
```

## 经 AOS 运行时查

```python
from core.fabric.plugins.fabric_hub import build_default_kernel
from core.fabric.capability import Capability
hub = build_default_kernel()
hub.route(Capability.CODE_UNDERSTANDING,
          {"tool": "get_architecture", "arguments": {"project": "AOS"}})
```

## 关键文件

- `third_party/codebase-memory-mcp/README.md` —— 完整说明、8 个 MCP 工具 + 6 个 CLI 工具清单、AOS 集成细节
- `src/core/fabric/adapters/mcp_stdio_adapter.py` —— stdio MCP 客户端（subprocess + JSON-RPC）
- `src/core/fabric/adapters/codebase_memory_mcp_adapter.py` —— 8 个 MCP 工具 → `code.understanding` 映射
- `src/kernel/plugins/fabric_hub.py` —— `register_codebase_mcp` / 自动探测注册
- `tests/test_mcp_stdio_adapter.py` —— 端到端验证（对 mock server，initialize→tools/list→tools/call）

## 诚实注记

AOS 早期有两个**冒用 codebase-memory-mcp 之名**的 legacy skill（`src/skills/codebase_memory.py`、
`src/skills/codebase_memory_mcp.py`），实为自研正则玩具索引器、从未调用真工具。现已将
`codebase_memory_mcp.py` 改为真实后端薄代理（可用走真工具、不可用诚实报错，不再造假），
`codebase_memory.py` 也已纠正冒充声明。真正的集成在本文件所述新栈——以 stdio MCP 接原版二进制。
