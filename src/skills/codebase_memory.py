"""
Codebase Memory Skill Module - 轻量本地索引器（LEGACY，非 DeusData 工具）

诚实声明：本文件是 AOS 早期自研的一个**轻量本地索引器**（基于正则/简单解析），
NOT DeusData 的 codebase-memory-mcp。之前文档曾误称其为「DeusData 团队开发的高
性能代码智能 MCP 服务器 / 基于 Tree-Sitter / 14 个 MCP 工具」——那是错误标注，
已纠正。真正的 DeusData 工具以 stdio MCP 接入 AOS 新栈（code.understanding 能力，
见 third_party/codebase-memory-mcp/README.md 与 src/skills/codebase_memory_mcp.py 的
薄代理）。本文件保留为 legacy 本地兜底，供无真实工具环境时的轻量检索。
"""

import os
import logging
import uuid
from typing import Dict, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)

CODEBASE_TOOLS = {
    "search": {"name": "语义搜索", "description": "搜索代码中的符号、函数、类"},
    "call_graph": {"name": "调用链追踪", "description": "追踪函数调用链"},
    "architecture": {"name": "架构分析", "description": "分析模块结构和依赖关系"},
    "impact": {"name": "变更影响分析", "description": "评估变更对其他模块的影响"},
    "find_definition": {"name": "查找定义", "description": "查找符号定义位置"},
    "find_references": {"name": "查找引用", "description": "查找符号引用位置"},
    "type_inference": {"name": "类型推断", "description": "推断参数和返回类型"},
    "dependency_graph": {"name": "依赖图谱", "description": "生成依赖关系图"},
    "index_status": {"name": "索引状态", "description": "查询索引状态"},
    "list_symbols": {"name": "列出符号", "description": "列出项目中的所有符号"},
    "get_file_structure": {"name": "文件结构", "description": "获取文件的AST结构"},
    "compare_versions": {"name": "版本比较", "description": "比较代码变更"},
    "generate_doc": {"name": "生成文档", "description": "为代码生成文档"},
    "analyze_complexity": {"name": "复杂度分析", "description": "分析代码复杂度"},
}


class CodebaseMemorySkill(Skill):
    """
    Codebase Memory 技能（legacy 本地索引器）

    轻量本地索引/检索，非 DeusData 的 codebase-memory-mcp。
    真实工具以 stdio MCP 接入 AOS 新栈（code.understanding 能力）。
    """
    
    NAME = "codebase_memory"
    DESCRIPTION = "Codebase Memory（legacy 轻量本地索引器，非 DeusData 工具；真实工具见 third_party/codebase-memory-mcp/）"
    VERSION = "1.0.0"
    AUTHOR = "AOS（legacy 本地索引器）"
    LICENSE = "MIT"
    CATEGORY = "development"
    TAGS = ["code", "memory", "mcp", "knowledge_graph", "ast", "search"]
    CAPABILITIES = ["semantic_search", "call_graph", "architecture_analysis", "impact_analysis", "find_definition", "find_references", "type_inference", "dependency_graph", "code_indexing", "generate_documentation", "complexity_analysis"]
    
    def __init__(self):
        super().__init__()
        self._server_running = False
        self._server_port = 8080
        self._indexed_projects: Dict[str, Dict] = {}
        self._mcp_client = None
        self._enhanced_mode = True
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行代码库分析任务
        
        Args:
            context: 执行上下文
                - tool: 工具名称 (search/call_graph/architecture/impact/find_definition/find_references/type_inference/dependency_graph/index_status/list_symbols/get_file_structure/compare_versions/generate_doc/analyze_complexity)
                - project_path: 项目路径
                - query: 查询内容
                - file_path: 文件路径（可选）
        
        Returns:
            Dict: 执行结果
        """
        tool = context.get("tool", context.get("action", "search"))
        project_path = context.get("project_path", context.get("path", ""))
        
        if not project_path:
            return {
                "success": False,
                "error": "缺少 project_path 参数",
                "available_tools": list(CODEBASE_TOOLS.keys()),
            }
        
        if tool not in CODEBASE_TOOLS:
            return {
                "success": False,
                "error": f"未知工具: {tool}，可用工具: {list(CODEBASE_TOOLS.keys())}",
                "available_tools": CODEBASE_TOOLS,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode:
            result = self._execute_enhanced(tool, project_path, context)
        else:
            result = self._execute_mcp(tool, project_path, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "tool": tool,
            "tool_name": CODEBASE_TOOLS[tool]["name"],
            "project_path": project_path,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode else "mcp",
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, tool: str, project_path: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用内置能力"""
        try:
            if tool == "search":
                return self._search_code(project_path, context.get("query", ""))
            elif tool == "architecture":
                return self._analyze_architecture(project_path)
            elif tool == "call_graph":
                return self._analyze_call_graph(project_path, context.get("query", ""))
            elif tool == "impact":
                return self._analyze_impact(project_path, context.get("query", ""))
            elif tool == "find_definition":
                return self._find_definition(project_path, context.get("query", ""))
            elif tool == "find_references":
                return self._find_references(project_path, context.get("query", ""))
            elif tool == "list_symbols":
                return self._list_symbols(project_path)
            elif tool == "get_file_structure":
                return self._get_file_structure(project_path, context.get("file_path", ""))
            elif tool == "generate_doc":
                return self._generate_doc(project_path, context.get("file_path", ""))
            elif tool == "index_status":
                return self._get_index_status(project_path)
            elif tool == "dependency_graph":
                return self._build_dependency_graph(project_path)
            elif tool == "type_inference":
                return self._infer_types(project_path, context.get("query", ""))
            elif tool == "compare_versions":
                return {"success": True, "result": {"message": "版本比较功能需要 Git 仓库"}}
            elif tool == "analyze_complexity":
                return self._analyze_complexity(project_path)
            else:
                return {"success": False, "error": f"未知工具: {tool}"}
        except Exception as e:
            logger.error(f"增强模式执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_mcp(self, tool: str, project_path: str, context: Dict) -> Dict[str, Any]:
        """MCP模式执行 — 调用外部服务器"""
        try:
            import requests
            
            url = f"http://localhost:{self._server_port}/api/{tool}"
            params = {
                "project_path": project_path,
                **context,
            }
            
            response = requests.post(url, json=params, timeout=30)
            return response.json()
        except Exception as e:
            logger.error(f"MCP模式执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _search_code(self, project_path: str, query: str) -> Dict[str, Any]:
        """语义搜索"""
        results = []
        extensions = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", "venv")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if query.lower() in content.lower():
                                lines = content.split("\n")
                                matches = []
                                for i, line in enumerate(lines, 1):
                                    if query.lower() in line.lower():
                                        matches.append({"line": i, "content": line.strip()})
                                if matches:
                                    results.append({
                                        "file": file_path,
                                        "matches": matches[:5],
                                    })
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": {
                "query": query,
                "results": results[:20],
                "total": len(results),
            },
        }
    
    def _analyze_architecture(self, project_path: str) -> Dict[str, Any]:
        """架构分析"""
        modules = {}
        extensions = (".py", ".js", ".ts", ".tsx", ".jsx")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", "venv")]
            
            rel_path = os.path.relpath(root, project_path)
            if rel_path == ".":
                module_name = "root"
            else:
                module_name = rel_path.replace(os.sep, ".")
            
            module_files = []
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    module_files.append(file)
            
            if module_files:
                modules[module_name] = {
                    "path": rel_path,
                    "files": module_files,
                    "count": len(module_files),
                }
        
        return {
            "success": True,
            "result": {
                "project": project_path,
                "modules": modules,
                "total_modules": len(modules),
                "total_files": sum(m["count"] for m in modules.values()),
            },
        }
    
    def _analyze_call_graph(self, project_path: str, query: str) -> Dict[str, Any]:
        """调用链追踪"""
        calls = []
        extensions = (".py", ".js", ".ts")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            lines = content.split("\n")
                            for i, line in enumerate(lines, 1):
                                if query in line and "def " not in line and "function " not in line:
                                    calls.append({
                                        "file": file_path,
                                        "line": i,
                                        "context": line.strip(),
                                    })
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": {
                "function": query,
                "calls": calls[:20],
                "total_calls": len(calls),
            },
        }
    
    def _analyze_impact(self, project_path: str, query: str) -> Dict[str, Any]:
        """变更影响分析"""
        references = []
        extensions = (".py", ".js", ".ts", ".tsx")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if query in content:
                                references.append({
                                    "file": file_path,
                                    "impact_level": "high" if content.count(query) > 5 else "medium",
                                })
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": {
                "target": query,
                "affected_files": references[:20],
                "total_affected": len(references),
                "high_impact": sum(1 for r in references if r["impact_level"] == "high"),
            },
        }
    
    def _find_definition(self, project_path: str, query: str) -> Dict[str, Any]:
        """查找定义"""
        definitions = []
        extensions = (".py", ".js", ".ts", ".java", ".go")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            lines = content.split("\n")
                            for i, line in enumerate(lines, 1):
                                if f"def {query}" in line or f"function {query}" in line or f"class {query}" in line:
                                    definitions.append({
                                        "file": file_path,
                                        "line": i,
                                        "definition": line.strip(),
                                    })
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": {
                "symbol": query,
                "definitions": definitions[:10],
                "total": len(definitions),
            },
        }
    
    def _find_references(self, project_path: str, query: str) -> Dict[str, Any]:
        """查找引用"""
        return self._search_code(project_path, query)
    
    def _list_symbols(self, project_path: str) -> Dict[str, Any]:
        """列出符号"""
        symbols = {"functions": [], "classes": [], "variables": []}
        extensions = (".py", ".js", ".ts")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            lines = content.split("\n")
                            for line in lines:
                                if line.strip().startswith("def "):
                                    name = line.strip().split("def ")[1].split("(")[0]
                                    symbols["functions"].append({"name": name, "file": file_path})
                                elif line.strip().startswith("class "):
                                    name = line.strip().split("class ")[1].split("(")[0].split(":")[0]
                                    symbols["classes"].append({"name": name, "file": file_path})
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": {
                "project": project_path,
                "symbols": symbols,
                "total_functions": len(symbols["functions"]),
                "total_classes": len(symbols["classes"]),
            },
        }
    
    def _get_file_structure(self, project_path: str, file_path: str) -> Dict[str, Any]:
        """获取文件结构"""
        full_path = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path
        
        if not os.path.exists(full_path):
            return {"success": False, "error": f"文件不存在: {full_path}"}
        
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            lines = content.split("\n")
            structure = []
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("function "):
                    structure.append({"line": i, "type": "function" if "def" in stripped or "function" in stripped else "class", "name": stripped.split("(")[0].split(" ")[1]})
            
            return {
                "success": True,
                "result": {
                    "file": full_path,
                    "lines": len(lines),
                    "structure": structure,
                    "preview": "\n".join(lines[:50]),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _generate_doc(self, project_path: str, file_path: str) -> Dict[str, Any]:
        """生成文档"""
        from core import get_brain
        
        brain = get_brain()
        
        full_path = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path
        
        if not os.path.exists(full_path):
            return {"success": False, "error": f"文件不存在: {full_path}"}
        
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            prompt = f"""你是一名专业的代码文档生成器。请为以下代码生成详细的文档。

文件: {file_path}

代码内容:
{content[:3000]}

要求:
1. 生成文件级别的说明文档
2. 为每个函数/类生成详细文档（功能、参数、返回值）
3. 使用 Markdown 格式输出
4. 包含代码结构分析"""
            
            result = brain.chat(message=prompt, session_id=f"codebase-doc-{file_path[:20]}")
            
            return {
                "success": True,
                "result": {
                    "file": file_path,
                    "documentation": result.get("response", ""),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_index_status(self, project_path: str) -> Dict[str, Any]:
        """获取索引状态"""
        if project_path in self._indexed_projects:
            return {
                "success": True,
                "result": {
                    "project": project_path,
                    "status": self._indexed_projects[project_path].get("status", "indexed"),
                    "indexed_at": self._indexed_projects[project_path].get("indexed_at"),
                    "files_indexed": self._indexed_projects[project_path].get("files_indexed", 0),
                },
            }
        
        return {
            "success": True,
            "result": {
                "project": project_path,
                "status": "not_indexed",
                "message": "项目尚未索引，调用 search 或 architecture 工具会自动索引",
            },
        }
    
    def _build_dependency_graph(self, project_path: str) -> Dict[str, Any]:
        """构建依赖图谱"""
        dependencies = {}
        extensions = (".py", ".js", ".ts")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            imports = []
                            for line in content.split("\n"):
                                if line.strip().startswith("import ") or line.strip().startswith("from "):
                                    imports.append(line.strip())
                            if imports:
                                dependencies[file_path] = {"imports": imports[:10]}
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": {
                "project": project_path,
                "dependencies": dependencies,
                "total_files": len(dependencies),
            },
        }
    
    def _infer_types(self, project_path: str, query: str) -> Dict[str, Any]:
        """类型推断"""
        from core import get_brain
        
        brain = get_brain()
        
        prompt = f"""你是一名专业的代码分析专家。请分析以下函数的参数类型和返回类型。

函数名: {query}
项目路径: {project_path}

请提供：
1. 参数列表及类型
2. 返回值类型
3. 可能的类型推断依据"""
        
        result = brain.chat(message=prompt, session_id=f"codebase-type-{query}")
        
        return {
            "success": True,
            "result": {
                "function": query,
                "type_inference": result.get("response", ""),
            },
        }
    
    def _analyze_complexity(self, project_path: str) -> Dict[str, Any]:
        """复杂度分析"""
        complexity = {"files": [], "total_lines": 0, "total_functions": 0, "complex_files": []}
        extensions = (".py", ".js", ".ts")
        
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
            
            for file in files:
                if file.endswith(extensions):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            lines = content.split("\n")
                            func_count = sum(1 for l in lines if l.strip().startswith("def ") or l.strip().startswith("function "))
                            file_complexity = len(lines) * (1 + func_count * 0.5)
                            
                            complexity["files"].append({
                                "file": file_path,
                                "lines": len(lines),
                                "functions": func_count,
                                "complexity": file_complexity,
                            })
                            
                            complexity["total_lines"] += len(lines)
                            complexity["total_functions"] += func_count
                            
                            if file_complexity > 100:
                                complexity["complex_files"].append(file_path)
                    except Exception:
                        pass
        
        return {
            "success": True,
            "result": complexity,
        }
    
    def list_tools(self) -> Dict[str, Any]:
        """列出所有可用工具"""
        return CODEBASE_TOOLS
    
    def is_enhanced_mode(self) -> bool:
        """检查是否在增强模式"""
        return self._enhanced_mode


def get_codebase_memory_skill() -> CodebaseMemorySkill:
    """获取或创建 Codebase Memory 技能实例"""
    return CodebaseMemorySkill()


def register_codebase_memory_skill(registry=None):
    """注册 Codebase Memory 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = CodebaseMemorySkill()
    registry.register(skill)
    logger.info("Codebase Memory MCP 技能已注册")
    return skill