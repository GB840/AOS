"""AOS 内核插件包。

这里放"把现有具体实现挂到内核 ABC 上"的薄适配器。内核核心（kernel/）
零依赖；本包才允许 import 具体实现（core.fabric / mcp / litellm）。

每个插件都是一个"翻译器"：把已有的真实能力（四个 OSS / litellm / MCP）
暴露成内核认得的 AgentRuntime / ModelGateway / SkillBus 接口。
"""

from .fabric_runtime import FabricAgentRuntime
from .fabric_hub import FabricHub
from .litellm_gateway import LiteLLMModelGateway
from .mcp_skill_bus import MCPSkillBus

# 注：mistralrs / composite 需要 openai / utils.config，按需惰性导入，
# 不在包顶层强制导入以保持缺依赖时可用。
__all__ = [
    "FabricAgentRuntime",
    "FabricHub",
    "LiteLLMModelGateway",
    "MCPSkillBus",
]
