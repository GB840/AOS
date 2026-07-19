import contextlib
import io
import json
import logging
import os
import sys
import threading
from enum import Enum
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class MCPMethod(Enum):
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"
    PING = "ping"
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"
    LOGGING_MESSAGE = "logging/message"
    SHUTDOWN = "shutdown"


class MCPErrorCode(Enum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_NOT_INITIALIZED = -32002
    UNKNOWN_RESOURCE = -32001
    UNKNOWN_TOOL = -32000
    TOOL_EXECUTION_ERROR = -32003


@dataclass
class MCPMessage:
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "MCPMessage":
        try:
            data = json.loads(json_str)
            return cls(
                jsonrpc=data.get("jsonrpc", "2.0"),
                id=data.get("id"),
                method=data.get("method"),
                params=data.get("params"),
                result=data.get("result"),
                error=data.get("error"),
            )
        except json.JSONDecodeError as e:
            return cls(
                error={
                    "code": MCPErrorCode.PARSE_ERROR.value,
                    "message": f"JSON解析错误: {str(e)}",
                }
            )


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPResource:
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class MCPPrompt:
    name: str
    description: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


class MCPProtocol:
    def __init__(self, server_name: str = "aos-mcp", server_version: str = "5.0.0"):
        self.server_name = server_name
        self.server_version = server_version
        self.protocol_version = "2024-11-05"
        self.initialized = False
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.prompts: Dict[str, MCPPrompt] = {}
        self.tool_handlers: Dict[str, Callable] = {}
        self.resource_handlers: Dict[str, Callable] = {}
        self.prompt_handlers: Dict[str, Callable] = {}
        self._subagent_registry = None
        self._register_default_tools()
        logger.info(f"MCP协议层初始化完成 ({server_name} v{server_version})")

    def _register_default_tools(self):
        self.register_tool(
            MCPTool(
                name="chat",
                description="与Hermes智能体对话",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "用户消息"},
                        "session_id": {"type": "string", "description": "会话ID"},
                    },
                    "required": ["message"],
                },
            ),
            self._default_chat_handler,
        )

        self.register_tool(
            MCPTool(
                name="search_memory",
                description="搜索记忆库",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "search_type": {"type": "string", "enum": ["hybrid", "semantic", "fulltext"], "default": "hybrid"},
                    },
                    "required": ["query"],
                },
            ),
            self._default_search_handler,
        )

        self.register_tool(
            MCPTool(
                name="get_status",
                description="获取系统状态",
                input_schema={"type": "object", "properties": {}},
            ),
            self._default_status_handler,
        )


        # ---- 子智能体 MCP Tools ----
        self.register_tool(
            MCPTool(
                name="openclaw_agent",
                description="调用OpenClaw子智能体 — 浏览器自动化、代码生成、团队协作、Web搜索",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "发送给OpenClaw的任务消息"},
                        "timeout": {"type": "integer", "description": "超时秒数", "default": 600},
                    },
                    "required": ["message"],
                },
            ),
            self._openclaw_handler,
        )

        self.register_tool(
            MCPTool(
                name="gui_automation",
                description="调用UI-TARS子智能体 — GUI桌面自动化、截屏识别、鼠标键盘操作",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "GUI自动化任务描述"},
                        "max_steps": {"type": "integer", "description": "最大步骤数", "default": 20},
                        "timeout": {"type": "integer", "description": "超时秒数", "default": 300},
                    },
                    "required": ["task"],
                },
            ),
            self._uitars_handler,
        )

        self.register_tool(
            MCPTool(
                name="office_agent",
                description="调用LobsterAI子智能体 — 办公自动化、文档处理、数据分析、PPT制作",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "办公自动化任务描述"},
                        "skill": {"type": "string", "description": "技能类型", "default": "general"},
                        "timeout": {"type": "integer", "description": "超时秒数", "default": 600},
                    },
                    "required": ["task"],
                },
            ),
            self._lobster_handler,
        )

        # ---- FabricHub 能力路由（B 路线成果对外暴露）----
        self.register_tool(
            MCPTool(
                name="aos_list_engines",
                description="列出 AOS 所有已注册引擎的实时状态：live/dead、声明的能力、是否隔离进子进程、隔离观测(子进程PID/热备就绪/三闸门)。对应 FabricHub.health_report()。",
                input_schema={"type": "object", "properties": {}},
            ),
            self._aos_list_engines_handler,
        )
        self.register_tool(
            MCPTool(
                name="aos_route",
                description="按能力(capability)把任务委派给首个 live 引擎，如 inference.llm→agnes/litellm, media.image→agnes, memory.semantic→mem0。对应 FabricHub.route()。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "capability": {"type": "string", "description": "能力标识，如 inference.llm / media.image / memory.semantic / group.orchestration"},
                        "payload": {"type": "object", "description": "传给引擎的参数(dict)"},
                    },
                    "required": ["capability"],
                },
            ),
            self._aos_route_handler,
        )
        self.register_tool(
            MCPTool(
                name="aos_invoke_engine",
                description="直接打指定引擎(按 engine_id)，绕过能力路由的「首个 live」选择。隔离引擎走子进程，进程内引擎走 registry。对应 FabricHub.invoke_engine()。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "engine_id": {"type": "string", "description": "引擎 id，如 agnes / ag2 / litellm / mem0 / openclaw"},
                        "capability": {"type": "string", "description": "能力标识", "default": "inference.llm"},
                        "payload": {"type": "object", "description": "传给引擎的参数(dict)"},
                    },
                    "required": ["engine_id"],
                },
            ),
            self._aos_invoke_engine_handler,
        )
        self.register_tool(
            MCPTool(
                name="aos_run_task",
                description="自主执行闭环：把一句话任务交给 AOS 规划→编排执行。优先用 AG2/cognition.planning 产出计划并解析成 steps，失败降级本地 heuristic；再经 OrchestrationChiplet 逐跳调度隔离引擎。对应 FabricHub.run_task()。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "一句话任务，如『搜索周末天气并画一张示意图』"},
                        "planner": {"type": "string", "description": "planner 模式：ag2(默认,尝试用规划引擎,失败降级 heuristic) / heuristic(纯本地,不调外部 LLM)", "default": "ag2"},
                    },
                    "required": ["task"],
                },
            ),
            self._aos_run_task_handler,
        )


    def _openclaw_handler(self, params: Dict[str, Any]) -> Any:
        """通过真实部署的 OpenClaw Gateway 调用 OpenClaw (Fabric OpenClawAdapter)。

        自研 OpenClawSubAgent 已于 #98 删除(违反"用真实开源"铁律); 此处改为
        经真实 OpenClaw Gateway(:18789) 服务, 与 brain 的 fabric 收编保持一致。
        若网关未启动, 优雅降级返回 error 而不崩溃。
        """
        try:
            from core.fabric.adapters.openclaw_adapter import OpenClawAdapter
            from core.fabric.capability import Capability
            from core.fabric.adapter import InvokeRequest
        except Exception as e:
            return {"success": False, "error": f"OpenClawAdapter 不可用: {e}"}

        try:
            adapter = OpenClawAdapter()
            if not adapter.health():
                return {"success": False, "error": "OpenClaw Gateway 未连接 (127.0.0.1:18789)"}
            req = InvokeRequest(
                capability=Capability.CHANNEL_ACCESS,
                payload={"text": params.get("message", "")},
            )
            res = adapter.invoke(req)
            if res.ok:
                return {"success": True, "reply": (res.data or {}).get("reply", "")}
            return {"success": False, "error": res.error}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _uitars_handler(self, params: Dict[str, Any]) -> Any:
        """通过子智能体注册中心调用 UI-TARS."""
        if self._subagent_registry:
            return self._subagent_registry.invoke("uitars", params)
        return {"error": "子智能体注册中心未初始化"}

    def _lobster_handler(self, params: Dict[str, Any]) -> Any:
        """通过子智能体注册中心调用 LobsterAI."""
        if self._subagent_registry:
            return self._subagent_registry.invoke("lobster", params)
        return {"error": "子智能体注册中心未初始化"}

    def _default_chat_handler(self, params: Dict[str, Any]) -> Any:
        return {"message": "聊天功能需要连接HermesAgent", "params_received": params}

    def _default_search_handler(self, params: Dict[str, Any]) -> Any:
        return {"message": "搜索功能需要连接MemoryManager", "params_received": params}

    def _default_status_handler(self, params: Dict[str, Any]) -> Any:
        return {
            "server": self.server_name,
            "version": self.server_version,
            "protocol_version": self.protocol_version,
            "initialized": self.initialized,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
            "timestamp": datetime.now().isoformat(),
        }

    # ---- FabricHub 能力路由 handlers（B 路线成果对外暴露）----
    def _aos_list_engines_handler(self, params: Dict[str, Any]) -> Any:
        """列出 AOS 引擎实时状态（对应 FabricHub.health_report）。"""
        try:
            hub = _get_hub()
            return hub.health_report()
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"AOS fabric 不可用: {e}"}

    def _aos_route_handler(self, params: Dict[str, Any]) -> Any:
        """按能力路由（对应 FabricHub.route）。"""
        capability = params.get("capability")
        payload = params.get("payload") or {}
        if not capability:
            return {"ok": False, "error": "capability 参数必填"}
        try:
            hub = _get_hub()
            res = hub.route(capability, payload)
            return {"ok": res.ok, "data": res.data, "error": res.error}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def _aos_invoke_engine_handler(self, params: Dict[str, Any]) -> Any:
        """直接打指定引擎（对应 FabricHub.invoke_engine）。"""
        engine_id = params.get("engine_id")
        capability = params.get("capability") or "inference.llm"
        payload = params.get("payload") or {}
        if not engine_id:
            return {"ok": False, "error": "engine_id 参数必填"}
        try:
            hub = _get_hub()
            res = hub.invoke_engine(engine_id, capability, payload)
            return {"ok": res.ok, "data": res.data, "error": res.error}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def _aos_run_task_handler(self, params: Dict[str, Any]) -> Any:
        """自主执行闭环（对应 FabricHub.run_task）。"""
        task = params.get("task")
        planner = params.get("planner") or "ag2"
        if not task:
            return {"ok": False, "error": "task 参数必填"}
        try:
            hub = _get_hub()
            return hub.run_task(task, planner=planner)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def set_subagent_registry(self, registry):
        """设置子智能体注册中心引用."""
        self._subagent_registry = registry
        logger.info("MCP协议层已绑定子智能体注册中心")

    def register_tool(self, tool: MCPTool, handler: Callable):
        self.tools[tool.name] = tool
        self.tool_handlers[tool.name] = handler

    def register_resource(self, resource: MCPResource, handler: Optional[Callable] = None):
        self.resources[resource.uri] = resource
        if handler:
            self.resource_handlers[resource.uri] = handler

    def register_prompt(self, prompt: MCPPrompt, handler: Optional[Callable] = None):
        self.prompts[prompt.name] = prompt
        if handler:
            self.prompt_handlers[prompt.name] = handler

    def handle_message(self, message: MCPMessage) -> MCPMessage:
        if message.error:
            logger.error(f"收到错误消息: {message.error}")
            return message

        if not message.method:
            return self._create_error_response(message.id, MCPErrorCode.INVALID_REQUEST, "缺少method字段")

        method = message.method
        params = message.params or {}

        if method != MCPMethod.INITIALIZE.value and not self.initialized:
            return self._create_error_response(message.id, MCPErrorCode.SERVER_NOT_INITIALIZED, "服务器未初始化")

        handlers = {
            MCPMethod.INITIALIZE.value: self._handle_initialize,
            MCPMethod.PING.value: self._handle_ping,
            MCPMethod.TOOLS_LIST.value: self._handle_tools_list,
            MCPMethod.TOOLS_CALL.value: self._handle_tools_call,
            MCPMethod.RESOURCES_LIST.value: self._handle_resources_list,
            MCPMethod.RESOURCES_READ.value: self._handle_resources_read,
            MCPMethod.PROMPTS_LIST.value: self._handle_prompts_list,
            MCPMethod.PROMPTS_GET.value: self._handle_prompts_get,
            MCPMethod.SHUTDOWN.value: self._handle_shutdown,
        }

        handler = handlers.get(method)
        if not handler:
            return self._create_error_response(message.id, MCPErrorCode.METHOD_NOT_FOUND, f"方法未找到: {method}")

        try:
            result = handler(params)
            return MCPMessage(id=message.id, result=result)
        except Exception as e:
            logger.error(f"处理方法 {method} 失败: {e}", exc_info=True)
            return self._create_error_response(message.id, MCPErrorCode.INTERNAL_ERROR, str(e))

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        client_protocol_version = params.get("protocolVersion", self.protocol_version)
        self.initialized = True
        logger.info(f"MCP客户端连接，协议版本: {client_protocol_version}")
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
                "logging": {},
            },
            "serverInfo": {
                "name": self.server_name,
                "version": self.server_version,
            },
        }

    def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"tools": [t.to_dict() for t in self.tools.values()]}

    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name or tool_name not in self.tools:
            return self._create_error_result(MCPErrorCode.UNKNOWN_TOOL, f"未知工具: {tool_name}")

        handler = self.tool_handlers.get(tool_name)
        if not handler:
            return self._create_error_result(MCPErrorCode.INTERNAL_ERROR, f"工具 {tool_name} 没有处理器")

        try:
            result = handler(arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, default=str),
                    }
                ],
                "isError": False,
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            }

    def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"resources": [r.to_dict() for r in self.resources.values()]}

    def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not uri or uri not in self.resources:
            return self._create_error_result(MCPErrorCode.UNKNOWN_RESOURCE, f"未知资源: {uri}")
        handler = self.resource_handlers.get(uri)
        if handler:
            content = handler(params)
        else:
            content = f"资源: {uri}"
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": self.resources[uri].mime_type,
                    "text": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
                }
            ]
        }

    def _handle_prompts_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"prompts": [p.to_dict() for p in self.prompts.values()]}

    def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        if not name or name not in self.prompts:
            return self._create_error_result(MCPErrorCode.INVALID_PARAMS, f"未知提示: {name}")
        handler = self.prompt_handlers.get(name)
        if handler:
            messages = handler(params.get("arguments", {}))
        else:
            messages = [{"role": "user", "content": {"type": "text", "text": f"提示: {name}"}}]
        return {"messages": messages}

    def _handle_shutdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.initialized = False
        logger.info("MCP服务器关闭")
        return {"status": "shutdown"}

    def _create_error_response(self, msg_id: Optional[str], code: MCPErrorCode, message: str) -> MCPMessage:
        return MCPMessage(
            id=msg_id,
            error={
                "code": code.value,
                "message": message,
            },
        )

    def _create_error_result(self, code: MCPErrorCode, message: str) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": message}],
            "isError": True,
            "errorCode": code.value,
        }

    def get_server_info(self) -> Dict[str, Any]:
        return {
            "name": self.server_name,
            "version": self.server_version,
            "protocol_version": self.protocol_version,
            "initialized": self.initialized,
            "tools": list(self.tools.keys()),
            "resources": list(self.resources.keys()),
            "prompts": list(self.prompts.keys()),
        }


# ---------------------------------------------------------------------------
# 懒加载 FabricHub 单例（供 aos_* MCP 工具 handler 调用）
# ---------------------------------------------------------------------------
_HUB_LOCK = threading.Lock()
_HUB = None


def _load_dotenv_best_effort() -> None:
    """best-effort 加载仓库根 .env（含真实 API key），不覆盖已有 env 变量。

    与 scripts/fabric_scorecard.py 的 _load_env 同口径：拿不到就退回 keyless
    结构检查，绝不抛。使真机 route 到 agnes/ag2 能拿到真实 key 返回内容。
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        env_path = os.path.join(root, ".env")
        if not os.path.exists(env_path):
            return
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


def _get_hub():
    """懒加载并缓存 FabricHub 单例（带隔离接线，与 scorecard 生产接线一致）。

    - 首次调用才 build：MCP client 的 initialize/tools/list 不触发，秒回；
      首次 tools/call 到 aos_* 才真正 spawn 隔离引擎(agnes/ag2)。
    - build 期把 stdout 重定向到 stderr，屏蔽隔离层 [iso] 打印，确保 MCP
      流纯净（不影响 scorecard——它不重定向，用户仍能在那看到 [iso]）。
    - best-effort 加载仓库根 .env 的 API key（不覆盖已有 env），使真机
      route 到 agnes/ag2 能拿到真实 key 返回内容。
    """
    global _HUB
    if _HUB is not None:
        return _HUB
    with _HUB_LOCK:
        if _HUB is None:
            _load_dotenv_best_effort()
            with contextlib.redirect_stdout(sys.stderr):
                from kernel.wiring import build_fabric_hub
                _HUB = build_fabric_hub(isolate_heavy=True)
        return _HUB
