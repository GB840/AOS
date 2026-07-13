"""
codebase_memory_mcp —— 真实 DeusData/codebase-memory-mcp 的薄代理（AOS 侧）。

重要更正（诚实）：本文件**不再自己造轮子**。早期版本是一个用正则粗糙解析 Python
的「玩具索引器」，却起名叫 codebase-memory-mcp、吹「Token 消耗降低 99%」，实际
从未调用过真实的 DeusData 工具——那是弄虚作假。现已改为**薄代理**：

- 真实工具由 AOS 新栈以 stdio MCP 接入（src/core/fabric/adapters/mcp_stdio_adapter.py
  + codebase_memory_mcp_adapter.py），能力为 code.understanding；
- 本 skill 只是 legacy brain/web 栈的兼容入口：可用时把 action 翻译成真实 MCP
  工具调用，不可用时报诚实错误，**绝不再偷偷做假索引**。

支持的 action（仅做「映射」，逻辑全在真实工具里）：
- index_codebase   -> index_repository(repo_path)
- search_code      -> search_code / search_graph
- get_symbol       -> get_code_snippet
- get_file_context -> get_code_snippet
- list_symbols     -> list_projects
- analyze_project  -> get_architecture
- clear_index      -> delete_project
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .base import Skill
from utils.config import config

logger = logging.getLogger(__name__)

# 保留 action 元数据，仅用于校验与命名（不再承载假索引逻辑）。
CODEBASE_FEATURES = {
    "index_codebase": {
        "name": "索引代码库",
        "description": "将整个代码库交给真实 codebase-memory-mcp 建图",
        "input": ["path", "exclusions"],
        "output": {"index_path", "symbol_count", "file_count"},
    },
    "search_code": {
        "name": "搜索代码",
        "description": "语义/符号/文本搜索（委托真实工具）",
        "input": ["query", "search_type", "top_k"],
        "output": {"results", "count"},
    },
    "get_symbol": {
        "name": "获取符号",
        "description": "获取函数/类定义与引用（委托真实工具）",
        "input": ["symbol_name", "symbol_type"],
        "output": {"definition", "references", "context"},
    },
    "get_file_context": {
        "name": "获取文件上下文",
        "description": "获取文件结构上下文（委托真实工具）",
        "input": ["file_path"],
        "output": {"file_info", "classes", "functions", "imports"},
    },
    "list_symbols": {
        "name": "列出符号",
        "description": "列出已索引项目（委托真实工具）",
        "input": ["symbol_type"],
        "output": {"symbols", "count"},
    },
    "analyze_project": {
        "name": "分析项目",
        "description": "架构概览：语言/包/路由/热点/集群（委托真实工具）",
        "input": ["path"],
        "output": {"project_info", "structure", "dependencies", "complexity"},
    },
    "clear_index": {
        "name": "清除索引",
        "description": "删除项目图数据（委托真实工具）",
        "input": [],
        "output": {"success"},
    },
}


class CodebaseMemoryMCPSkill(Skill):
    """真实 codebase-memory-mcp 的薄代理（legacy 入口，逻辑在真实工具里）。"""

    NAME = "codebase_memory_mcp"
    DESCRIPTION = "codebase-memory-mcp 薄代理：把代码理解请求委派给真实的 DeusData 工具（stdio MCP / code.understanding）"
    VERSION = "2.0.0"
    AUTHOR = "AOS（委派至 DeusData/codebase-memory-mcp, MIT）"
    LICENSE = "MIT"
    CATEGORY = "development"
    TAGS = ["codebase", "memory", "mcp", "knowledge", "search", "code", "delegate"]
    CAPABILITIES = [
        "code_indexing",
        "code_search",
        "symbol_resolution",
        "project_analysis",
        "semantic_search",
        "knowledge_graph",
        "code_context",
    ]

    def __init__(self):
        super().__init__()
        self._indexed = False  # 仅反映最近一次委派是否成功，不做本地假索引

    # ---- 路径/二进制探测（与 FabricHub 同策略） -----------------
    def _repo_path(self) -> str:
        return getattr(config, "BASE_DIR", str(Path.cwd()))

    def _project_name(self) -> str:
        return Path(self._repo_path()).resolve().name

    def _real_adapter(self):
        """构造真实 stdio 适配器；二进制不可用返回 None（诚实失败）。"""
        bin_path = os.environ.get("AOS_CODEBASE_MCP_BIN")
        if not bin_path or not os.path.isfile(bin_path):
            default = (
                Path(self._repo_path())
                / "third_party"
                / "codebase-memory-mcp"
                / "bin"
                / "codebase-memory-mcp.exe"
            )
            if default.is_file():
                bin_path = str(default)
        if not bin_path or not os.path.isfile(bin_path):
            return None
        try:
            from core.fabric.adapters.codebase_memory_mcp_adapter import (
                build_codebase_mcp_adapter,
            )
            return build_codebase_mcp_adapter(bin_path, repo_path=self._repo_path())
        except Exception as e:  # noqa: BLE001
            logger.warning("构造真实 codebase-memory-mcp 适配器失败: %s", e)
            return None

    # ---- action -> 真实 MCP 工具 映射 ----------------------------
    def _map_action(self, action: str, context: Dict[str, Any]
                    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        project = self._project_name()
        if action == "index_codebase":
            return "index_repository", {"repo_path": context.get("path") or self._repo_path()}
        if action == "search_code":
            q = context.get("query", "")
            if context.get("search_type") == "symbol":
                return "search_graph", {"name_pattern": q}
            return "search_code", {"project": project, "query": q}
        if action == "get_symbol":
            return "get_code_snippet", {"qualified_name": context.get("symbol_name", "")}
        if action == "get_file_context":
            return "get_code_snippet", {"qualified_name": context.get("file_path", "")}
        if action == "list_symbols":
            return "list_projects", {}
        if action == "analyze_project":
            return "get_architecture", {"project": project}
        if action == "clear_index":
            return "delete_project", {"project": project}
        return None

    # ---- 执行（委派，不再造假） ----------------------------------
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        action = context.get("action", "search_code")
        feat = CODEBASE_FEATURES.get(action)
        if feat is None:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用: {list(CODEBASE_FEATURES.keys())}",
                "available_actions": CODEBASE_FEATURES,
                "mode": "delegated",
                "indexed": False,
                "timestamp": datetime.now().isoformat(),
            }

        adapter = self._real_adapter()
        if adapter is None:
            # 诚实：真实工具没装，绝不偷偷用假索引糊弄。
            return {
                "success": False,
                "error": (
                    "真实 codebase-memory-mcp 未安装或未通电：请运行 "
                    "third_party/codebase-memory-mcp/install.ps1 安装二进制，"
                    "或将 AOS_CODEBASE_MCP_BIN 指向它。"
                ),
                "action": action,
                "action_name": feat["name"],
                "mode": "delegated",
                "indexed": False,
                "timestamp": datetime.now().isoformat(),
            }

        mapped = self._map_action(action, context)
        if mapped is None:
            adapter.shutdown()
            return {
                "success": False,
                "error": f"无法将操作 {action} 映射到真实工具",
                "action": action,
                "action_name": feat["name"],
                "mode": "delegated",
                "indexed": False,
                "timestamp": datetime.now().isoformat(),
            }

        tool, arguments = mapped
        try:
            from core.fabric.adapter import InvokeRequest
            from core.fabric.capability import Capability

            res = adapter.invoke(
                InvokeRequest(
                    capability=Capability.CODE_UNDERSTANDING,
                    payload={"tool": tool, "arguments": arguments},
                )
            )
        except Exception as e:  # noqa: BLE001
            adapter.shutdown()
            return {
                "success": False,
                "error": f"真实工具调用失败: {e!r}",
                "action": action,
                "action_name": feat["name"],
                "mode": "delegated",
                "indexed": False,
                "timestamp": datetime.now().isoformat(),
            }
        adapter.shutdown()

        if res.ok:
            text = (res.data or {}).get("text", "")
            self._indexed = True
            return {
                "success": True,
                "task_id": str(uuid.uuid4())[:8],
                "action": action,
                "action_name": feat["name"],
                "result": {
                    "results": [
                        {
                            "type": "tool_result",
                            "tool": (res.data or {}).get("tool"),
                            "text": text,
                        }
                    ],
                    "count": 1,
                    "raw": (res.data or {}).get("raw"),
                },
                "mode": "delegated-real",
                "indexed": True,
                "timestamp": datetime.now().isoformat(),
            }
        return {
            "success": False,
            "error": res.error or "真实工具返回错误",
            "action": action,
            "action_name": feat["name"],
            "mode": "delegated",
            "indexed": False,
            "timestamp": datetime.now().isoformat(),
        }

    def list_features(self) -> Dict[str, Any]:
        return CODEBASE_FEATURES

    def is_indexed(self) -> bool:
        return self._indexed


def get_codebase_memory_mcp_skill() -> CodebaseMemoryMCPSkill:
    """获取或创建 Codebase Memory MCP 技能实例"""
    return CodebaseMemoryMCPSkill()


def register_codebase_memory_mcp_skill(registry=None):
    """注册 Codebase Memory MCP 技能到技能注册表（现为真实工具薄代理）"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()

    skill = CodebaseMemoryMCPSkill()
    registry.register(skill)
    logger.info("Codebase Memory MCP 技能已注册（委派至真实 DeusData 工具）")
    return skill
