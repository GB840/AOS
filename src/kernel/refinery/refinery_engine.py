"""炼化总控引擎（Code Refinery Engine）。

编排五层炼化流程，提供一站式项目代码炼化服务：
1. 加载项目到沙箱
2. 代码质量分析
3. 生成优化提案
4. 应用低风险优化
5. 运行测试验证
6. 生成炼化报告

设计原则：
- 端到端自动化，一键炼化
- 每步都有快照，随时可回滚
- 风险分级，低风险自动处理，高风险需审批
- 结构化报告，可机读可展示
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project_sandbox import ProjectSandbox, SandboxSnapshot
from .code_analyzer import CodeAnalyzer, CodeQualityReport
from .code_optimizer import CodeOptimizer, OptimizationProposal
from .test_runner import TestRunner, TestResult

logger = logging.getLogger(__name__)


@dataclass
class RefineryTask:
    """一个炼化任务。"""
    id: str
    project_root: str
    status: str = "pending"  # pending / analyzing / optimizing / testing / completed / failed
    description: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""

    # 各阶段结果
    initial_analysis: Optional[Dict[str, Any]] = None
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    applied_proposals: List[str] = field(default_factory=list)
    test_results: Optional[Dict[str, Any]] = None
    final_analysis: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_root": self.project_root,
            "status": self.status,
            "description": self.description,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round((self.completed_at - self.started_at) * 1000, 1)
            if self.completed_at else 0.0,
            "error": self.error,
            "has_initial_analysis": self.initial_analysis is not None,
            "proposal_count": len(self.proposals),
            "applied_count": len(self.applied_proposals),
            "has_test_results": self.test_results is not None,
            "has_final_analysis": self.final_analysis is not None,
        }


@dataclass
class RefineryReport:
    """炼化完整报告。"""
    task_id: str
    status: str
    duration_ms: float = 0.0

    # 分数变化
    initial_score: float = 0.0
    final_score: float = 0.0
    score_improvement: float = 0.0

    # 问题变化
    initial_issues: int = 0
    final_issues: int = 0
    issues_fixed: int = 0

    # 优化统计
    total_proposals: int = 0
    applied_proposals: int = 0
    auto_applied: int = 0
    pending_review: int = 0

    # 测试结果
    tests_passed: int = 0
    tests_total: int = 0
    all_tests_pass: bool = False

    # 建议
    recommendations: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 1),
            "initial_score": round(self.initial_score, 1),
            "final_score": round(self.final_score, 1),
            "score_improvement": round(self.score_improvement, 1),
            "initial_issues": self.initial_issues,
            "final_issues": self.final_issues,
            "issues_fixed": self.issues_fixed,
            "total_proposals": self.total_proposals,
            "applied_proposals": self.applied_proposals,
            "auto_applied": self.auto_applied,
            "pending_review": self.pending_review,
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
            "all_tests_pass": self.all_tests_pass,
            "recommendations": self.recommendations,
            "summary": self.summary,
        }


class CodeRefineryEngine:
    """代码炼化总控引擎。

    端到端编排：分析 → 优化 → 测试 → 报告
    """

    def __init__(self):
        self._tasks: Dict[str, RefineryTask] = {}
        self._active_sandbox: Optional[ProjectSandbox] = None
        self._analyzer: Optional[CodeAnalyzer] = None
        self._optimizer: Optional[CodeOptimizer] = None
        self._test_runner: Optional[TestRunner] = None

    # ── 主入口 ──────────────────────────────────────────────────────

    def refine_project(self, project_root: str,
                       description: str = "",
                       auto_apply: bool = True,
                       run_tests: bool = True) -> Dict[str, Any]:
        """一键炼化整个项目。

        Args:
            project_root: 项目根目录（绝对路径）
            description: 任务描述
            auto_apply: 是否自动应用低风险优化
            run_tests: 是否运行测试验证

        Returns:
            炼化结果字典
        """
        import hashlib
        task_id = hashlib.sha256(
            f"{project_root}-{time.time()}".encode()
        ).hexdigest()[:12]

        task = RefineryTask(
            id=task_id,
            project_root=project_root,
            status="pending",
            description=description,
            started_at=time.time(),
        )
        self._tasks[task_id] = task

        try:
            # Step 1: 创建沙箱
            task.status = "sandboxing"
            logger.info("[%s] Step 1/5: 创建项目沙箱...", task_id)
            sandbox = ProjectSandbox(project_root=project_root, name=f"refine-{task_id}")
            result = sandbox.create()
            if not result.get("success"):
                raise RuntimeError(result.get("error", "沙箱创建失败"))
            self._active_sandbox = sandbox

            # Step 2: 初始质量分析
            task.status = "analyzing"
            logger.info("[%s] Step 2/5: 初始代码质量分析...", task_id)
            self._analyzer = CodeAnalyzer(sandbox.root)
            initial_report = self._analyzer.analyze()
            task.initial_analysis = initial_report.to_dict()
            logger.info("[%s] 初始得分: %.1f, 问题: %d",
                        task_id, initial_report.overall_score,
                        len(initial_report.issues))

            # Step 3: 生成优化提案
            task.status = "optimizing"
            logger.info("[%s] Step 3/5: 生成优化提案...", task_id)
            self._optimizer = CodeOptimizer(sandbox.root)
            proposals = self._optimizer.generate_proposals(initial_report)
            task.proposals = [p.to_dict() for p in proposals]
            logger.info("[%s] 生成 %d 条优化提案", task_id, len(proposals))

            # Step 4: 应用低风险优化
            if auto_apply:
                logger.info("[%s] Step 4/5: 应用低风险优化...", task_id)
                # 先做快照
                snap_result = sandbox.snapshot("before-optimization",
                                               "应用优化前的基线快照")
                if snap_result.get("success"):
                    apply_result = self._optimizer.apply_auto_proposals()
                    task.applied_proposals = [
                        r.get("proposal_id", "") for r in apply_result.get("results", [])
                        if r.get("success")
                    ]
                    logger.info("[%s] 已应用 %d / %d 条自动优化",
                                task_id, apply_result.get("applied", 0),
                                apply_result.get("total", 0))
                else:
                    logger.warning("[%s] 快照失败，跳过自动优化", task_id)
            else:
                logger.info("[%s] Step 4/5: 跳过自动优化（需手动审批）", task_id)

            # Step 5: 测试验证
            if run_tests:
                task.status = "testing"
                logger.info("[%s] Step 5/5: 运行测试验证...", task_id)
                # 尝试找 tests 目录（可能在项目根或 src 下）
                test_dir = self._find_test_dir(sandbox.root)
                self._test_runner = TestRunner(sandbox.root)
                if test_dir:
                    test_result = self._test_runner.run_all(test_dir=test_dir)
                    task.test_results = test_result
                    logger.info("[%s] 测试: %d/%d 通过",
                                task_id, test_result.get("passed", 0),
                                test_result.get("total_tests", 0))
                else:
                    task.test_results = {"success": True, "note": "未找到测试目录",
                                         "total_tests": 0, "passed": 0}
                    logger.info("[%s] 未找到测试目录，跳过测试", task_id)
            else:
                logger.info("[%s] Step 5/5: 跳过测试", task_id)

            # 最终分析
            if self._optimizer and self._optimizer.proposals:
                final_analyzer = CodeAnalyzer(sandbox.root)
                final_report = final_analyzer.analyze()
                task.final_analysis = final_report.to_dict()

            # 完成
            task.status = "completed"
            task.completed_at = time.time()
            logger.info("[%s] 炼化完成！", task_id)

            # 生成报告
            report = self._generate_report(task)
            return {
                "success": True,
                "task": task.to_dict(),
                "report": report.to_dict(),
                "sandbox_path": sandbox.root,
            }

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
            logger.error("[%s] 炼化失败: %s", task_id, e, exc_info=True)
            return {
                "success": False,
                "task": task.to_dict(),
                "error": str(e),
            }

    # ── 分阶段方法 ──────────────────────────────────────────────────

    def create_task(self, project_root: str,
                    description: str = "") -> Dict[str, Any]:
        """创建炼化任务（分阶段执行用）。"""
        import hashlib
        task_id = hashlib.sha256(
            f"{project_root}-{time.time()}".encode()
        ).hexdigest()[:12]

        task = RefineryTask(
            id=task_id,
            project_root=project_root,
            status="pending",
            description=description,
            started_at=time.time(),
        )
        self._tasks[task_id] = task
        return {"success": True, "task_id": task_id, "task": task.to_dict()}

    def analyze(self, task_id: str) -> Dict[str, Any]:
        """执行分析阶段。"""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        try:
            task.status = "sandboxing"
            sandbox = ProjectSandbox(project_root=task.project_root,
                                     name=f"refine-{task_id}")
            result = sandbox.create()
            if not result.get("success"):
                raise RuntimeError(result.get("error", "沙箱创建失败"))
            self._active_sandbox = sandbox

            task.status = "analyzing"
            self._analyzer = CodeAnalyzer(sandbox.root)
            report = self._analyzer.analyze()
            task.initial_analysis = report.to_dict()

            # 同时生成提案
            self._optimizer = CodeOptimizer(sandbox.root)
            proposals = self._optimizer.generate_proposals(report)
            task.proposals = [p.to_dict() for p in proposals]

            task.status = "pending_review"
            return {
                "success": True,
                "task_id": task_id,
                "analysis": report.to_dict(),
                "proposals": [p.to_dict() for p in proposals],
            }
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            return {"success": False, "error": str(e)}

    def apply_optimization(self, task_id: str,
                           proposal_ids: List[str] = None) -> Dict[str, Any]:
        """应用优化提案。"""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        if not self._optimizer or not self._active_sandbox:
            return {"success": False, "error": "请先执行分析阶段"}

        try:
            task.status = "optimizing"
            self._active_sandbox.snapshot("before-apply", "应用优化前")

            if proposal_ids:
                # 应用指定提案
                applied = []
                for pid in proposal_ids:
                    res = self._optimizer.apply_proposal(pid)
                    if res.get("success"):
                        applied.append(pid)
                task.applied_proposals = applied
            else:
                # 应用所有自动优化
                res = self._optimizer.apply_auto_proposals()
                task.applied_proposals = [
                    r.get("proposal_id", "") for r in res.get("results", [])
                    if r.get("success")
                ]

            task.status = "optimized"
            return {"success": True, "applied": len(task.applied_proposals)}
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            return {"success": False, "error": str(e)}

    def run_tests(self, task_id: str, test_dir: str = "tests") -> Dict[str, Any]:
        """运行测试。"""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        if not self._active_sandbox:
            return {"success": False, "error": "请先创建沙箱"}

        try:
            task.status = "testing"
            self._test_runner = TestRunner(self._active_sandbox.root)
            result = self._test_runner.run_all(test_dir=test_dir)
            task.test_results = result
            task.status = "tested"
            return {"success": True, "results": result}
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            return {"success": False, "error": str(e)}

    def finalize(self, task_id: str) -> Dict[str, Any]:
        """完成任务，生成最终报告。"""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        if not self._active_sandbox:
            return {"success": False, "error": "请先创建沙箱"}

        try:
            # 最终分析
            final_analyzer = CodeAnalyzer(self._active_sandbox.root)
            final_report = final_analyzer.analyze()
            task.final_analysis = final_report.to_dict()

            task.status = "completed"
            task.completed_at = time.time()

            report = self._generate_report(task)
            return {
                "success": True,
                "task": task.to_dict(),
                "report": report.to_dict(),
            }
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            return {"success": False, "error": str(e)}

    def rollback(self, task_id: str, snapshot_name: str) -> Dict[str, Any]:
        """回滚到指定快照。"""
        if not self._active_sandbox:
            return {"success": False, "error": "无活动沙箱"}

        # 找快照
        snaps = self._active_sandbox.list_snapshots()
        if not snaps.get("success"):
            return snaps

        target = None
        for s in snaps.get("snapshots", []):
            if s.get("name") == snapshot_name or s.get("id") == snapshot_name:
                target = s.get("id")
                break

        if not target:
            return {"success": False, "error": f"快照不存在: {snapshot_name}"}

        return self._active_sandbox.rollback(target)

    def get_task(self, task_id: str) -> Optional[RefineryTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in sorted(
            self._tasks.values(), key=lambda t: t.started_at, reverse=True
        )]

    # ── 内部方法 ────────────────────────────────────────────────────

    @staticmethod
    def _find_test_dir(root: Path) -> Optional[str]:
        """查找测试目录。"""
        candidates = ["tests", "test", "src/tests", "src/test"]
        for c in candidates:
            if (root / c).is_dir():
                return c
        return None

    @staticmethod
    def _generate_report(task: RefineryTask) -> RefineryReport:
        """生成炼化报告。"""
        report = RefineryReport(
            task_id=task.id,
            status=task.status,
            duration_ms=(task.completed_at - task.started_at) * 1000
            if task.completed_at else 0.0,
        )

        # 初始分析
        if task.initial_analysis:
            report.initial_score = task.initial_analysis.get("overall_score", 0)
            report.initial_issues = task.initial_analysis.get("issue_count", 0)

        # 最终分析
        if task.final_analysis:
            report.final_score = task.final_analysis.get("overall_score", 0)
            report.final_issues = task.final_analysis.get("issue_count", 0)
            report.score_improvement = report.final_score - report.initial_score
            report.issues_fixed = report.initial_issues - report.final_issues

        # 提案统计
        report.total_proposals = len(task.proposals)
        report.applied_proposals = len(task.applied_proposals)
        report.auto_applied = sum(1 for p in task.proposals
                                   if p.get("status") == "applied"
                                   and p.get("auto_applicable"))
        report.pending_review = sum(1 for p in task.proposals
                                    if p.get("status") in ("proposed", "approved")
                                    and not p.get("auto_applicable"))

        # 测试
        if task.test_results:
            report.tests_total = task.test_results.get("total_tests", 0)
            report.tests_passed = task.test_results.get("passed", 0)
            report.all_tests_pass = task.test_results.get("success", False)

        # 建议
        recommendations = []
        if report.pending_review > 0:
            recommendations.append(
                f"有 {report.pending_review} 条中高风险优化提案待审批"
            )
        if not report.all_tests_pass and report.tests_total > 0:
            recommendations.append(
                f"有 {report.tests_total - report.tests_passed} 个测试未通过，需排查"
            )
        if report.score_improvement < 5 and report.initial_score < 80:
            recommendations.append("代码质量提升空间较大，建议考虑架构级重构")
        if report.initial_score >= 90:
            recommendations.append("代码质量优良，继续保持！")
        report.recommendations = recommendations

        # 总结
        lines = [
            f"炼化任务 {task.id} {task.status}",
            f"代码质量: {report.initial_score:.1f} → {report.final_score:.1f} "
            f"({'+' if report.score_improvement >= 0 else ''}{report.score_improvement:.1f})",
            f"问题修复: {report.issues_fixed} / {report.initial_issues}",
            f"优化提案: 共 {report.total_proposals} 条，已应用 {report.applied_proposals} 条",
        ]
        if report.tests_total > 0:
            lines.append(f"测试: {report.tests_passed}/{report.tests_total} 通过")
        report.summary = "\n".join(lines)

        return report
