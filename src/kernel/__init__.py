"""AOS 极简内核包（v1.0 物种思维合约层）。

本包零依赖：只使用标准库。任何具体实现（litellm / 四个真实 OSS / MCP）
都是"插件"，由外部接线层经三个 ABC 登记进来，内核从不 hardcode 它们。

公开 API（惰性导入）：
- AOSKernel              极简内核（生命周期 / 路由 / 权限）
- ModelGateway / AgentRuntime / SkillBus   三大可替换层抽象接口
- 版本化系统（ModuleVersion / VersionRegistry / UpgradeManager / Migration）
- 事件系统（Event / EventBus / EventEmitter / SystemEvent）
- 值类型（AgentSpec / AgentInstance / Message / Response / ...）

惰性导入：原先此处急切导入 55 个符号（来自 10 个子模块），任何
`import kernel` 都会把整套子模块一次性拉入，拖慢轻量使用者。
改为 `__getattr__` 模式：仅在真正访问 `kernel.X` / `from kernel import X`
时才加载对应子模块，行为与之前完全一致，但消除了导入期耦合。
（审计 P1#9：套用 core/__init__.py 的 __getattr__ 模式）
"""

import importlib

# (公开名 -> (子模块, 属性名))。
# 注意：ComplianceLayer 在 .compliance 与 .future 中都有定义，原急切导入时
# .future 行在 .compliance 之后，故最终绑定到 .future；此处须保持同一优先级。
_LAZY_IMPORTS = {
    "AuthBridge": (".auth_bridge", "AuthBridge"),
    "AuthProvider": (".auth_bridge", "AuthProvider"),
    "AuthResult": (".auth_bridge", "AuthResult"),
    "AuditEntry": (".compliance", "AuditEntry"),
    "AuditTrail": (".compliance", "AuditTrail"),
    "ContentGuard": (".compliance", "ContentGuard"),
    "PolicyEngine": (".compliance", "PolicyEngine"),
    "PolicyRule": (".compliance", "PolicyRule"),
    "NaturalSelection": (".ecology", "NaturalSelection"),
    "ResourceBudget": (".ecology", "ResourceBudget"),
    "ResourceEconomy": (".ecology", "ResourceEconomy"),
    "SymbiosisDetector": (".ecology", "SymbiosisDetector"),
    "Event": (".events", "Event"),
    "EventBus": (".events", "EventBus"),
    "EventEmitter": (".events", "EventEmitter"),
    "SystemEvent": (".events", "SystemEvent"),
    "AgentDNA": (".evolution", "AgentDNA"),
    "Breeder": (".evolution", "Breeder"),
    "FitnessScore": (".evolution", "FitnessScore"),
    "FitnessTracker": (".evolution", "FitnessTracker"),
    "Gene": (".evolution", "Gene"),
    "ComplianceLayer": (".future", "ComplianceLayer"),
    "ModelCapabilityExt": (".future", "ModelCapabilityExt"),
    "ModelCapabilityProvider": (".future", "ModelCapabilityProvider"),
    "ProtocolAdapter": (".future", "ProtocolAdapter"),
    "ArbitrationResponse": (".hippo_scroll", "ArbitrationResponse"),
    "CognitionNode": (".hippo_scroll", "CognitionNode"),
    "CognitionTrack": (".hippo_scroll", "CognitionTrack"),
    "Confidence": (".hippo_scroll", "Confidence"),
    "EvidenceAnchor": (".hippo_scroll", "EvidenceAnchor"),
    "EvidenceTrack": (".hippo_scroll", "EvidenceTrack"),
    "HippoScrollEngine": (".hippo_scroll", "HippoScrollEngine"),
    "MetacognitivePatrol": (".hippo_scroll", "MetacognitivePatrol"),
    "Modality": (".hippo_scroll", "Modality"),
    "PatrolFinding": (".hippo_scroll", "PatrolFinding"),
    "PyramidRetriever": (".hippo_scroll", "PyramidRetriever"),
    "HotSwapManager": (".hotswap", "HotSwapManager"),
    "AnomalyDetector": (".immunity", "AnomalyDetector"),
    "CircuitBreaker": (".immunity", "CircuitBreaker"),
    "CircuitBreakerOpenError": (".immunity", "CircuitBreakerOpenError"),
    "SelfHealer": (".immunity", "SelfHealer"),
    "AgentRuntime": (".interfaces", "AgentRuntime"),
    "ModelGateway": (".interfaces", "ModelGateway"),
    "SkillBus": (".interfaces", "SkillBus"),
    "AOSKernel": (".kernel", "AOSKernel"),
    "AgentInstance": (".types", "AgentInstance"),
    "AgentSpec": (".types", "AgentSpec"),
    "AgentStatus": (".types", "AgentStatus"),
    "ChatChunk": (".types", "ChatChunk"),
    "ChatResponse": (".types", "ChatResponse"),
    "Message": (".types", "Message"),
    "ModelCapabilities": (".types", "ModelCapabilities"),
    "ModelInfo": (".types", "ModelInfo"),
    "Permission": (".types", "Permission"),
    "Response": (".types", "Response"),
    "SkillInfo": (".types", "SkillInfo"),
    "SkillResult": (".types", "SkillResult"),
    "SkillSpec": (".types", "SkillSpec"),
    "Migration": (".versioning", "Migration"),
    "ModuleVersion": (".versioning", "ModuleVersion"),
    "UpgradeManager": (".versioning", "UpgradeManager"),
    "VersionRegistry": (".versioning", "VersionRegistry"),
    "VersionedPlugin": (".versioning", "VersionedPlugin"),
    # 自主环
    "autopilot": ("kernel.autopilot", "run"),
    "aos": ("kernel.aos", "run_task"),
    # 工作流
    "workflow_engine": ("kernel.workflow_engine", "WorkflowEngine"),
    # 记忆
    "hippo_scroll": ("kernel.hippo_scroll", "HippoScrollEngine"),
    "memory_compression": ("kernel.memory_compression", "MemoryCompressor"),
    "memory_distiller": ("kernel.memory_distiller", "MemoryDistiller"),
    "memory_lifecycle": ("kernel.memory_lifecycle", "MemoryLifecycleBridge"),
    # 安全
    "compliance": ("kernel.compliance", "AuditTrail"),
    "auth_bridge": ("kernel.auth_bridge", "AuthBridge"),
    # 进化
    "evolution_distiller": ("kernel.evolution_distiller", "EvolutionDistiller"),
    "learning_loop": ("kernel.learning_loop", "LearningLoop"),
    # 桥接
    "v5_bridge": ("kernel.v5_bridge", "ChatBridge"),
    "skills_bridge": ("kernel.skills_bridge", "SkillsBridge"),
    # 可观测
    "semantic_state": ("kernel.semantic_state", "SEMANTIC_LOCK"),
    # 无人区新模块
    "causal_experiment": ("kernel.causal_experiment", "CausalExperimentEngine"),
    "evidence_chain": ("kernel.evidence_chain", "EvidenceChainBuilder"),
    "experience_sharing": ("kernel.experience_sharing", "ExperienceSharingEngine"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_name, attr = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_name, __name__)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
