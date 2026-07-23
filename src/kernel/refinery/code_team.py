"""多智能体炼化团队（Code Refinery Team）。

四个角色协作完成代码炼化，端到端编排"分析 → 方案 → 审查 → 执行"闭环：
- 架构师（ArchitectAgent）：分析架构问题（循环依赖/模块耦合/分层违规/巨型文件），产出改进建议
- 工程师（EngineerAgent）：基于建议与问题清单生成文件级优化方案，调用 CodeOptimizer 执行低风险优化
- 审查员（ReviewerAgent）：审查修改是否引入新问题（语法错误/逻辑回归），调用 TestRunner 做语法检查
- 执行者（ExecutorAgent）：协调前三者工作流，管理沙箱快照/回滚，生成最终团队报告

设计原则：
- 角色分工明确，每个角色 = 数据类（状态/结果）+ 逻辑类（行为）
- 上一角色输出逐级传递给下一角色
- 低风险自动应用，高风险经审查后再决定（保留/回滚）
- 全程快照可回滚，审查未通过自动回退到基线

典型流程：
    team = RefineryTeam(sandbox_root="/path/to/sandbox")
    result = team.run(analysis_report)  # analysis_report 为 CodeQualityReport.to_dict() 的产物
    print(result["team_report"]["summary"])
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .code_analyzer import CodeAnalyzer, CodeQualityReport, CodeIssue
from .code_optimizer import CodeOptimizer, OptimizationProposal
from .test_runner import TestRunner, TestResult

logger = logging.getLogger(__name__)

# ── 分层优先级（数值越大越底层；底层依赖顶层即视为违规）──────────────
_LAYER_PRIORITY = {
    "presentation": 0, "api": 1, "router": 1, "controller": 1, "view": 0,
    "service": 2, "application": 2, "skill": 2, "skills": 2, "agent": 2,
    "domain": 3, "model": 3, "entity": 3,
    "infrastructure": 4, "adapter": 4, "persistence": 4, "repository": 4,
    "kernel": 5, "core": 5, "refinery": 5,
}

# ── 阈值 ─────────────────────────────────────────────────────────
_HIGH_COUPLING_THRESHOLD = 5  # 单模块导入数超过此值视为高耦合
_REGRESSION_SCORE_DROP = 5.0  # 得分下降超过此值视为回归
_MAX_SNAPSHOTS = 8


# ════════════════════════════════════════════════════════════════════
# 数据类：各角色的结构化输出
# ════════════════════════════════════════════════════════════════════

@dataclass
class ArchitectSuggestion:
    """架构改进建议。"""
    id: str
    category: str  # circular_dependency / high_coupling / layering_violation / oversized_file
    severity: str  # high / medium / low
    title: str
    description: str
    affected_files: List[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EngineerPlan:
    """工程师优化方案。"""
    total_proposals: int = 0
    auto_applicable: int = 0
    manual_review: int = 0
    applied_count: int = 0
    failed_count: int = 0
    changed_files: List[str] = field(default_factory=list)
    file_actions: List[Dict[str, Any]] = field(default_factory=list)
    apply_result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewVerdict:
    """审查结论。"""
    verdict: str = "approved"  # approved / changes_requested / rejected
    syntax_ok: bool = True
    regression_detected: bool = False
    new_issue_count: int = 0
    score_delta: float = 0.0
    after_score: float = 0.0
    after_issue_count: int = 0
    syntax_checks: List[Dict[str, Any]] = field(default_factory=list)
    new_issues: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "syntax_ok": self.syntax_ok,
            "regression_detected": self.regression_detected,
            "new_issue_count": self.new_issue_count,
            "score_delta": round(self.score_delta, 2),
            "after_score": round(self.after_score, 2),
            "after_issue_count": self.after_issue_count,
            "syntax_checks": self.syntax_checks,
            "new_issues": self.new_issues,
            "risks": self.risks,
            "summary": self.summary,
        }


@dataclass
class TeamReport:
    """团队最终报告。"""
    status: str = "completed"  # completed / completed_with_warnings / rolled_back / failed
    initial_score: float = 0.0
    final_score: float = 0.0
    score_improvement: float = 0.0
    initial_issues: int = 0
    final_issues: int = 0
    issues_fixed: int = 0
    suggestions_count: int = 0
    proposals_total: int = 0
    proposals_applied: int = 0
    syntax_passed: bool = False
    rolled_back: bool = False
    snapshot_id: str = ""
    recommendations: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "initial_score": round(self.initial_score, 2),
            "final_score": round(self.final_score, 2),
            "score_improvement": round(self.score_improvement, 2),
            "initial_issues": self.initial_issues,
            "final_issues": self.final_issues,
            "issues_fixed": self.issues_fixed,
            "suggestions_count": self.suggestions_count,
            "proposals_total": self.proposals_total,
            "proposals_applied": self.proposals_applied,
            "syntax_passed": self.syntax_passed,
            "rolled_back": self.rolled_back,
            "snapshot_id": self.snapshot_id,
            "recommendations": self.recommendations,
            "summary": self.summary,
        }


# ════════════════════════════════════════════════════════════════════
# 角色 1：架构师
# ════════════════════════════════════════════════════════════════════

class ArchitectAgent:
    """架构师：分析架构问题，产出改进建议列表。

    接收 CodeQualityReport，从循环依赖、模块耦合、分层违规、巨型文件四个维度分析。
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: 沙箱根目录（绝对路径）
        """
        self._sandbox_root = sandbox_root

    def analyze(self, report: CodeQualityReport) -> List[ArchitectSuggestion]:
        """对质量报告做架构层面分析。

        Args:
            report: 代码质量报告对象

        Returns:
            架构改进建议列表
        """
        suggestions: List[ArchitectSuggestion] = []
        suggestions.extend(self._analyze_circular_deps(report))
        suggestions.extend(self._analyze_coupling(report))
        suggestions.extend(self._analyze_layering(report))
        suggestions.extend(self._analyze_oversized_files(report))

        logger.info("架构师分析完成: %d 条建议", len(suggestions))
        return suggestions

    # ── 各维度分析 ────────────────────────────────────────────────

    def _analyze_circular_deps(self, report: CodeQualityReport) -> List[ArchitectSuggestion]:
        """循环依赖分析。"""
        suggestions: List[ArchitectSuggestion] = []
        for idx, cycle in enumerate(report.circular_deps):
            chain = " → ".join(cycle) if cycle else ""
            suggestions.append(ArchitectSuggestion(
                id=f"circular-{idx:04d}",
                category="circular_dependency",
                severity="high",
                title=f"循环依赖: {chain}",
                description=f"检测到模块间形成环路：{chain} → {cycle[0] if cycle else ''}",
                affected_files=[self._module_to_file(m) for m in cycle],
                recommendation="提取公共模块或引入抽象接口，反转依赖方向打破环路",
            ))
        return suggestions

    def _analyze_coupling(self, report: CodeQualityReport) -> List[ArchitectSuggestion]:
        """模块耦合分析（基于导入数衡量扇出）。"""
        outgoing: Dict[str, int] = {}
        for dep in self._iter_dependencies(report):
            src = self._dep_source(dep)
            if not src:
                continue
            outgoing[src] = outgoing.get(src, 0) + len(self._dep_imports(dep))

        suggestions: List[ArchitectSuggestion] = []
        for idx, (mod, count) in enumerate(
                sorted(outgoing.items(), key=lambda x: -x[1])):
            if count < _HIGH_COUPLING_THRESHOLD:
                break
            suggestions.append(ArchitectSuggestion(
                id=f"couple-{idx:04d}",
                category="high_coupling",
                severity="medium",
                title=f"模块 {mod} 依赖过多（{count} 个导入）",
                description=f"模块 {mod} 直接依赖了 {count} 个外部模块，耦合度偏高，"
                            f"变更影响面较大。",
                affected_files=[self._module_to_file(mod)],
                recommendation="引入接口抽象或依赖注入，收敛对外部模块的直接依赖",
            ))
        return suggestions

    def _analyze_layering(self, report: CodeQualityReport) -> List[ArchitectSuggestion]:
        """分层违规分析（底层模块依赖顶层模块）。"""
        suggestions: List[ArchitectSuggestion] = []
        seen: set = set()
        for dep in self._iter_dependencies(report):
            src = self._dep_source(dep)
            tgt = self._dep_target(dep)
            src_layer = self._layer_of(src)
            tgt_layer = self._layer_of(tgt)
            if src_layer is None or tgt_layer is None:
                continue
            # 底层（priority 大）依赖顶层（priority 小）即违规
            if src_layer > tgt_layer:
                key = (src, tgt)
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append(ArchitectSuggestion(
                    id=f"layer-{len(suggestions):04d}",
                    category="layering_violation",
                    severity="high",
                    title=f"分层违规: {src} 依赖 {tgt}",
                    description=f"底层模块 {src}（层级 {src_layer}）依赖了上层模块 "
                                f"{tgt}（层级 {tgt_layer}），违反了依赖倒置原则。",
                    affected_files=[self._module_to_file(src), self._module_to_file(tgt)],
                    recommendation="定义抽象接口于底层，让上层依赖抽象而非具体实现",
                ))
        return suggestions

    def _analyze_oversized_files(self, report: CodeQualityReport) -> List[ArchitectSuggestion]:
        """巨型文件分析（从 issue 清单中提取）。"""
        suggestions: List[ArchitectSuggestion] = []
        seen: set = set()
        for issue in report.issues:
            if issue.rule not in ("file_too_long", "file_long"):
                continue
            if issue.file in seen:
                continue
            seen.add(issue.file)
            suggestions.append(ArchitectSuggestion(
                id=f"oversized-{len(suggestions):04d}",
                category="oversized_file",
                severity="high" if issue.severity == "high" else "medium",
                title=f"文件过大: {issue.file}",
                description=issue.message or f"文件 {issue.file} 行数过多",
                affected_files=[issue.file],
                recommendation="按职责拆分为多个高内聚、低耦合的子模块",
            ))
        return suggestions

    # ── 依赖访问工具（兼容对象/字典两种形态）──────────────────────

    @staticmethod
    def _iter_dependencies(report: CodeQualityReport) -> List[Any]:
        deps = getattr(report, "dependencies", None) or []
        return list(deps)

    @staticmethod
    def _dep_source(dep: Any) -> str:
        val = getattr(dep, "source", None)
        if val is not None:
            return str(val)
        return str(dep.get("source", "")) if isinstance(dep, dict) else ""

    @staticmethod
    def _dep_target(dep: Any) -> str:
        val = getattr(dep, "target", None)
        if val is not None:
            return str(val)
        return str(dep.get("target", "")) if isinstance(dep, dict) else ""

    @staticmethod
    def _dep_imports(dep: Any) -> List[str]:
        val = getattr(dep, "imports", None)
        if val is not None:
            return list(val)
        return list(dep.get("imports", [])) if isinstance(dep, dict) else []

    @staticmethod
    def _layer_of(module_name: str) -> Optional[int]:
        """从模块路径中推断其所属分层优先级。"""
        if not module_name:
            return None
        parts = module_name.lower().replace("-", "_").split(".")
        for part in parts:
            if part in _LAYER_PRIORITY:
                return _LAYER_PRIORITY[part]
        return None

    @staticmethod
    def _module_to_file(module: str) -> str:
        """模块名转文件路径（尽力而为，不保证存在）。"""
        if not module:
            return ""
        return module.replace(".", "/") + ".py"


# ════════════════════════════════════════════════════════════════════
# 角色 2：工程师
# ════════════════════════════════════════════════════════════════════

class EngineerAgent:
    """工程师：生成文件级优化方案并调用 CodeOptimizer 执行。

    接收架构师建议与 CodeAnalyzer 的问题清单，生成优化提案，应用低风险自动优化。
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: 沙箱根目录（绝对路径）
        """
        self._sandbox_root = sandbox_root
        self._optimizer = CodeOptimizer(sandbox_root)

    def plan_and_apply(self, report: CodeQualityReport,
                       suggestions: List[ArchitectSuggestion]) -> EngineerPlan:
        """生成方案并应用低风险自动优化。

        Args:
            report: 代码质量报告（提供 issues 给 CodeOptimizer 生成提案）
            suggestions: 架构师改进建议

        Returns:
            工程师优化方案
        """
        # 1. 基于 issue 清单生成优化提案
        proposals: List[OptimizationProposal] = self._optimizer.generate_proposals(report)
        # 2. 构建文件级行动清单（含架构师建议中尚无提案的部分）
        file_actions = self._build_file_actions(proposals, suggestions)
        # 3. 应用低风险自动优化
        apply_result = self._optimizer.apply_auto_proposals()
        # 4. 收集实际发生变更的文件
        changed_files = sorted({f for p in self._optimizer.proposals
                                if p.status == "applied" for f in p.files})

        plan = EngineerPlan(
            total_proposals=len(proposals),
            auto_applicable=sum(1 for p in proposals if p.auto_applicable),
            manual_review=sum(1 for p in proposals if not p.auto_applicable),
            applied_count=int(apply_result.get("applied", 0)),
            failed_count=int(apply_result.get("failed", 0)),
            changed_files=changed_files,
            file_actions=file_actions,
            apply_result=apply_result,
        )
        logger.info("工程师方案: 共 %d 提案，自动应用 %d，变更 %d 文件",
                    plan.total_proposals, plan.applied_count, len(changed_files))
        return plan

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _build_file_actions(proposals: List[OptimizationProposal],
                            suggestions: List[ArchitectSuggestion]) -> List[Dict[str, Any]]:
        """构建文件级行动清单。"""
        actions: List[Dict[str, Any]] = []
        proposal_files: set = set()

        for prop in proposals:
            for fp in prop.files:
                proposal_files.add(fp)
                actions.append({
                    "file": fp,
                    "proposal_id": prop.id,
                    "category": prop.category,
                    "risk_level": prop.risk_level,
                    "auto_applicable": prop.auto_applicable,
                    "title": prop.title,
                })

        # 架构师建议中尚无对应提案的文件标记为需人工重构
        for sug in suggestions:
            for fp in sug.affected_files:
                if fp and fp not in proposal_files:
                    actions.append({
                        "file": fp,
                        "proposal_id": "",
                        "category": sug.category,
                        "risk_level": sug.severity,
                        "auto_applicable": False,
                        "title": f"[需人工] {sug.title}",
                    })
        return actions


# ════════════════════════════════════════════════════════════════════
# 角色 3：审查员
# ════════════════════════════════════════════════════════════════════

class ReviewerAgent:
    """审查员：审查工程师的修改，检查语法错误与逻辑回归。

    调用 TestRunner 做语法检查，重新分析对比问题清单，判定是否引入新问题。
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: 沙箱根目录（绝对路径）
        """
        self._sandbox_root = sandbox_root
        self._test_runner = TestRunner(sandbox_root)

    def review(self, baseline_report: CodeQualityReport,
               changed_files: List[str]) -> ReviewVerdict:
        """审查工程师修改后的沙箱状态。

        Args:
            baseline_report: 工程师修改前的质量报告
            changed_files: 工程师变更的文件列表

        Returns:
            审查结论
        """
        verdict = ReviewVerdict()

        # 1. 语法检查（全量，确保整体可编译）
        syntax_result = self._test_runner.check_syntax()
        syntax_dict = self._to_dict(syntax_result)
        verdict.syntax_ok = bool(syntax_dict.get("success", False))

        # 按变更文件提取其语法检查条目（兼容路径分隔符差异）
        cases = {self._norm(c.get("name", "")): c
                 for c in syntax_dict.get("test_cases", [])}
        for fp in changed_files:
            case = cases.get(self._norm(fp))
            verdict.syntax_checks.append({
                "file": fp,
                "status": case.get("status") if case else "not_checked",
                "error": (case.get("error", "") if case else ""),
            })

        # 2. 重新分析，对比问题清单与得分
        after_report = CodeAnalyzer(self._sandbox_root).analyze()
        verdict.after_score = after_report.overall_score
        verdict.after_issue_count = len(after_report.issues)
        verdict.score_delta = after_report.overall_score - baseline_report.overall_score

        new_issues = self._diff_issues(baseline_report.issues, after_report.issues)
        verdict.new_issue_count = len(new_issues)
        verdict.new_issues = [i.to_dict() for i in new_issues[:20]]
        verdict.regression_detected = (
            verdict.new_issue_count > 0 or verdict.score_delta < -_REGRESSION_SCORE_DROP
        )

        # 3. 判定结论（仅当工程师"新引入"语法错误才判定为不可接受并触发回滚；
        #    预存的语法错误不视为工程师的过错）
        changed_set = {self._norm(f) for f in changed_files}
        new_syntax_errors = [i for i in new_issues
                            if i.rule == "syntax_error" and self._norm(i.file) in changed_set]
        if new_syntax_errors:
            verdict.verdict = "rejected"
            verdict.risks.append(
                f"工程师修改引入 {len(new_syntax_errors)} 个语法错误，需回滚"
            )
        elif verdict.regression_detected:
            verdict.verdict = "changes_requested"
            verdict.risks.append(
                f"引入 {verdict.new_issue_count} 个新问题，得分变化 "
                f"{verdict.score_delta:+.1f}，需进一步修正"
            )
        else:
            verdict.verdict = "approved"

        verdict.summary = (
            f"审查结论: {verdict.verdict} | 语法: "
            f"{'通过' if verdict.syntax_ok else '失败'} | "
            f"新问题: {verdict.new_issue_count} | "
            f"得分变化: {verdict.score_delta:+.1f}"
        )
        logger.info("审查员结论: %s (新问题=%d, 得分变化=%+.1f)",
                    verdict.verdict, verdict.new_issue_count, verdict.score_delta)
        return verdict

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _diff_issues(before: List[CodeIssue],
                     after: List[CodeIssue]) -> List[CodeIssue]:
        """对比前后问题清单，返回新增的问题（按 file+rule+message 匹配）。"""
        before_keys = {(i.file, i.rule, i.message) for i in before}
        return [i for i in after if (i.file, i.rule, i.message) not in before_keys]

    @staticmethod
    def _to_dict(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return {"value": obj}

    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("\\", "/")


# ════════════════════════════════════════════════════════════════════
# 角色 4：执行者
# ════════════════════════════════════════════════════════════════════

class ExecutorAgent:
    """执行者：协调工作流，管理沙箱快照/回滚，生成最终团队报告。

    负责应用决策（保留或回滚工程师的修改）并运行最终测试验证。
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: 沙箱根目录（绝对路径）
        """
        self._sandbox_root = sandbox_root
        self._root = Path(sandbox_root).resolve()
        self._test_runner = TestRunner(sandbox_root)
        self._snapshots: Dict[str, Dict[str, Any]] = {}

    # ── 快照 / 回滚 ────────────────────────────────────────────────

    def snapshot(self, name: str, description: str = "") -> Dict[str, Any]:
        """创建全量快照（复制沙箱到临时目录）。"""
        if not self._root.is_dir():
            return {"success": False, "error": "沙箱目录不存在"}

        if len(self._snapshots) >= _MAX_SNAPSHOTS:
            oldest_id = min(self._snapshots, key=lambda k: self._snapshots[k]["created_at"])
            self._drop_snapshot(oldest_id)

        snap_id = hashlib.sha256(f"{name}-{time.time()}".encode()).hexdigest()[:12]
        snap_dir = Path(tempfile.mkdtemp(prefix="refinery-team-snap-")).resolve()
        try:
            for item in self._root.iterdir():
                dst = snap_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, symlinks=False)
                else:
                    shutil.copy2(item, dst)
        except Exception as e:
            shutil.rmtree(snap_dir, ignore_errors=True)
            logger.error("团队快照创建失败: %s", e)
            return {"success": False, "error": f"快照创建失败: {e}"}

        self._snapshots[snap_id] = {
            "name": name,
            "dir": str(snap_dir),
            "created_at": time.time(),
            "description": description,
        }
        logger.info("团队快照创建: id=%s, name=%s", snap_id, name)
        return {"success": True, "snapshot_id": snap_id, "name": name}

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """回滚到指定快照。"""
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            return {"success": False, "error": f"快照不存在: {snapshot_id}"}
        snap_dir = Path(snap["dir"])
        if not snap_dir.is_dir():
            return {"success": False, "error": "快照数据已丢失"}

        try:
            # 清空当前沙箱
            for item in self._root.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            # 从快照复制回来
            for item in snap_dir.iterdir():
                dst = self._root / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, symlinks=False)
                else:
                    shutil.copy2(item, dst)
            logger.info("团队快照回滚完成: %s", snapshot_id)
            return {"success": True, "snapshot_id": snapshot_id}
        except Exception as e:
            return {"success": False, "error": f"回滚失败: {e}"}

    def cleanup_snapshots(self) -> None:
        """清理所有快照临时目录。"""
        for snap_id in list(self._snapshots.keys()):
            self._drop_snapshot(snap_id)

    def _drop_snapshot(self, snap_id: str) -> None:
        snap = self._snapshots.pop(snap_id, None)
        if not snap:
            return
        snap_dir = Path(snap["dir"])
        if snap_dir.is_dir():
            shutil.rmtree(snap_dir, ignore_errors=True)

    # ── 执行决策 ────────────────────────────────────────────────

    def execute(self, baseline_score: float, baseline_issue_count: int,
                plan: EngineerPlan, verdict: ReviewVerdict,
                snapshot_id: str) -> Tuple[TeamReport, Dict[str, Any]]:
        """应用决策（保留/回滚）并运行最终测试验证。

        Args:
            baseline_score: 基线得分
            baseline_issue_count: 基线问题数
            plan: 工程师方案
            verdict: 审查结论
            snapshot_id: 基线快照 ID

        Returns:
            (团队报告, 执行元信息)
        """
        report = TeamReport(
            initial_score=baseline_score,
            initial_issues=baseline_issue_count,
            proposals_total=plan.total_proposals,
            proposals_applied=plan.applied_count,
            snapshot_id=snapshot_id,
        )
        meta: Dict[str, Any] = {}

        if verdict.verdict == "rejected":
            # 审查未通过：回滚到基线
            rb = self.rollback(snapshot_id)
            report.rolled_back = rb.get("success", False)
            report.status = "rolled_back" if report.rolled_back else "failed"
            report.final_score = baseline_score
            report.final_issues = baseline_issue_count
            report.issues_fixed = 0
            # 回滚后做一次语法检查确认基线可用
            syntax = self._to_dict(self._test_runner.check_syntax())
            report.syntax_passed = bool(syntax.get("success", False))
            meta["rollback"] = rb
            meta["final_syntax_check"] = {"success": report.syntax_passed,
                                          "total": syntax.get("total", 0)}
            logger.info("执行者: 审查未通过，已回滚到基线快照")
        else:
            # approved / changes_requested：保留变更，全量语法验证
            syntax = self._to_dict(self._test_runner.check_syntax())
            report.syntax_passed = bool(syntax.get("success", False))
            report.final_score = verdict.after_score
            report.final_issues = verdict.after_issue_count
            report.issues_fixed = max(0, baseline_issue_count - verdict.after_issue_count)
            report.status = "completed"
            if verdict.verdict == "changes_requested" or not report.syntax_passed:
                report.status = "completed_with_warnings"
            meta["final_syntax_check"] = {"success": report.syntax_passed,
                                          "total": syntax.get("total", 0)}
            logger.info("执行者: 保留变更，语法验证 %s，最终得分 %.1f",
                        "通过" if report.syntax_passed else "失败", report.final_score)

        report.score_improvement = report.final_score - report.initial_score
        report.recommendations = self._build_recommendations(report, verdict, plan)
        report.summary = self._build_summary(report, verdict)
        return report, meta

    # ── 内部方法 ────────────────────────────────────────────────

    @staticmethod
    def _build_recommendations(report: TeamReport, verdict: ReviewVerdict,
                                plan: EngineerPlan) -> List[str]:
        recs: List[str] = []
        if report.rolled_back:
            recs.append("已回滚到基线快照，建议人工介入修复引入的语法/回归问题")
        if plan.manual_review > 0:
            recs.append(f"有 {plan.manual_review} 条中高风险优化提案待人工审批")
        if report.score_improvement > 0:
            recs.append(f"代码质量提升 {report.score_improvement:.1f} 分")
        elif not report.rolled_back and report.proposals_applied == 0:
            recs.append("本轮无可自动应用的低风险优化，建议人工评估架构级重构")
        if not report.syntax_passed:
            recs.append("存在语法错误，需立即修复")
        if verdict.new_issue_count > 0 and not report.rolled_back:
            recs.append(f"修改引入 {verdict.new_issue_count} 个新问题，建议下一轮迭代修正")
        if not recs:
            recs.append("代码质量良好，团队协作流程顺利完成")
        return recs

    @staticmethod
    def _build_summary(report: TeamReport, verdict: ReviewVerdict) -> str:
        lines = [
            f"炼化团队执行状态: {report.status}",
            f"代码质量: {report.initial_score:.1f} → {report.final_score:.1f} "
            f"({'+' if report.score_improvement >= 0 else ''}{report.score_improvement:.1f})",
            f"问题修复: {report.issues_fixed} / {report.initial_issues}",
            f"优化提案: 共 {report.proposals_total} 条，已应用 {report.proposals_applied} 条",
            f"架构建议: {report.suggestions_count} 条",
            f"语法验证: {'通过' if report.syntax_passed else '失败'}",
        ]
        if report.rolled_back:
            lines.append("⚠ 已回滚到基线快照")
        if verdict.new_issue_count > 0:
            lines.append(f"⚠ 引入 {verdict.new_issue_count} 个新问题")
        return "\n".join(lines)

    @staticmethod
    def _to_dict(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return {"value": obj}


# ════════════════════════════════════════════════════════════════════
# 核心类：炼化团队
# ════════════════════════════════════════════════════════════════════

class RefineryTeam:
    """多智能体炼化团队：端到端编排四个角色的协作炼化流程。

    四个阶段：
        Phase 1: 架构师分析 → 架构改进建议
        Phase 2: 工程师生成方案 + 应用低风险优化 → 工程师方案
        Phase 3: 审查员审查 → 审查结论
        Phase 4: 执行者应用决策 + 测试 → 团队报告
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: 沙箱根目录（绝对路径）
        """
        root = Path(sandbox_root).resolve()
        if not root.is_dir():
            raise ValueError(f"沙箱目录不存在: {sandbox_root}")
        self._sandbox_root = str(root)
        self._architect = ArchitectAgent(self._sandbox_root)
        self._engineer = EngineerAgent(self._sandbox_root)
        self._reviewer = ReviewerAgent(self._sandbox_root)
        self._executor = ExecutorAgent(self._sandbox_root)

    def run(self, analysis_report: dict) -> dict:
        """端到端执行团队协作炼化流程。

        Args:
            analysis_report: 基线分析报告（CodeQualityReport.to_dict() 的产物），
                提供 overall_score / issue_count 作为基线对照

        Returns:
            包含 team_report / phases / decisions 的结构化字典
        """
        decisions: List[Dict[str, Any]] = []
        phases: Dict[str, Any] = {}

        try:
            # 重新分析得到完整工作报告对象（含依赖/循环依赖/问题清单）
            working_report = CodeAnalyzer(self._sandbox_root).analyze()
            if "overall_score" in analysis_report:
                baseline_score = float(analysis_report["overall_score"])
            else:
                baseline_score = working_report.overall_score
            if "issue_count" in analysis_report:
                baseline_issue_count = int(analysis_report["issue_count"])
            else:
                baseline_issue_count = len(working_report.issues)

            # Phase 1: 架构师分析
            t1 = time.time()
            suggestions = self._architect.analyze(working_report)
            phases["architect"] = {
                "suggestions": [s.to_dict() for s in suggestions],
                "count": len(suggestions),
                "duration_ms": round((time.time() - t1) * 1000, 1),
            }
            decisions.append({
                "phase": "architect",
                "action": "analyze",
                "detail": f"产出 {len(suggestions)} 条架构改进建议",
            })

            # 执行者创建基线快照（工程师应用前）
            snap = self._executor.snapshot("before-engineer", "工程师应用自动优化前的基线")
            snapshot_id = snap.get("snapshot_id", "")
            if snap.get("success"):
                decisions.append({
                    "phase": "executor",
                    "action": "snapshot",
                    "detail": f"创建基线快照 {snapshot_id}",
                })
            else:
                decisions.append({
                    "phase": "executor",
                    "action": "snapshot_failed",
                    "detail": snap.get("error", "快照创建失败"),
                })

            # Phase 2: 工程师生成方案并应用低风险优化
            t2 = time.time()
            plan = self._engineer.plan_and_apply(working_report, suggestions)
            phases["engineer"] = {
                **plan.to_dict(),
                "duration_ms": round((time.time() - t2) * 1000, 1),
            }
            decisions.append({
                "phase": "engineer",
                "action": "apply_auto",
                "detail": (f"应用 {plan.applied_count}/{plan.auto_applicable} 条自动优化，"
                           f"变更 {len(plan.changed_files)} 个文件"),
            })

            # Phase 3: 审查员审查
            t3 = time.time()
            verdict = self._reviewer.review(working_report, plan.changed_files)
            phases["reviewer"] = {
                **verdict.to_dict(),
                "duration_ms": round((time.time() - t3) * 1000, 1),
            }
            decisions.append({
                "phase": "reviewer",
                "action": "verdict",
                "detail": (f"审查结论: {verdict.verdict}（新问题 {verdict.new_issue_count}，"
                           f"得分变化 {verdict.score_delta:+.1f}）"),
            })

            # Phase 4: 执行者应用决策 + 测试
            t4 = time.time()
            team_report, exec_meta = self._executor.execute(
                baseline_score=baseline_score,
                baseline_issue_count=baseline_issue_count,
                plan=plan,
                verdict=verdict,
                snapshot_id=snapshot_id,
            )
            team_report.suggestions_count = len(suggestions)
            phases["executor"] = {
                **exec_meta,
                "team_report": team_report.to_dict(),
                "duration_ms": round((time.time() - t4) * 1000, 1),
            }
            if team_report.rolled_back:
                decisions.append({
                    "phase": "executor",
                    "action": "rollback",
                    "detail": "审查未通过，已回滚到基线快照",
                })
            else:
                decisions.append({
                    "phase": "executor",
                    "action": "finalize",
                    "detail": (f"保留变更，语法验证{'通过' if team_report.syntax_passed else '失败'}，"
                               f"最终得分 {team_report.final_score:.1f}"),
                })

            logger.info("炼化团队流程完成: status=%s, score=%.1f→%.1f",
                        team_report.status, baseline_score, team_report.final_score)
            return {
                "success": team_report.status != "failed",
                "team_report": team_report.to_dict(),
                "phases": phases,
                "decisions": decisions,
            }

        except Exception as e:
            logger.error("炼化团队执行失败: %s", e, exc_info=True)
            return {
                "success": False,
                "team_report": TeamReport(
                    status="failed",
                    summary=f"执行失败: {e}",
                ).to_dict(),
                "phases": phases,
                "decisions": decisions,
            }
        finally:
            self._executor.cleanup_snapshots()
