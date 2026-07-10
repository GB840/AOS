"""AOS 极简内核包（v1.0 物种思维合约层）。

本包零依赖：只使用标准库。任何具体实现（litellm / 四个真实 OSS / MCP）
都是"插件"，由外部接线层经三个 ABC 登记进来，内核从不 hardcode 它们。

公开 API：
- AOSKernel              极简内核（生命周期 / 路由 / 权限）
- ModelGateway / AgentRuntime / SkillBus   三大可替换层抽象接口
- 版本化系统（ModuleVersion / VersionRegistry / UpgradeManager / Migration）
- 事件系统（Event / EventBus / EventEmitter / SystemEvent）
- 值类型（AgentSpec / AgentInstance / Message / Response / ...）
"""

from .auth_bridge import AuthBridge, AuthProvider, AuthResult
from .compliance import AuditEntry, AuditTrail, ComplianceLayer, ContentGuard, PolicyEngine, PolicyRule
from .ecology import NaturalSelection, ResourceBudget, ResourceEconomy, SymbiosisDetector
from .events import Event, EventBus, EventEmitter, SystemEvent
from .evolution import AgentDNA, Breeder, FitnessScore, FitnessTracker, Gene
from .future import ComplianceLayer, ModelCapabilityExt, ModelCapabilityProvider, ProtocolAdapter
from .hippo_scroll import (
    ArbitrationResponse,
    CognitionNode,
    CognitionTrack,
    Confidence,
    EvidenceAnchor,
    EvidenceTrack,
    HippoScrollEngine,
    MetacognitivePatrol,
    Modality,
    PatrolFinding,
    PyramidRetriever,
)
from .hotswap import HotSwapManager
from .immunity import AnomalyDetector, CircuitBreaker, CircuitBreakerOpenError, SelfHealer
from .interfaces import AgentRuntime, ModelGateway, SkillBus
from .kernel import AOSKernel
from .types import (
    AgentInstance,
    AgentSpec,
    AgentStatus,
    ChatChunk,
    ChatResponse,
    Message,
    ModelCapabilities,
    ModelInfo,
    Permission,
    Response,
    SkillInfo,
    SkillResult,
    SkillSpec,
)
from .versioning import (
    Migration,
    ModuleVersion,
    UpgradeManager,
    VersionRegistry,
    VersionedPlugin,
)

__all__ = [
    "AOSKernel",
    "ModelGateway", "AgentRuntime", "SkillBus",
    "AgentDNA", "AgentInstance", "AgentSpec", "AgentStatus",
    "AnomalyDetector",
    "AuthBridge", "AuthProvider", "AuthResult",
    "Breeder",
    "ChatChunk", "ChatResponse",
    "CircuitBreaker", "CircuitBreakerOpenError",
    "Event", "EventBus", "EventEmitter",
    "FitnessScore", "FitnessTracker",
    "Gene",
    "HippoScrollEngine",
    "HotSwapManager",
    "Message", "Migration",
    "ModelCapabilities", "ModelCapabilityExt", "ModelCapabilityProvider", "ModelInfo", "ModuleVersion",
    "NaturalSelection",
    "Permission",
    "ProtocolAdapter",
    "ResourceBudget", "ResourceEconomy", "Response",
    "SelfHealer",
    "SkillInfo", "SkillResult", "SkillSpec",
    "SymbiosisDetector", "SystemEvent",
    "UpgradeManager",
    "VersionRegistry", "VersionedPlugin",
]
