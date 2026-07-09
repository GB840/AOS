"""
AOS v5.0 — ORM 模型聚合

导入本模块即把全部 42 张表注册进 SQLModel.metadata。
分四层 + 基础设施:
  基础设施 13 + 生态 10 + 进化 10 + 经济 5 + 免疫 4 = 42
  (基础设施新增: notifications / event_store / snapshots / cold_memories)
"""

from core.database.models.economy import (
    BudgetPool,
    CostAccounting,
    EconomicTransaction,
    RewardEvent,
    TokenLedger,
)
from core.database.models.ecosystem import (
    AgencyRole,
    AgentCard,
    CapabilityRegistry,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    McpConnector,
    Skill,
    SkillVersion,
    SubagentRegistry,
    ToolRegistry,
)
from core.database.models.evolution import (
    EvolutionLog,
    LearningExperience,
    ModelRoutingHistory,
    NegotiationSession,
    OrchestrationSpec,
    PerformanceMetric,
    PromptTemplate,
    SelfModificationProposal,
    TaskFingerprint,
    WorkflowDefinition,
)
from core.database.models.immune import (
    ComplianceRecord,
    IdentityVault,
    SandboxPolicy,
    SemanticFirewallRule,
)
from core.database.models.infra import (
    Agent,
    AuditLog,
    Checkpoint,
    ColdMemory,
    Conversation,
    EventStore,
    Knowledge,
    Message,
    Notification,
    Snapshot,
    Task,
    Thread,
    User,
)

# 全量表类清单 (供测试/迁移使用)
ALL_MODELS = [
    User, Agent, Thread, Message, Checkpoint, Conversation, Knowledge, Task, AuditLog,
    Notification, EventStore, Snapshot, ColdMemory,
    Skill, SkillVersion, ToolRegistry, McpConnector, AgentCard, SubagentRegistry,
    KnowledgeGraphNode, KnowledgeGraphEdge, AgencyRole, CapabilityRegistry,
    TaskFingerprint, OrchestrationSpec, WorkflowDefinition, EvolutionLog,
    LearningExperience, ModelRoutingHistory, PerformanceMetric, PromptTemplate,
    NegotiationSession, SelfModificationProposal,
    TokenLedger, CostAccounting, RewardEvent, BudgetPool, EconomicTransaction,
    ComplianceRecord, IdentityVault, SemanticFirewallRule, SandboxPolicy,
]

TABLE_COUNT = len(ALL_MODELS)

__all__ = [m.__name__ for m in ALL_MODELS] + ["ALL_MODELS", "TABLE_COUNT"]
