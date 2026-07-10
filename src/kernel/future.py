"""v1.0 未来扩展点预留接口。

这是 v1.0 文档"未来扩展点设计"节的代码落地：为尚未实现但有明确需求的
能力预留抽象接口签名。当前仅定义接口，不实现——未来接入时只需提供实现类，
内核不改。

当前预留：
- ProtocolAdapter: 未来 Agent 通信协议（A2A / ACP / AG-UI）
- ComplianceLayer: 未来合规审计层（GB/Z 185 / ISO 合规）
- ModelCapabilityExt: 未来模型能力扩展（多模态、工具调用增强）

所有接口零依赖（仅 ABC + dataclasses）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List


# ─── 协议适配器（A2A / ACP / AG-UI 等） ───────────────────────────

@dataclass
class ProtocolMessage:
    """协议无关的消息表示。"""
    content: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProtocolAdapter(ABC):
    """未来 Agent 通信协议适配器（A2A / ACP / AG-UI 等）。

    当前 MCP 已成为 SkillBus 的默认协议；未来有新协议出现时，
    提供继承此接口的实现类即可接入 AOS 系统，内核不改。
    """

    @abstractmethod
    def discover_agents(self) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def send(self, target_agent: str, message: ProtocolMessage) -> Dict[str, Any]:
        ...

    @abstractmethod
    def stream(self, target_agent: str, message: ProtocolMessage) -> AsyncIterator:
        ...

    @abstractmethod
    def protocol_version(self) -> str:
        ...


# ─── 合规审计层 ───────────────────────────────────────────────────

@dataclass
class AuditRecord:
    """一条合规审计记录。"""
    event_id: str
    timestamp: str
    actor: str                    # 操作主体
    action: str                   # 操作类型
    resource: str = ""            # 操作对象
    result: str = "unknown"       # "allowed" / "denied" / "error"
    detail: Dict[str, Any] = field(default_factory=dict)


class ComplianceLayer(ABC):
    """未来合规审计层（GB/Z 185 / ISO 合规等）。

    当 AOS 需要满足国家/行业合规标准时，继承此接口提供实现。
    - 审计日志写入
    - 合规规则检查（如数据不出境）
    - 合规报告生成
    """

    @abstractmethod
    def audit(self, record: AuditRecord) -> None:
        ...

    @abstractmethod
    def check_compliance(self, action: str, context: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def generate_report(self, start_time: str, end_time: str) -> Dict[str, Any]:
        ...


# ─── 模型能力扩展 ─────────────────────────────────────────────────

@dataclass
class ModelCapabilityExt:
    """模型能力扩展描述符（多模态、函数调用增强等）。"""
    model_id: str
    supports_multimodal: bool = False
    supports_function_calling: bool = False
    supports_code_interpreter: bool = False
    supports_rag: bool = False
    max_tokens: int = 0
    languages: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


class ModelCapabilityProvider(ABC):
    """未来模型能力查询扩展接口。

    当前 ModelGateway.get_capabilities 返回基础能力；
    当模型支持多模态/函数调用/代码解释器等复杂能力时，
    可继承此接口提供能力查询服务。
    """

    @abstractmethod
    def get_capabilities_ext(self, model_id: str) -> ModelCapabilityExt:
        ...

    @abstractmethod
    def filter_by_capability(self, capability: str) -> List[str]:
        ...


__all__ = [
    "AuditRecord",
    "ComplianceLayer",
    "ModelCapabilityExt",
    "ModelCapabilityProvider",
    "ProtocolAdapter",
    "ProtocolMessage",
]
