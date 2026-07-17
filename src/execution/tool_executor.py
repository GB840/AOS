"""
Tool Executor - 工具执行器

统一管理所有工具的执行，支持：
- 外部工具调用
- MCP工具调用
- 内置工具调用
- 异步工具执行
- 工具结果收集与格式化

标准：OpenAI Function Calling 标准
"""

import logging
import asyncio
from typing import Dict, List, Any, Callable
from datetime import datetime

from core.fabric.tool_call_repair import execute_with_repair, ToolCallRepair

logger = logging.getLogger(__name__)


class ToolExecutor:
    """工具执行器 - 统一管理所有工具的调用"""
    
    def __init__(self):
        # 工具注册表，用于存储已注册的工具
        self._tool_registry = {}
        
        logger.info("ToolExecutor initialized")
    
    def register_tool(self, 
                      name: str, 
                      description: str,
                      parameters: Dict,
                      handler: Callable) -> Dict[str, Any]:
        """注册工具"""
        if name in self._tool_registry:
            return {"success": False, "error": f"工具已存在: {name}"}
        
        self._tool_registry[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": handler,
            "registered_at": datetime.now().isoformat(),
        }
        
        logger.info(f"工具注册成功: {name}")
        return {"success": True, "message": f"工具 {name} 已注册"}
    
    def _execute_raw(self, tool_name: str, arguments: Any) -> Dict[str, Any]:
        """不加修复的原始执行（execute_tool 的内层）。保留现有语义：
        合法调用一次成功即返回；handler 抛异常则捕获为 error dict。"""
        tool = self._tool_registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        try:
            start_time = datetime.now()
            result = tool["handler"](**(arguments or {}))
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "success": True,
                "tool_name": tool_name,
                "result": result,
                "duration": round(duration, 2),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_tool(self, 
                     tool_name: str,
                     arguments: Any = None,
                     *, repair: bool = True) -> Dict[str, Any]:
        """执行工具（默认带 Tool-Call Repair 自愈，借鉴 Reasonix）。

        修复层作为「前置参数规范化 + 失败自愈」始终生效（repair=True 时）：
        先按 JSON Schema 规范化参数（类型强制/枚举裁剪/未知字段剔除/缺必填报
        default），再执行；执行失败则升级 aggressiveness（激进 JSON 容错/推断补
        必填）重试。合法调用零改写，且 repair 报告始终量化附回（理念6 诚实+量化）。
        repair=False 时退化为纯原样执行（无 repair 键）。
        """
        tool = self._tool_registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        if not repair or not isinstance(arguments, (str, dict)):
            return self._execute_raw(tool_name, arguments)
        schema = tool.get("parameters") or {}
        repaired = execute_with_repair(self, tool_name, arguments, schema=schema)
        repaired.setdefault("tool_name", tool_name)
        return repaired
    
    def execute_with_repair(self, 
                            tool_name: str,
                            raw_args: Any,
                            *, max_rounds: int = 3) -> Dict[str, Any]:
        """带工具调用修复地执行工具（借鉴 Reasonix Tool-Call Repair）。

        当 LLM 返回的原始参数「脏」（JSON 不合法/类型错位/缺必填/枚举越界/夹带
        未知字段）导致执行失败时，自动诊断并就地修复后重试，避免直接判失败。
        修复动作全部量化记录在返回的 repair 字段里（理念6 诚实+量化）。
        schema 自动取该工具注册时的 parameters；无 schema 时仅做 JSON 容错。
        """
        tool = self._tool_registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        schema = tool.get("parameters") or {}
        return execute_with_repair(self, tool_name, raw_args,
                                   schema=schema, max_rounds=max_rounds)
    
    async def execute_tool_async(self, 
                                  tool_name: str,
                                  arguments: Any = None,
                                  *, repair: bool = True) -> Dict[str, Any]:
        """异步执行工具（默认带修复自愈，同 execute_tool）"""
        tool = self._tool_registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        try:
            start_time = datetime.now()
            if asyncio.iscoroutinefunction(tool["handler"]):
                result = await tool["handler"](**(arguments or {}))
            else:
                result = await asyncio.to_thread(tool["handler"], **(arguments or {}))
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "success": True,
                "tool_name": tool_name,
                "result": result,
                "duration": round(duration, 2),
            }
        except Exception as e:
            first_err = str(e)
            if not repair or not isinstance(arguments, (str, dict)):
                return {"success": False, "error": first_err}
            schema = tool.get("parameters") or {}
            repaired = execute_with_repair(self, tool_name, arguments, schema=schema)
            if repaired.get("success"):
                repaired.setdefault("tool_name", tool_name)
                return repaired
            out = {"success": False, "error": first_err}
            if repaired.get("repair"):
                out["repair"] = repaired["repair"]
            return out
    
    def execute_tools_batch(self, 
                            tools: List[Dict]) -> List[Dict[str, Any]]:
        """批量执行工具"""
        results = []
        
        for tool in tools:
            tool_name = tool.get("name")
            arguments = tool.get("arguments", {})
            
            result = self.execute_tool(tool_name, arguments)
            results.append(result)
        
        return results
    
    def list_tools(self) -> Dict[str, Any]:
        """列出所有已注册的工具"""
        tools_info = []
        
        for name, tool in self._tool_registry.items():
            tools_info.append({
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"],
                "registered_at": tool["registered_at"],
            })
        
        return {
            "success": True,
            "tools": tools_info,
            "count": len(tools_info),
        }
    
    def get_tool_info(self, tool_name: str) -> Dict[str, Any]:
        """获取工具信息"""
        tool = self._tool_registry.get(tool_name)
        
        if not tool:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        
        return {
            "success": True,
            "tool": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "registered_at": tool["registered_at"],
            },
        }
    
    def unregister_tool(self, tool_name: str) -> Dict[str, Any]:
        """注销工具"""
        if tool_name not in self._tool_registry:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        
        del self._tool_registry[tool_name]
        logger.info(f"工具已注销: {tool_name}")
        
        return {"success": True, "message": f"工具 {tool_name} 已注销"}
