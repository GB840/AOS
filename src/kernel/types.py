"""AOS 内核值类型 — 零依赖（仅标准库）。

这些类型是所有插件（模型网关 / Agent 运行时 / 技能总线）与内核之间交换的
"通用语言"。它们不依赖任何框架、库或协议，是 v1.0「物种思维」里
"依赖倒置 + 协议优先" 的承载物：具体实现依赖这些抽象类型，而非反过来。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# 内核三职责相关的通用类型
# --------------------------------------------------------------------------

class AgentStatus(str, Enum):
    """Agent 实例的生命周期状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentSpec:
    """登记一个 Agent 所需的声明（由插件实现提供，内核只存不实现）。"""

    agent_id: str
    name: str
    engine: str                 # 对应某个已登记的 AgentRuntime 插件，如 'hermes'/'ag2'
    capabilities: List[str] = field(default_factory=list)
    version: str = "0.1.0"      # 语义化版本，支持多版本共存
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentInstance:
    """内核创建并托管的 Agent 实例（生命周期对象）。"""

    agent_id: str
    spec: AgentSpec
    status: AgentStatus = AgentStatus.PENDING
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.spec.name,
            "engine": self.spec.engine,
            "capabilities": self.spec.capabilities,
            "version": self.spec.version,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Message:
    """内核路由的最小消息单元。"""

    sender: str
    recipient: str
    payload: Dict[str, Any]
    message_id: str = field(default_factory=lambda: f"msg-{_now()}")
    timestamp: str = field(default_factory=_now)


@dataclass
class Response:
    """send_message 的返回。内核只负责路由，实际内容由运行时插件产生。"""

    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class Permission:
    """一条权限规则（内核第三职责的最小单元）。"""

    agent_id: str
    action: str
    granted: bool


# --------------------------------------------------------------------------
# 模型网关（ModelGateway）相关类型
# --------------------------------------------------------------------------

@dataclass
class ModelInfo:
    model_id: str
    provider: str
    display_name: str = ""
    version: str = "1.0.0"


@dataclass
class ChatChunk:
    """流式分片。"""

    delta: str = ""
    finish_reason: Optional[str] = None


@dataclass
class ChatResponse:
    content: str
    model: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelCapabilities:
    """模型能力声明（多模态 / 工具调用 / 上下文长度等）。"""

    context_window: int = 0
    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# 技能总线（SkillBus）相关类型
# --------------------------------------------------------------------------

@dataclass
class SkillInfo:
    skill_id: str
    description: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillSpec:
    skill_id: str
    description: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    handler: Any = None  # 可选：注册时直接挂处理函数


@dataclass
class SkillResult:
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
