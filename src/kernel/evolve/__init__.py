"""Evolve —— L5 演进层：自动进化引擎 + 镜像分支试错闸门。

子模块：
- evolve_engine   自动进化引擎（提示词/工作流/模型选择的数据驱动优化）
- mirror_branch   L5 镜像分支试错（影子对照 → 统计闸门 → 晋升/回滚，宪法红线否决）

诚实度：mirror_branch 为 ② 单元验证（tests/test_mirror_branch.py），真实灰度流量为 ③ 待验。
"""
from .evolve_engine import EvolveEngine, ABTest, get_evolve_engine
from .mirror_branch import (
    MirrorBranch, MirrorLab, TrialSample, GateDecision,
    ShadowLeak, BranchClosed, two_proportion_z,
    BASELINE, CANDIDATE, TRIAL, PROMOTED, ROLLED_BACK, BLOCKED,
    HOLD, PROMOTE, ROLLBACK, NEEDS_APPROVAL, CONSTITUTION_BLOCK,
)

__all__ = [
    "EvolveEngine", "ABTest", "get_evolve_engine",
    "MirrorBranch", "MirrorLab", "TrialSample", "GateDecision",
    "ShadowLeak", "BranchClosed", "two_proportion_z",
    "BASELINE", "CANDIDATE", "TRIAL", "PROMOTED", "ROLLED_BACK", "BLOCKED",
    "HOLD", "PROMOTE", "ROLLBACK", "NEEDS_APPROVAL", "CONSTITUTION_BLOCK",
]
