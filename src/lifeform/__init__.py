"""生命体 OS 自研核心包（lifeform）。

本包承载白皮书第十一章 11.10「外部证伪项 → 自研转化」中，经穷尽搜索仍无法证实
或属编造的外部项目，其背后的架构能力由本项目完全自研落地（与宪法「核心护城河＝
完全自研」一致）。

模块映射：
- self_evolve_engine.py  ← Mobius「全球首个自进化 Agent OS」（无法证实）→ L6 个体自进化引擎
- fractal_holo_agent.py  ← Holo「分形全息 Agent · 3.02×/98.1%」（指标伪造）→ L2/L6 分形全息自适应
- world_model_engine.py  ← LeWM「1GB 显存跑 JEPA」（指标编造）→ L7 轻量因果世界模型

诚实纪律：以下均为**自研骨架（设计级 + ② 单元可测）**，非端到端跑通。
实现遵循「可验证即真理」——每个公开方法都带硬判定，不得谎报闭环。
硬上限（迭代/深度/子节点/成本/时间）借鉴 plasma-ai/fractal 的公开设计。
"""

from .self_evolve_engine import SelfEvolveEngine, EvolutionLimit
from .fractal_holo_agent import FractalHoloAgent, FractalNode
from .world_model_engine import WorldModelEngine, CausalLayer

__all__ = [
    "SelfEvolveEngine",
    "EvolutionLimit",
    "FractalHoloAgent",
    "FractalNode",
    "WorldModelEngine",
    "CausalLayer",
]
