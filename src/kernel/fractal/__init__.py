"""L7 分形粒子集群：派生 + 生长约束（白皮书 L7）。

参考：plasma-ai/fractal 递归硬上限（vendor/plasma-ai-fractal，只读借鉴）。
生长约束常量硬编码（不可配置为无限），见 spawner.py / growth_guard.py。
"""
from .spawner import FractalSpawner, FractalNode, MAX_GEN, QUOTA_DECAY, MAX_SIBLINGS
from .growth_guard import GrowthGuard
from .conflict import (
    ConflictCoordinator, Lease, ArbitrationResult, ConflictEscalation,
)
from .particles import (
    ParticleType, ParticleSpec, ParticleRegistry,
    SENSOR, WORKER, GUARDIAN, ARCHIVIST,
)

__all__ = ["FractalSpawner", "FractalNode", "GrowthGuard",
           "MAX_GEN", "QUOTA_DECAY", "MAX_SIBLINGS",
           "ConflictCoordinator", "Lease", "ArbitrationResult", "ConflictEscalation",
           "ParticleType", "ParticleSpec", "ParticleRegistry",
           "SENSOR", "WORKER", "GUARDIAN", "ARCHIVIST"]
