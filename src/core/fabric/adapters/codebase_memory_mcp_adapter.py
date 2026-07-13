"""codebase-memory-mcp（DeusData，纯 C / 零依赖 / MIT）的 AOS 适配工厂。

这是「把真实开源工具弄进 AOS」的范例：AOS 不重写它的脑子，只是用 stdio
MCP 客户端（MCPStdioAdapter）把它接成 `code.understanding` 能力供给方。
FabricHub.register_codebase_mcp() 调本工厂；二进制缺失时优雅跳过（不谎报 live）。

真实暴露的 14 个 MCP 工具（索引类 + 查询类）全部归属 code.understanding；
invoke 时用 payload["tool"] 指定具体工具（诚实多路复用，绝不偷偷落到首个 tool）。
"""
from __future__ import annotations

from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter
from core.fabric.capability import Capability

# DeusData codebase-memory-mcp 真实暴露的 14 个 MCP 工具。顺序与上游 README 一致：
# 索引类 4 个 + 查询类 10 个。改这里即可同步，无需动适配器核心逻辑。
CODEBASE_MCP_TOOLS: list[str] = [
    # 索引类
    "index_repository",   # 把仓库索引进图（repo_path 绝对路径）
    "list_projects",      # 列出已索引项目及节点/边数量
    "delete_project",     # 删除项目及其图数据
    "index_status",       # 索引状态
    # 查询类
    "search_graph",       # 按标签/名称/文件/度数结构化搜索
    "trace_path",         # BFS：谁调用了某函数 / 它调用了什么
    "detect_changes",     # git diff → 受影响符号 + 风险分类（爆炸半径）
    "query_graph",        # Cypher 风格只读图查询
    "get_graph_schema",   # 各标签节点/边计数、关系模式、属性定义
    "get_code_snippet",   # 按限定名读函数源码
    "get_architecture",   # 代码库概览：语言/包/路由/热点/集群/ADR
    "search_code",        # 已索引文件内 grep 式文本搜索
    "manage_adr",         # 架构决策记录 ADR 增删改查
    "ingest_traces",      # 摄取运行时追踪验证 HTTP_CALLS 边
]


def build_codebase_mcp_adapter(
    bin_path: str,
    repo_path: str,
    engine_id: str = "codebase-memory-mcp",
    timeout: float = 60.0,
) -> MCPStdioAdapter:
    """构造一个指向 codebase-memory-mcp 的 stdio 适配器。

    bin_path: 二进制路径（如 third_party/codebase-memory-mcp/bin/codebase-memory-mcp.exe）
    repo_path: 要索引的仓库根（AOS 自身即 D:/AOS）。MCP server 在此 cwd 下运行，
               便于它把图缓存写到仓库内 .codebase-memory/，供他人直接加载。
    """
    # 14 个工具统一归属 code.understanding；具体工具由 invoke 的 payload["tool"] 选定。
    cap_map = {t: Capability.CODE_UNDERSTANDING for t in CODEBASE_MCP_TOOLS}
    return MCPStdioAdapter(
        command=[bin_path],
        engine_id=engine_id,
        cwd=repo_path,
        capability_map=cap_map,
        timeout=timeout,
    )
