"""AOS 内核层默认实现 — v1.0 四层结构的落地点。

四个层级分别对应结构图的每一行：
  model_gateway_layer  → 模型网关层（统一调用 / 智能路由 / 成本控制）
  mcp_bus_layer        → MCP 总线层（服务发现 / 消息路由 / 权限校验）
  agent_runtime_layer  → Agent 运行时层（记忆管理 / 工作流编排 / 生命周期）
  ui_layer             → UI 层（抽象接口 + 三 UI 面：对话面板/工作台/应用商店）

每个层级只依赖 kernel ABCs + stdlib，不 import 具体实现。
它们的实例由 system.py 的 build_default_system() 统一装配。
"""

from .agent_runtime_layer import (
    AgentRuntimeLayer,
    FileMemoryManager,
    InMemoryMemoryManager,
    MemoryManager,
    WorkflowResult,
    WorkflowStep,
)
from .mcp_bus_layer import MCPBusLayer
from .model_fallback import FallbackChain, FallbackResult
from .model_gateway_layer import CostTracker, ModelGatewayLayer, RouteStrategy
from .ui_layer import CLIUILayer, SurfaceKind, UILayer, UIRender, UISurface, WebUILayer

__all__ = [
    "AgentRuntimeLayer",
    "CLIUILayer",
    "CostTracker",
    "FallbackChain",
    "FallbackResult",
    "InMemoryMemoryManager",
    "MCPBusLayer",
    "MemoryManager",
    "ModelGatewayLayer",
    "RouteStrategy",
    "SurfaceKind",
    "UILayer",
    "UIRender",
    "UISurface",
    "WebUILayer",
    "WorkflowResult",
    "WorkflowStep",
]
