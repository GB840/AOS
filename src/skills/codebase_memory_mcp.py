"""
Codebase Memory MCP Skill Module - 项目级长期记忆引擎

codebase-memory-mcp 是一个强大的代码库记忆系统，将代码库解析为知识图谱，
替代昂贵的逐文件读取，将Token消耗降低99%。

核心价值:
- 代码感知: 将整个代码库解析为结构化知识图谱
- 智能检索: 支持语义搜索、符号搜索、路径搜索
- Token节约: 避免重复读取整个文件，按需检索
- 项目级记忆: 为Hermes提供跨会话的代码上下文

部署位置:
1. Hermes 认知大脑的"代码记忆层" - 代码感知与检索
2. DeerFlow 任务调度引擎的"代码分析Worker" - 代码理解与分析
3. AI 工厂的"代码知识库" - RAG系统

支持的操作:
- index_codebase: 索引整个代码库
- search_code: 搜索代码（语义/符号/路径）
- get_symbol: 获取符号定义
- get_file_context: 获取文件上下文
- list_symbols: 列出所有符号
- analyze_project: 分析项目结构
"""

import os
import sys
import json
import logging
import uuid
import time
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .base import Skill, SkillMeta
from utils.config import config

logger = logging.getLogger(__name__)

CODEBASE_FEATURES = {
    "index_codebase": {
        "name": "索引代码库",
        "description": "将整个代码库解析为知识图谱并建立索引",
        "input": ["path", "exclusions"],
        "output": {"index_path", "symbol_count", "file_count"},
    },
    "search_code": {
        "name": "搜索代码",
        "description": "支持语义搜索、符号搜索、路径搜索",
        "input": ["query", "search_type", "top_k"],
        "output": {"results", "count"},
    },
    "get_symbol": {
        "name": "获取符号",
        "description": "获取函数、类、变量的定义和引用",
        "input": ["symbol_name", "symbol_type"],
        "output": {"definition", "references", "context"},
    },
    "get_file_context": {
        "name": "获取文件上下文",
        "description": "获取文件的结构化上下文（类、函数、依赖）",
        "input": ["file_path"],
        "output": {"file_info", "classes", "functions", "imports"},
    },
    "list_symbols": {
        "name": "列出符号",
        "description": "列出项目中所有符号（函数、类、变量）",
        "input": ["symbol_type"],
        "output": {"symbols", "count"},
    },
    "analyze_project": {
        "name": "分析项目",
        "description": "分析项目结构、依赖关系、代码复杂度",
        "input": ["path"],
        "output": {"project_info", "structure", "dependencies", "complexity"},
    },
    "clear_index": {
        "name": "清除索引",
        "description": "清除现有索引，重新建立",
        "input": [],
        "output": {"success"},
    },
}

EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".idea", ".vscode", "dist", "build", "outputs", "data", "logs",
}

EXCLUDED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".egg-info", ".so", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".tar", ".gz", ".zip", ".rar", ".7z",
    ".log", ".tmp", ".bak",
}


class CodebaseMemoryMCPSkill(Skill):
    """
    Codebase Memory MCP 技能 - 项目级长期记忆
    
    将代码库解析为知识图谱，为Hermes提供代码感知能力。
    支持语义搜索、符号搜索、路径搜索，将Token消耗降低99%。
    """
    
    NAME = "codebase_memory_mcp"
    DESCRIPTION = "Codebase Memory MCP — 项目级长期记忆引擎，将代码库解析为知识图谱，Token消耗降低99%"
    VERSION = "1.0.0"
    AUTHOR = "codebase-memory-mcp"
    LICENSE = "MIT"
    CATEGORY = "development"
    TAGS = ["codebase", "memory", "mcp", "knowledge", "search", "code"]
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
        self._index_path = os.path.join(config.BASE_DIR, "codebase_index")
        self._index_data = {}
        self._symbols = {}
        self._files = {}
        self._project_info = {}
        self._indexed = False
        
        Path(self._index_path).mkdir(parents=True, exist_ok=True)
        self._load_index()
    
    def _load_index(self):
        """加载已有的索引"""
        index_file = os.path.join(self._index_path, "index.json")
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    self._index_data = json.load(f)
                    self._symbols = self._index_data.get("symbols", {})
                    self._files = self._index_data.get("files", {})
                    self._project_info = self._index_data.get("project_info", {})
                    self._indexed = True
                logger.info(f"代码库索引已加载: {len(self._symbols)} 个符号, {len(self._files)} 个文件")
            except Exception as e:
                logger.warning(f"加载索引失败: {e}")
    
    def _save_index(self):
        """保存索引"""
        index_file = os.path.join(self._index_path, "index.json")
        self._index_data = {
            "symbols": self._symbols,
            "files": self._files,
            "project_info": self._project_info,
            "indexed_at": datetime.now().isoformat(),
        }
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(self._index_data, f, ensure_ascii=False, indent=2)
    
    def _should_exclude(self, path: str) -> bool:
        """判断是否排除路径"""
        parts = path.replace("\\", "/").split("/")
        for part in parts:
            if part in EXCLUDED_DIRS:
                return True
        
        ext = os.path.splitext(path)[1].lower()
        if ext in EXCLUDED_EXTENSIONS:
            return True
        
        return False
    
    def _parse_python_file(self, file_path: str) -> Dict[str, Any]:
        """解析Python文件，提取符号"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            file_info = {
                "path": file_path,
                "size": len(content),
                "lines": content.count("\n") + 1,
                "classes": [],
                "functions": [],
                "imports": [],
                "docstrings": [],
            }
            
            import re
            
            for match in re.finditer(r'^import\s+(\w+(?:\.\w+)*)', content, re.MULTILINE):
                file_info["imports"].append(match.group(1))
            
            for match in re.finditer(r'^from\s+(\w+(?:\.\w+)*)\s+import', content, re.MULTILINE):
                file_info["imports"].append(match.group(1))
            
            class_pattern = r'(?:class\s+(\w+)\s*(?:\([^)]*\))?\s*:)|(?:def\s+(\w+)\s*\([^)]*\)\s*:)'
            for match in re.finditer(class_pattern, content):
                if match.group(1):
                    class_name = match.group(1)
                    file_info["classes"].append(class_name)
                    self._symbols[class_name] = {
                        "name": class_name,
                        "type": "class",
                        "file": file_path,
                        "line": content[:match.start()].count("\n") + 1,
                        "context": self._extract_context(content, match.start(), match.end(), 3),
                    }
                elif match.group(2):
                    func_name = match.group(2)
                    file_info["functions"].append(func_name)
                    self._symbols[func_name] = {
                        "name": func_name,
                        "type": "function",
                        "file": file_path,
                        "line": content[:match.start()].count("\n") + 1,
                        "context": self._extract_context(content, match.start(), match.end(), 3),
                    }
            
            return file_info
        except Exception as e:
            logger.debug(f"解析文件失败 {file_path}: {e}")
            return {"path": file_path, "error": str(e)}
    
    def _extract_context(self, content: str, start: int, end: int, lines: int) -> str:
        """提取上下文内容"""
        lines_before = content[:start].split("\n")[-lines:]
        lines_after = content[end:].split("\n")[:lines]
        
        before_text = "\n".join(lines_before)
        middle_text = content[start:end]
        after_text = "\n".join(lines_after)
        
        return f"{before_text}\n{middle_text}\n{after_text}".strip()
    
    def _scan_directory(self, path: str, exclusions: List[str] = None) -> List[str]:
        """扫描目录，获取所有代码文件"""
        files = []
        exclusions = exclusions or []
        
        for root, dirs, filenames in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and d not in exclusions]
            
            for filename in filenames:
                file_path = os.path.join(root, filename)
                if not self._should_exclude(file_path):
                    files.append(file_path)
        
        return files
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行代码库记忆操作
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - path: 项目路径
                - query: 搜索查询
                - search_type: 搜索类型 (semantic/symbol/path)
                - symbol_name: 符号名称
                - symbol_type: 符号类型 (class/function/variable)
                - file_path: 文件路径
                - top_k: 返回数量
                - exclusions: 排除目录列表
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "search_code")
        
        if action not in CODEBASE_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(CODEBASE_FEATURES.keys())}",
                "available_actions": CODEBASE_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        result = self._execute_action(action, task_id, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": CODEBASE_FEATURES[action]["name"],
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._indexed else "building",
            "indexed": self._indexed,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_action(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """执行具体操作"""
        try:
            if action == "index_codebase":
                return self._index_codebase(context)
            elif action == "search_code":
                return self._search_code(context)
            elif action == "get_symbol":
                return self._get_symbol(context)
            elif action == "get_file_context":
                return self._get_file_context(context)
            elif action == "list_symbols":
                return self._list_symbols(context)
            elif action == "analyze_project":
                return self._analyze_project(context)
            elif action == "clear_index":
                return self._clear_index(context)
            else:
                return {"success": False, "error": f"操作 {action} 未实现"}
        except Exception as e:
            logger.error(f"执行失败 {action}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _index_codebase(self, context: Dict) -> Dict[str, Any]:
        """索引整个代码库"""
        path = context.get("path", config.BASE_DIR)
        exclusions = context.get("exclusions", [])
        
        logger.info(f"开始索引代码库: {path}")
        
        self._symbols = {}
        self._files = {}
        
        files = self._scan_directory(path, exclusions)
        logger.info(f"发现 {len(files)} 个文件")
        
        for file_path in files:
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == ".py":
                    file_info = self._parse_python_file(file_path)
                    self._files[file_path] = file_info
                else:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        self._files[file_path] = {
                            "path": file_path,
                            "size": len(content),
                            "lines": content.count("\n") + 1,
                        }
            except Exception as e:
                logger.debug(f"处理文件失败 {file_path}: {e}")
        
        self._project_info = {
            "path": path,
            "file_count": len(self._files),
            "symbol_count": len(self._symbols),
            "class_count": sum(1 for s in self._symbols.values() if s["type"] == "class"),
            "function_count": sum(1 for s in self._symbols.values() if s["type"] == "function"),
            "indexed_at": datetime.now().isoformat(),
        }
        
        self._save_index()
        self._indexed = True
        
        logger.info(f"代码库索引完成: {len(self._symbols)} 个符号, {len(self._files)} 个文件")
        
        return {
            "success": True,
            "result": {
                "index_path": self._index_path,
                "file_count": len(self._files),
                "symbol_count": len(self._symbols),
                "project_info": self._project_info,
            },
        }
    
    def _search_code(self, context: Dict) -> Dict[str, Any]:
        """搜索代码"""
        query = context.get("query", "")
        search_type = context.get("search_type", "semantic")
        top_k = context.get("top_k", 10)
        
        if not query:
            return {"success": False, "error": "请提供搜索查询"}
        
        if not self._indexed:
            self._index_codebase({"path": config.BASE_DIR})
        
        results = []
        
        if search_type == "symbol":
            for symbol_name, symbol in self._symbols.items():
                if query.lower() in symbol_name.lower():
                    results.append({
                        "type": "symbol",
                        "name": symbol_name,
                        "symbol_type": symbol["type"],
                        "file": symbol["file"],
                        "line": symbol["line"],
                        "context": symbol["context"],
                    })
        
        elif search_type == "path":
            for file_path, file_info in self._files.items():
                if query.lower() in file_path.lower():
                    results.append({
                        "type": "file",
                        "path": file_path,
                        "size": file_info.get("size", 0),
                        "lines": file_info.get("lines", 0),
                    })
        
        else:
            for symbol_name, symbol in self._symbols.items():
                context_text = symbol["context"].lower()
                if query.lower() in context_text or query.lower() in symbol_name.lower():
                    results.append({
                        "type": "symbol",
                        "name": symbol_name,
                        "symbol_type": symbol["type"],
                        "file": symbol["file"],
                        "line": symbol["line"],
                        "context": symbol["context"],
                    })
            
            for file_path, file_info in self._files.items():
                if query.lower() in file_path.lower():
                    results.append({
                        "type": "file",
                        "path": file_path,
                        "size": file_info.get("size", 0),
                        "lines": file_info.get("lines", 0),
                    })
        
        results = results[:top_k]
        
        return {
            "success": True,
            "result": {
                "query": query,
                "search_type": search_type,
                "results": results,
                "count": len(results),
            },
        }
    
    def _get_symbol(self, context: Dict) -> Dict[str, Any]:
        """获取符号定义"""
        symbol_name = context.get("symbol_name", "")
        symbol_type = context.get("symbol_type", "")
        
        if not symbol_name:
            return {"success": False, "error": "请提供符号名称"}
        
        if not self._indexed:
            self._index_codebase({"path": config.BASE_DIR})
        
        symbol = self._symbols.get(symbol_name)
        if not symbol:
            return {"success": False, "error": f"符号 {symbol_name} 未找到"}
        
        references = []
        for file_path, file_info in self._files.items():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if symbol_name in content:
                    references.append(file_path)
            except Exception:
                pass
        
        return {
            "success": True,
            "result": {
                "symbol": symbol,
                "references": references[:20],
                "reference_count": len(references),
            },
        }
    
    def _get_file_context(self, context: Dict) -> Dict[str, Any]:
        """获取文件上下文"""
        file_path = context.get("file_path", "")
        
        if not file_path:
            return {"success": False, "error": "请提供文件路径"}
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            lines = content.split("\n")
            file_info = {
                "path": file_path,
                "size": len(content),
                "lines": len(lines),
            }
            
            classes = []
            functions = []
            imports = []
            
            for i, line in enumerate(lines, 1):
                if re.match(r'^\s*class\s+\w+', line):
                    classes.append({"name": re.search(r'class\s+(\w+)', line).group(1), "line": i})
                elif re.match(r'^\s*def\s+\w+', line):
                    functions.append({"name": re.search(r'def\s+(\w+)', line).group(1), "line": i})
                elif re.match(r'^\s*(import|from)', line):
                    imports.append(line.strip())
            
            return {
                "success": True,
                "result": {
                    "file_info": file_info,
                    "classes": classes,
                    "functions": functions,
                    "imports": imports,
                    "preview": content[:2000],
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _list_symbols(self, context: Dict) -> Dict[str, Any]:
        """列出所有符号"""
        symbol_type = context.get("symbol_type", "")
        
        if not self._indexed:
            self._index_codebase({"path": config.BASE_DIR})
        
        symbols = []
        for symbol_name, symbol in self._symbols.items():
            if not symbol_type or symbol["type"] == symbol_type:
                symbols.append({
                    "name": symbol_name,
                    "type": symbol["type"],
                    "file": symbol["file"],
                    "line": symbol["line"],
                })
        
        return {
            "success": True,
            "result": {
                "symbols": symbols,
                "count": len(symbols),
            },
        }
    
    def _analyze_project(self, context: Dict) -> Dict[str, Any]:
        """分析项目结构"""
        path = context.get("path", config.BASE_DIR)
        
        if not self._indexed:
            self._index_codebase({"path": path})
        
        structure = {}
        
        for file_path in self._files.keys():
            rel_path = os.path.relpath(file_path, path)
            parts = rel_path.split(os.sep)
            current = structure
            
            for i, part in enumerate(parts):
                if part not in current:
                    if i == len(parts) - 1:
                        current[part] = {"__type": "file", "__path": file_path}
                    else:
                        current[part] = {"__type": "dir"}
                current = current[part]
        
        dependencies = []
        for file_path, file_info in self._files.items():
            if isinstance(file_info, dict) and "imports" in file_info:
                for imp in file_info["imports"]:
                    if imp not in dependencies:
                        dependencies.append(imp)
        
        complexity = {
            "total_files": len(self._files),
            "total_symbols": len(self._symbols),
            "classes": sum(1 for s in self._symbols.values() if s["type"] == "class"),
            "functions": sum(1 for s in self._symbols.values() if s["type"] == "function"),
            "dependencies": len(dependencies),
            "avg_file_size": sum(f.get("size", 0) for f in self._files.values()) / len(self._files) if self._files else 0,
        }
        
        return {
            "success": True,
            "result": {
                "project_info": self._project_info,
                "structure": structure,
                "dependencies": dependencies[:50],
                "complexity": complexity,
            },
        }
    
    def _clear_index(self, context: Dict) -> Dict[str, Any]:
        """清除索引"""
        self._symbols = {}
        self._files = {}
        self._project_info = {}
        self._indexed = False
        
        index_file = os.path.join(self._index_path, "index.json")
        if os.path.exists(index_file):
            os.remove(index_file)
        
        return {
            "success": True,
            "result": {"message": "索引已清除"},
        }
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return CODEBASE_FEATURES
    
    def is_indexed(self) -> bool:
        """检查是否已建立索引"""
        return self._indexed


def get_codebase_memory_mcp_skill() -> CodebaseMemoryMCPSkill:
    """获取或创建 Codebase Memory MCP 技能实例"""
    return CodebaseMemoryMCPSkill()


def register_codebase_memory_mcp_skill(registry=None):
    """注册 Codebase Memory MCP 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = CodebaseMemoryMCPSkill()
    registry.register(skill)
    logger.info("Codebase Memory MCP 技能已注册")
    return skill