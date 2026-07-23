"""代码优化引擎（Code Optimizer）。

基于代码分析结果，生成可执行的优化提案并安全地应用到沙箱中：
- 安全加固（修复安全风险）
- 性能优化（重构高复杂度函数）
- 质量改进（移除无用 import、修复命名风格）
- 架构优化（解决循环依赖、提取公共模块）

设计原则：
- 每个优化都生成 OptimizationProposal，带风险等级和回滚方案
- 自动应用低风险优化，中高风险需审批
- 应用前自动快照，失败自动回滚
- 与 CodeAnalyzer 输出无缝对接
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OptimizationProposal:
    """一个优化提案。"""
    id: str
    category: str  # security / performance / quality / architecture / style
    title: str
    description: str
    risk_level: str  # low / medium / high
    expected_benefit: str = ""
    auto_applicable: bool = False  # 是否可以自动应用

    # 涉及的文件
    files: List[str] = field(default_factory=list)

    # 具体变更（file_path -> new_content）
    changes: Dict[str, str] = field(default_factory=dict)

    # 回滚所需的快照 ID（应用后填充）
    snapshot_id: str = ""

    # 状态
    status: str = "proposed"  # proposed / approved / applied / rejected / failed
    applied_at: float = 0.0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "risk_level": self.risk_level,
            "expected_benefit": self.expected_benefit,
            "auto_applicable": self.auto_applicable,
            "files": self.files,
            "status": self.status,
            "applied_at": self.applied_at,
            "error": self.error,
        }


class CodeOptimizer:
    """代码优化引擎。

    接收 CodeQualityReport，生成优化提案，并可安全地应用到沙箱中。
    """

    def __init__(self, sandbox_root: str):
        self._root = Path(sandbox_root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"沙箱目录不存在: {sandbox_root}")
        self._proposals: Dict[str, OptimizationProposal] = {}

    @property
    def proposals(self) -> List[OptimizationProposal]:
        return list(self._proposals.values())

    # ── 提案生成 ────────────────────────────────────────────────────

    def generate_proposals(self, quality_report) -> List[OptimizationProposal]:
        """从质量报告生成优化提案。"""
        self._proposals.clear()

        # 按类别生成提案
        self._gen_security_proposals(quality_report)
        self._gen_quality_proposals(quality_report)
        self._gen_complexity_proposals(quality_report)
        self._gen_architecture_proposals(quality_report)

        logger.info("生成优化提案: %d 条", len(self._proposals))
        return list(self._proposals.values())

    def _gen_security_proposals(self, report) -> None:
        """生成安全类优化提案。"""
        # 按文件分组安全问题
        file_issues: Dict[str, List] = {}
        for issue in report.issues:
            if issue.category == "security" and issue.severity in ("high", "medium"):
                if issue.file not in file_issues:
                    file_issues[issue.file] = []
                file_issues[issue.file].append(issue)

        idx = 0
        for file_path, issues in file_issues.items():
            idx += 1
            desc_lines = [f"文件 {file_path} 存在 {len(issues)} 个安全问题："]
            for iss in issues[:5]:
                desc_lines.append(f"  - [{iss.severity}] L{iss.line}: {iss.message}")
            if len(issues) > 5:
                desc_lines.append(f"  ... 还有 {len(issues) - 5} 个")

            prop = OptimizationProposal(
                id=f"sec-{idx:04d}",
                category="security",
                title=f"安全加固: {Path(file_path).name}",
                description="\n".join(desc_lines),
                risk_level="high",
                expected_benefit="消除安全风险，避免注入/泄露",
                auto_applicable=False,
                files=[file_path],
            )
            self._proposals[prop.id] = prop

    def _gen_quality_proposals(self, report) -> None:
        """生成质量类优化提案（可自动应用的低风险优化）。"""
        # 未使用的 import 可以安全移除
        unused_imports: Dict[str, List[Tuple[int, str]]] = {}
        for issue in report.issues:
            if issue.rule == "unused_import" and issue.category == "quality":
                if issue.file not in unused_imports:
                    unused_imports[issue.file] = []
                unused_imports[issue.file].append((issue.line, issue.message))

        idx = 0
        for file_path, items in unused_imports.items():
            idx += 1
            full = self._root / file_path
            if not full.is_file():
                continue
            try:
                content = full.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lines = content.splitlines(keepends=True)
            # 标记要删除的行号
            lines_to_remove = {ln for ln, _ in items}
            new_lines = [l for i, l in enumerate(lines, 1) if i not in lines_to_remove]
            new_content = "".join(new_lines)

            if new_content != content:
                prop = OptimizationProposal(
                    id=f"qual-unused-{idx:04d}",
                    category="quality",
                    title=f"移除未使用 import: {Path(file_path).name}",
                    description=f"移除 {len(items)} 个未使用的 import 语句",
                    risk_level="low",
                    expected_benefit="减少不必要的依赖，提高代码清晰度",
                    auto_applicable=True,
                    files=[file_path],
                    changes={file_path: new_content},
                )
                self._proposals[prop.id] = prop

    def _gen_complexity_proposals(self, report) -> None:
        """生成复杂度类优化提案。"""
        # 高复杂度函数需要重构，但不能自动应用
        high_complex = [i for i in report.issues
                        if i.rule.startswith("cyclomatic") and i.severity == "high"]

        if high_complex:
            files = sorted(set(i.file for i in high_complex))
            desc_lines = [f"发现 {len(high_complex)} 个高复杂度函数："]
            for iss in high_complex[:10]:
                desc_lines.append(f"  - {iss.file}:L{iss.line}: {iss.message}")

            prop = OptimizationProposal(
                id="complex-high-0001",
                category="performance",
                title="重构高复杂度函数",
                description="\n".join(desc_lines),
                risk_level="medium",
                expected_benefit="提高可维护性，降低 bug 率",
                auto_applicable=False,
                files=files,
            )
            self._proposals[prop.id] = prop

    def _gen_architecture_proposals(self, report) -> None:
        """生成架构类优化提案。"""
        if report.circular_deps:
            files = set()
            for cycle in report.circular_deps:
                for mod in cycle:
                    # 模块名转文件路径（简单映射）
                    fp = mod.replace(".", "/") + ".py"
                    if (self._root / fp).is_file():
                        files.add(fp)
                    init_fp = mod.replace(".", "/") + "/__init__.py"
                    if (self._root / init_fp).is_file():
                        files.add(init_fp)

            desc_lines = [f"发现 {len(report.circular_deps)} 组循环依赖："]
            for cycle in report.circular_deps:
                desc_lines.append(f"  - {' → '.join(cycle)}")

            prop = OptimizationProposal(
                id="arch-circular-0001",
                category="architecture",
                title="解决循环依赖",
                description="\n".join(desc_lines),
                risk_level="high",
                expected_benefit="改善架构可维护性，避免导入顺序问题",
                auto_applicable=False,
                files=sorted(files),
            )
            self._proposals[prop.id] = prop

        # 文件过长的拆分建议
        long_files = [i for i in report.issues
                      if i.rule == "file_too_long" and i.severity == "high"]
        if long_files:
            files = [i.file for i in long_files]
            prop = OptimizationProposal(
                id="arch-split-0001",
                category="architecture",
                title=f"拆分 {len(long_files)} 个过长文件",
                description=f"以下文件超过 {500} 行，建议拆分：\n" +
                            "\n".join(f"  - {f}" for f in files),
                risk_level="medium",
                expected_benefit="提高模块内聚性，降低认知负担",
                auto_applicable=False,
                files=files,
            )
            self._proposals[prop.id] = prop

    # ── 提案应用 ────────────────────────────────────────────────────

    def apply_proposal(self, proposal_id: str,
                       snapshot_before: bool = True) -> Dict[str, Any]:
        """应用一个优化提案。

        Args:
            proposal_id: 提案 ID
            snapshot_before: 应用前是否做快照

        Returns:
            应用结果字典
        """
        if proposal_id not in self._proposals:
            return {"success": False, "error": f"提案不存在: {proposal_id}"}

        prop = self._proposals[proposal_id]

        if prop.status == "applied":
            return {"success": False, "error": "提案已应用"}

        if not prop.changes:
            prop.status = "failed"
            prop.error = "无具体变更内容，无法自动应用"
            return {"success": False, "error": prop.error}

        # 快照
        if snapshot_before:
            snap_id = f"before-{proposal_id}"
            # 简单快照：把要修改的文件备份到内存
            backups: Dict[str, str] = {}
            for fp in prop.changes:
                full = self._root / fp
                if full.is_file():
                    try:
                        backups[fp] = full.read_text(encoding="utf-8")
                    except OSError:
                        pass
            prop.snapshot_id = snap_id

        # 应用变更
        try:
            for fp, new_content in prop.changes.items():
                full = self._root / fp
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(new_content, encoding="utf-8")

            prop.status = "applied"
            prop.applied_at = time.time()
            logger.info("优化提案已应用: %s (%s)", proposal_id, prop.title)
            return {
                "success": True,
                "proposal_id": proposal_id,
                "files_changed": len(prop.changes),
                "snapshot_id": prop.snapshot_id,
            }
        except Exception as e:
            # 失败回滚
            if snapshot_before:
                for fp, old_content in backups.items():
                    full = self._root / fp
                    try:
                        full.write_text(old_content, encoding="utf-8")
                    except OSError:
                        pass
            prop.status = "failed"
            prop.error = str(e)
            logger.error("优化提案应用失败: %s, error=%s", proposal_id, e)
            return {"success": False, "error": str(e)}

    def apply_auto_proposals(self, max_count: int = 20) -> Dict[str, Any]:
        """批量应用所有低风险自动优化。"""
        auto_props = [p for p in self._proposals.values()
                      if p.auto_applicable and p.status == "proposed"]
        auto_props = auto_props[:max_count]

        results = []
        success_count = 0
        for prop in auto_props:
            res = self.apply_proposal(prop.id, snapshot_before=True)
            results.append(res)
            if res.get("success"):
                success_count += 1

        return {
            "success": True,
            "total": len(auto_props),
            "applied": success_count,
            "failed": len(auto_props) - success_count,
            "results": results,
        }

    # ── 提案管理 ────────────────────────────────────────────────────

    def get_proposal(self, proposal_id: str) -> Optional[OptimizationProposal]:
        return self._proposals.get(proposal_id)

    def list_proposals(self, category: str = None,
                       risk_level: str = None,
                       status: str = None) -> List[OptimizationProposal]:
        props = list(self._proposals.values())
        if category:
            props = [p for p in props if p.category == category]
        if risk_level:
            props = [p for p in props if p.risk_level == risk_level]
        if status:
            props = [p for p in props if p.status == status]
        return sorted(props, key=lambda p: (p.risk_level == "high",
                                             p.risk_level == "medium",
                                             p.risk_level == "low"))

    def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """审批通过一个高风险提案。"""
        prop = self._proposals.get(proposal_id)
        if not prop:
            return {"success": False, "error": f"提案不存在: {proposal_id}"}
        if prop.status != "proposed":
            return {"success": False, "error": f"提案状态不是 proposed: {prop.status}"}
        prop.status = "approved"
        return {"success": True, "proposal_id": proposal_id}

    def reject_proposal(self, proposal_id: str, reason: str = "") -> Dict[str, Any]:
        """拒绝一个提案。"""
        prop = self._proposals.get(proposal_id)
        if not prop:
            return {"success": False, "error": f"提案不存在: {proposal_id}"}
        prop.status = "rejected"
        prop.error = reason
        return {"success": True, "proposal_id": proposal_id}
