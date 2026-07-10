"""AOS 三大可替换层抽象接口 — 零依赖（仅标准库）。

这是 v1.0「物种思维」的契约核心：
- 内核只依赖这三个 ABC，不依赖任何具体实现。
- 今天用 LiteLLM / 四个真实 OSS（AG2/Hermes/DeerFlow/OpenClaw）/ MCP，
  明天换成别的，内核一行不改 —— 只需提供新的实现并登记为插件。

接口方法签名严格对齐用户 v1.0 文档；同时，每个接口的形状都兼容现有种子：
- AgentRuntime  <- fabric.BaseAgentAdapter（engine_id/advertise/invoke/health）
- ModelGateway  <- fabric.LiteLLMAdapter（capability=LLM_GATEWAY）
- SkillBus      <- mcp.MCPProtocol（register_tool/call_tool）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List

from .types import (
    AgentInstance,
    AgentSpec,
    ChatResponse,
    ChatChunk,
    Message,
    ModelCapabilities,
    ModelInfo,
    Response,
    SkillInfo,
    SkillResult,
    SkillSpec,
)


class ModelGateway(ABC):
    """任何模型实现都必须实现这个接口（v1.0 模型网关层）。

    今天：LiteLLMAdapter 实现 -> 调本地/云端 100+ 模型
    明天：任意新模型适配器 -> 内核不改，只换实现
    """

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        ...

    @abstractmethod
    def chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> ChatResponse:
        ...

    @abstractmethod
    def stream_chat(self, model_id: str, messages: List[Message], **kwargs: Any) -> AsyncIterator[ChatChunk]:
        ...

    @abstractmethod
    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        ...


class AgentRuntime(ABC):
    """任何 Agent 编排引擎都必须实现这个接口（v1.0 Agent 运行时层）。

    今天：fabric.BaseAgentAdapter 的四个真实 OSS 实现
          （OpenClaw / Hermes / DeerFlow / AG2）
    明天：任意新框架 -> 内核不改，只换实现

    注：v1.0 文档用 create_agent/run_agent 词汇；本接口保留该高层词汇，
    同时兼容 BaseAgentAdapter 的 engine_id/advertise/invoke/health 底层契约
    —— 具体适配器可用薄封装把 invoke 映射到 run_agent。
    """

    @abstractmethod
    def create_agent(self, spec: AgentSpec) -> AgentInstance:
        ...

    @abstractmethod
    def run_agent(self, instance: AgentInstance, task: Any) -> Response:
        ...

    @abstractmethod
    def stream_run(self, instance: AgentInstance, task: Any) -> AsyncIterator[Any]:
        ...

    @abstractmethod
    def get_status(self, instance_id: str) -> str:
        ...


class SkillBus(ABC):
    """任何技能/工具协议都必须实现这个接口（v1.0 MCP 总线层）。

    今天：mcp.MCPProtocol 实现（基于 MCP 协议）
    明天：任意新协议适配器 -> 内核不改，只换实现
    """

    @abstractmethod
    def discover_skills(self) -> List[SkillInfo]:
        ...

    @abstractmethod
    def call_skill(self, skill_id: str, params: Dict[str, Any]) -> SkillResult:
        ...

    @abstractmethod
    def register_skill(self, skill_spec: SkillSpec) -> None:
        ...
