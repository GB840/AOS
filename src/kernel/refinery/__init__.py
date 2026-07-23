"""AOS 代码炼化系统（Code Refinery System）。

沙箱 + 全项目炼化的深度融合：
- 安全隔离：把整个项目代码库加载进沙箱，所有修改/执行都在隔离环境中进行
- 多维炼化：静态分析 → 优化建议 → 代码重构 → 测试验证 → 进化蒸馏
- 闭环进化：从每次炼化结果中学习，沉淀最佳实践，持续提升代码质量

架构分层（自下而上）：
  1. project_sandbox.py   - 项目级沙箱工作空间（安全隔离层）
  2. code_analyzer.py     - 代码分析引擎（静态分析/依赖图谱/质量评估）
  3. code_optimizer.py    - 代码优化引擎（重构/性能/安全）
  4. test_runner.py       - 测试验证引擎（单元/集成/回归）
  5. refinery_engine.py   - 炼化总控引擎（编排五层协作）
  6. evolution_loop.py    - 进化蒸馏闭环（从结果中学习）

遵循 AOS 全局约定：
- 所有外部调用经 FabricHub 统一路由
- 审计日志链式哈希防篡改
- 资源受限（超时/内存/CPU）
- 可回滚（每次修改前做快照）
"""

from .project_sandbox import ProjectSandbox, SandboxSnapshot
from .code_analyzer import CodeAnalyzer, CodeQualityReport, CodeIssue
from .code_optimizer import CodeOptimizer, OptimizationProposal
from .test_runner import TestRunner, TestResult
from .refinery_engine import CodeRefineryEngine, RefineryTask, RefineryReport
from .evolution_loop import RefineryEvolutionLoop, DistilledPattern
from .code_team import RefineryTeam
from .incremental_analyzer import IncrementalAnalyzer, IncrementalResult

__all__ = [
    "ProjectSandbox",
    "SandboxSnapshot",
    "CodeAnalyzer",
    "CodeQualityReport",
    "CodeIssue",
    "CodeOptimizer",
    "OptimizationProposal",
    "TestRunner",
    "TestResult",
    "CodeRefineryEngine",
    "RefineryTask",
    "RefineryReport",
    "RefineryEvolutionLoop",
    "DistilledPattern",
    "RefineryTeam",
    "IncrementalAnalyzer",
    "IncrementalResult",
]
