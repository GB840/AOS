"""L6 虚实交互闭环层 —— 生命体与真实世界之间的三道关口（生命体OS 白皮书 L6）。

子模块：
- perception_gateway  感知数据流网关（进：限流/去重/脱敏/防注入/定信/分发）
- human_causal_sim    人本因果仿真（判：行动落到人身上的六维影响 + 反事实对照）
- emergency_brake     故障紧急制动总线（停：三级全局急停，锁存，HARD 以上人工解除）

三者构成"进—判—停"的完整闭环：
    外界 → [网关] → 内核决策 → [人本仿真] → 行动 → 异常 → [急停] → 全体停手

注：L6A 生成式界面 / L6B 3D 在场感 / L6C 内容产出 / L6D 语音全双工 属 🔧复用，
分别落在 `core/fabric/a2ui.py`、`companion.py`、`media_gen_adapter.py`、`voice_chiplet.py`，
本包不重复造（选型铁律：现有够好就复用）。行动仲裁在 `kernel/action_arbiter.py`。

诚实度：② 单元验证（tests/test_interact_layer.py）；接真实感知流/物理执行为 ③ 待验。
"""

from .perception_gateway import (
    PerceptionGateway, Percept, IngestResult, TRUST_TIERS,
    redact, detect_injection,
    ACCEPTED, RATE_LIMITED, DUPLICATE, QUARANTINED,
)
from .human_causal_sim import (
    HumanCausalSimulator, HumanImpact, CausalEdge,
    DIMENSIONS, DIM_WEIGHTS, ALLOW, NEEDS_APPROVAL, DENY,
    DIM_TIME, DIM_ATTENTION, DIM_EMOTION, DIM_MONEY, DIM_RELATION, DIM_AUTONOMY,
)
from .emergency_brake import (
    EmergencyBrake, BrakeEvent, BrakeEngaged, get_brake, reset_brake,
    NONE, SOFT, HARD, FULL, LEVEL_NAMES,
    ACT_READ, ACT_INTERNAL, ACT_EXTERNAL, ACT_CRITICAL, ACT_SPAWN, ACT_IRREVERSIBLE,
)

__all__ = [
    "PerceptionGateway", "Percept", "IngestResult", "TRUST_TIERS",
    "redact", "detect_injection",
    "ACCEPTED", "RATE_LIMITED", "DUPLICATE", "QUARANTINED",
    "HumanCausalSimulator", "HumanImpact", "CausalEdge",
    "DIMENSIONS", "DIM_WEIGHTS", "ALLOW", "NEEDS_APPROVAL", "DENY",
    "DIM_TIME", "DIM_ATTENTION", "DIM_EMOTION", "DIM_MONEY", "DIM_RELATION", "DIM_AUTONOMY",
    "EmergencyBrake", "BrakeEvent", "BrakeEngaged", "get_brake", "reset_brake",
    "NONE", "SOFT", "HARD", "FULL", "LEVEL_NAMES",
    "ACT_READ", "ACT_INTERNAL", "ACT_EXTERNAL", "ACT_CRITICAL",
    "ACT_SPAWN", "ACT_IRREVERSIBLE",
]
