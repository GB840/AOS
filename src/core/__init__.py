"""
core 包初始化 (惰性导入)

原先此处急切导入 brain / task_classifier 等 6 个重模块,任何 `import core.xxx`
都会被拖入 brain 的整套依赖 (skills/yaml/...),导致 core.database 这类轻量子模块
也无法独立使用。

改为惰性导入: 仅在真正访问 `core.UnifiedBrain` / `from core import ...` 时才加载
对应子模块。行为与之前完全一致,但消除了导入期耦合。
"""

import importlib

_LAZY_IMPORTS = {
    "UnifiedBrain": (".brain", "UnifiedBrain"),
    "get_brain": (".brain", "get_brain"),
    "TaskClassifier": (".task_classifier", "TaskClassifier"),
    "TaskLevel": (".task_classifier", "TaskLevel"),
    "TaskChannel": (".task_classifier", "TaskChannel"),
    "TaskClassification": (".task_classifier", "TaskClassification"),
    "MetaDebate": (".meta_debate", "MetaDebate"),
    "DebateResult": (".meta_debate", "DebateResult"),
    "RoleCandidate": (".meta_debate", "RoleCandidate"),
    "ModelTier": (".meta_debate", "ModelTier"),
    "LEMONOrchestrator": (".lemon_orchestrator", "LEMONOrchestrator"),
    "OrchestrationSpec": (".lemon_orchestrator", "OrchestrationSpec"),
    "OrchestrationStep": (".lemon_orchestrator", "OrchestrationStep"),
    "SwarmFlow": (".swarm_flow", "SwarmFlow"),
    "WorkflowResult": (".swarm_flow", "WorkflowResult"),
    "ExecutionStatus": (".swarm_flow", "ExecutionStatus"),
    "StepStatus": (".swarm_flow", "StepStatus"),
    "TaskFingerprint": (".task_fingerprint", "TaskFingerprint"),
    "TaskTemplate": (".task_fingerprint", "TaskTemplate"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_name, attr = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_name, __name__)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
