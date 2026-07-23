"""代码分析引擎（Code Analyzer）。

对沙箱内的项目代码进行多维度静态分析：
- 代码质量评估（复杂度/重复度/注释覆盖率）
- 依赖关系图谱（模块依赖/导入关系/调用关系）
- 安全风险扫描（危险函数/硬编码密钥/注入点）
- 架构合规性检查（分层依赖/循环依赖/接口一致性）

设计原则：
- 纯静态分析，不执行代码（安全）
- 基于 AST 的结构化分析（准确）
- 可配置规则集（灵活）
- 输出结构化报告（可机读）
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── 安全风险模式 ──────────────────────────────────────────────────────
_SECURITY_PATTERNS = [
    ("hardcoded_secret", re.compile(
        r"(api[_-]?key|secret|password|token|private[_-]?key)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
        re.I), "high", "硬编码密钥/口令"),
    ("sql_injection", re.compile(
        r"(execute|cursor\.execute|query)\s*\(\s*f[\"']|%s.*%|\.format\(", re.I),
        "medium", "潜在 SQL 注入"),
    ("cmd_injection_fstring", re.compile(
        r"(os\.system|os\.popen|subprocess\.(Popen|call|run))\s*\(\s*f[\"']", re.I),
        "high", "f-string 命令注入风险"),
    ("dangerous_os_system", re.compile(
        r"os\.system\s*\(", re.I),
        "high", "os.system 调用（命令执行风险）"),
    ("dangerous_os_popen", re.compile(
        r"os\.popen\s*\(", re.I),
        "high", "os.popen 调用（命令执行风险）"),
    ("dangerous_subprocess", re.compile(
        r"subprocess\.(Popen|call|run|check_call|check_output)\s*\(", re.I),
        "medium", "subprocess 调用（命令执行需审查）"),
    ("unsafe_eval", re.compile(r"\beval\s*\(", re.I),
        "high", "eval 调用（代码注入风险）"),
    ("unsafe_exec", re.compile(r"\bexec\s*\(", re.I),
        "high", "exec 调用（代码注入风险）"),
    ("unsafe_pickle", re.compile(r"pickle\.loads\s*\(", re.I),
        "medium", "反序列化风险"),
    ("unsafe_yaml", re.compile(r"yaml\.load\s*\(", re.I),
        "medium", "不安全的 YAML 加载"),
    ("bare_except", re.compile(r"except\s*:", re.I),
        "low", "裸 except（吞异常）"),
]

# ── 复杂度阈值 ────────────────────────────────────────────────────────
_CYCLOMATIC_HIGH = 15
_CYCLOMATIC_MEDIUM = 10
_FUNCTION_LENGTH_HIGH = 80
_FUNCTION_LENGTH_MEDIUM = 50
_FILE_LINE_HIGH = 500
_FILE_LINE_MEDIUM = 300


@dataclass
class CodeIssue:
    """单个代码问题。"""
    file: str
    line: int
    severity: str  # high / medium / low
    category: str  # security / quality / complexity / style / architecture
    rule: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleDependency:
    """模块依赖关系。"""
    source: str
    target: str
    imports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CodeQualityReport:
    """代码质量分析报告。"""
    total_files: int = 0
    total_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0

    issues: List[CodeIssue] = field(default_factory=list)
    dependencies: List[ModuleDependency] = field(default_factory=list)
    circular_deps: List[List[str]] = field(default_factory=list)

    avg_complexity: float = 0.0
    comment_ratio: float = 0.0
    duplicate_code_ratio: float = 0.0

    security_score: float = 100.0
    quality_score: float = 100.0
    architecture_score: float = 100.0
    overall_score: float = 100.0

    summary: str = ""
    analysis_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "total_functions": self.total_functions,
            "total_classes": self.total_classes,
            "issues": [i.to_dict() for i in self.issues],
            "issue_count": len(self.issues),
            "high_issues": sum(1 for i in self.issues if i.severity == "high"),
            "medium_issues": sum(1 for i in self.issues if i.severity == "medium"),
            "low_issues": sum(1 for i in self.issues if i.severity == "low"),
            "circular_deps": self.circular_deps,
            "avg_complexity": round(self.avg_complexity, 2),
            "comment_ratio": round(self.comment_ratio, 4),
            "duplicate_code_ratio": round(self.duplicate_code_ratio, 4),
            "security_score": round(self.security_score, 1),
            "quality_score": round(self.quality_score, 1),
            "architecture_score": round(self.architecture_score, 1),
            "overall_score": round(self.overall_score, 1),
            "summary": self.summary,
            "analysis_duration_ms": round(self.analysis_duration_ms, 1),
        }


class CodeAnalyzer:
    """代码分析引擎。

    对沙箱内的项目进行全量静态分析，输出结构化质量报告。
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: 沙箱根目录（绝对路径）
        """
        self._root = Path(sandbox_root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"沙箱目录不存在: {sandbox_root}")

        self._python_files: List[Path] = []
        self._all_files: List[Path] = []
        self._scan()

    def _scan(self) -> None:
        """扫描沙箱内的所有文件。"""
        for p in self._root.rglob("*"):
            if not p.is_file():
                continue
            # 排除常见的非源码目录
            parts = set(p.relative_to(self._root).parts)
            if parts & {"__pycache__", ".git", "node_modules", ".venv", "venv",
                        "data", ".pytest_cache", ".mypy_cache", ".ruff_cache"}:
                continue
            self._all_files.append(p)
            if p.suffix == ".py":
                self._python_files.append(p)

        logger.info("代码分析引擎就绪: py_files=%d, all_files=%d",
                    len(self._python_files), len(self._all_files))

    # ── 主入口 ────────────────────────────────────────────────────────

    def analyze(self, categories: Optional[List[str]] = None,
                file_pattern: str = None) -> CodeQualityReport:
        """执行全量分析。

        Args:
            categories: 分析类别列表，None 表示全部
                ["security", "quality", "complexity", "architecture", "duplication"]
            file_pattern: 只分析匹配的文件（glob 模式，相对路径）
        """
        start = time.time()
        report = CodeQualityReport()
        cats = set(categories or ["security", "quality", "complexity",
                                   "architecture", "duplication"])

        files = self._python_files
        if file_pattern:
            import fnmatch
            files = [f for f in files
                     if fnmatch.fnmatch(str(f.relative_to(self._root)), file_pattern)]

        report.total_files = len(files)

        all_complexities: List[int] = []
        all_lines: List[int] = []
        total_comment_lines = 0

        for file_path in files:
            rel = str(file_path.relative_to(self._root))
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            lines = content.splitlines()
            line_count = len(lines)
            report.total_lines += line_count
            all_lines.append(line_count)

            # 注释行统计
            comment_lines = sum(1 for l in lines
                                if l.strip().startswith("#") or
                                l.strip().startswith('"""') or
                                l.strip().startswith("'''"))
            total_comment_lines += comment_lines

            try:
                tree = ast.parse(content)
            except SyntaxError:
                report.issues.append(CodeIssue(
                    file=rel, line=0, severity="medium",
                    category="quality", rule="syntax_error",
                    message=f"语法错误，无法解析",
                ))
                continue

            # 统计函数/类
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
            report.total_functions += len(funcs)
            report.total_classes += len(classes)

            # 复杂度分析
            if "complexity" in cats:
                for func in funcs:
                    comp = self._cyclomatic_complexity(func)
                    all_complexities.append(comp)
                    if comp > _CYCLOMATIC_HIGH:
                        report.issues.append(CodeIssue(
                            file=rel, line=func.lineno, severity="high",
                            category="complexity", rule="cyclomatic_complexity_high",
                            message=f"函数 {func.name} 圈复杂度 {comp}（>{_CYCLOMATIC_HIGH}）",
                            suggestion="建议拆分函数，降低复杂度",
                        ))
                    elif comp > _CYCLOMATIC_MEDIUM:
                        report.issues.append(CodeIssue(
                            file=rel, line=func.lineno, severity="medium",
                            category="complexity", rule="cyclomatic_complexity_medium",
                            message=f"函数 {func.name} 圈复杂度 {comp}（>{_CYCLOMATIC_MEDIUM}）",
                            suggestion="可考虑拆分",
                        ))

                    func_len = self._function_line_count(func, lines)
                    if func_len > _FUNCTION_LENGTH_HIGH:
                        report.issues.append(CodeIssue(
                            file=rel, line=func.lineno, severity="high",
                            category="complexity", rule="function_too_long",
                            message=f"函数 {func.name} 过长（{func_len}行）",
                            suggestion="建议拆分",
                        ))

            # 安全扫描
            if "security" in cats:
                self._scan_security(rel, content, lines, report)

            # 质量检查
            if "quality" in cats:
                self._scan_quality(rel, tree, lines, report)

            # 架构/依赖分析
            if "architecture" in cats:
                dep = self._extract_deps(rel, tree)
                if dep:
                    report.dependencies.append(dep)

        # 文件级大小检查
        if "quality" in cats:
            for file_path in files:
                rel = str(file_path.relative_to(self._root))
                try:
                    lc = sum(1 for _ in file_path.open(encoding="utf-8"))
                except OSError:
                    continue
                if lc > _FILE_LINE_HIGH:
                    report.issues.append(CodeIssue(
                        file=rel, line=0, severity="high",
                        category="quality", rule="file_too_long",
                        message=f"文件过长（{lc}行）",
                        suggestion="建议拆分为多个模块",
                    ))
                elif lc > _FILE_LINE_MEDIUM:
                    report.issues.append(CodeIssue(
                        file=rel, line=0, severity="medium",
                        category="quality", rule="file_long",
                        message=f"文件较长（{lc}行）",
                        suggestion="可考虑拆分",
                    ))

        # 循环依赖检测
        if "architecture" in cats:
            report.circular_deps = self._detect_circular_deps(report.dependencies)
            for cycle in report.circular_deps:
                report.issues.append(CodeIssue(
                    file=cycle[0], line=0, severity="high",
                    category="architecture", rule="circular_dependency",
                    message=f"循环依赖: {' → '.join(cycle)} → {cycle[0]}",
                    suggestion="通过依赖倒置或提取公共模块解决",
                ))

        # 重复代码检测（简单行级哈希）
        if "duplication" in cats:
            report.duplicate_code_ratio = self._detect_duplication(files, report)

        # 汇总评分
        report.avg_complexity = (sum(all_complexities) / len(all_complexities)
                                 if all_complexities else 0.0)
        report.comment_ratio = (total_comment_lines / report.total_lines
                                if report.total_lines > 0 else 0.0)
        self._compute_scores(report)
        report.analysis_duration_ms = (time.time() - start) * 1000

        report.summary = self._generate_summary(report)
        logger.info("代码分析完成: score=%.1f, issues=%d, duration_ms=%.0f",
                    report.overall_score, len(report.issues),
                    report.analysis_duration_ms)
        return report

    # ── 各类分析器 ──────────────────────────────────────────────────

    def _scan_security(self, rel_path: str, content: str,
                       lines: List[str], report: CodeQualityReport) -> None:
        """安全风险扫描。"""
        for rule_id, pattern, severity, desc in _SECURITY_PATTERNS:
            for match in pattern.finditer(content):
                line_no = content[:match.start()].count("\n") + 1
                report.issues.append(CodeIssue(
                    file=rel_path, line=line_no, severity=severity,
                    category="security", rule=rule_id,
                    message=f"{desc}: {match.group()[:80]}",
                    suggestion="请审查并修复此安全问题",
                ))

    def _scan_quality(self, rel_path: str, tree: ast.AST,
                      lines: List[str], report: CodeQualityReport) -> None:
        """代码质量检查。"""
        # 未使用的 import（简单检测：import 了但没用到）
        imported: Dict[str, int] = {}  # name -> lineno
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    imported[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported[name] = node.lineno

        used_names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)

        for name, lineno in imported.items():
            if name not in used_names:
                report.issues.append(CodeIssue(
                    file=rel_path, line=lineno, severity="low",
                    category="quality", rule="unused_import",
                    message=f"未使用的 import: {name}",
                    suggestion="移除未使用的导入",
                ))

    def _extract_deps(self, rel_path: str, tree: ast.AST) -> Optional[ModuleDependency]:
        """提取模块依赖关系。"""
        imports: List[str] = []
        targets: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    targets.append(alias.name)
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    full = f"{mod}.{alias.name}" if mod else alias.name
                    targets.append(mod or alias.name)
                    imports.append(f"from {mod} import {alias.name}")

        if not targets:
            return None

        # 只记录项目内部模块（以 src. 开头或相对路径）
        module_name = rel_path.replace("\\", ".").replace("/", ".")
        if module_name.endswith(".py"):
            module_name = module_name[:-3]
        # 去掉 __init__
        if module_name.endswith(".__init__"):
            module_name = module_name[:-9]

        return ModuleDependency(
            source=module_name,
            target=targets[0] if targets else "",
            imports=imports,
        )

    def _detect_circular_deps(self, deps: List[ModuleDependency]) -> List[List[str]]:
        """检测循环依赖（简单 DFS 环检测）。"""
        graph: Dict[str, Set[str]] = {}
        for dep in deps:
            if dep.source not in graph:
                graph[dep.source] = set()
            graph[dep.source].add(dep.target)

        # 只关注项目内部模块（含 src. 或 kernel. 等）
        internal = {k for k in graph if any(
            k.startswith(p) for p in ("src.", "kernel.", "core.", "api.",
                                       "skills.", "execution.", "memory.",
                                       "deerflow.", "compliance.", "voice.")
        )}

        cycles: List[List[str]] = []
        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(node: str):
            if node in stack:
                idx = stack.index(node)
                cycle = stack[idx:]
                if len(cycle) >= 2 and cycle not in cycles:
                    cycles.append(cycle[:])
                return
            if node in visited:
                return
            visited.add(node)
            stack.append(node)
            for neighbor in graph.get(node, set()):
                if neighbor in internal:
                    dfs(neighbor)
            stack.pop()

        for node in sorted(internal):
            if node not in visited:
                dfs(node)

        return cycles

    def _detect_duplication(self, files: List[Path],
                            report: CodeQualityReport) -> float:
        """简单的重复代码检测（基于函数体哈希）。"""
        func_hashes: Dict[str, List[Tuple[str, int, str]]] = {}

        for file_path in files:
            rel = str(file_path.relative_to(self._root))
            try:
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content)
            except (UnicodeDecodeError, SyntaxError, OSError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # 去掉注释和字符串，计算结构哈希
                    body_stripped = self._normalize_ast(node)
                    if len(body_stripped) < 200:  # 太短不算重复
                        continue
                    h = hashlib.md5(body_stripped.encode()).hexdigest()[:12]
                    if h not in func_hashes:
                        func_hashes[h] = []
                    func_hashes[h].append((rel, node.lineno, node.name))

        duplicate_count = 0
        total_funcs = max(1, sum(len(v) for v in func_hashes.values()))

        for h, occurrences in func_hashes.items():
            if len(occurrences) > 1:
                duplicate_count += len(occurrences)
                locations = "; ".join(f"{f}:{l}({n})" for f, l, n in occurrences)
                first = occurrences[0]
                report.issues.append(CodeIssue(
                    file=first[0], line=first[1], severity="medium",
                    category="quality", rule="duplicate_code",
                    message=f"重复代码（{len(occurrences)}处）: {locations}",
                    suggestion="提取公共函数/方法，消除重复",
                ))

        return duplicate_count / total_funcs if total_funcs > 0 else 0.0

    # ── 工具方法 ────────────────────────────────────────────────────

    @staticmethod
    def _cyclomatic_complexity(node: ast.AST) -> int:
        """计算圈复杂度（决策点 + 1）。"""
        count = 1
        for n in ast.walk(node):
            if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While,
                              ast.And, ast.Or, ast.ExceptHandler,
                              ast.With, ast.AsyncWith)):
                count += 1
            elif isinstance(n, ast.IfExp):
                count += 1
        return count

    @staticmethod
    def _function_line_count(func: ast.AST, lines: List[str]) -> int:
        """估算函数行数。"""
        if not hasattr(func, "end_lineno") or func.end_lineno is None:
            return 0
        return func.end_lineno - func.lineno + 1

    @staticmethod
    def _normalize_ast(node: ast.AST) -> str:
        """把 AST 序列化为规范化字符串（用于重复检测）。"""
        parts = []
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                parts.append("N")
            elif isinstance(n, ast.Constant):
                parts.append("C")
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parts.append("F")
            elif isinstance(n, ast.ClassDef):
                parts.append("K")
            elif isinstance(n, ast.Call):
                parts.append("()")
            elif isinstance(n, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                parts.append("OP")
        return "".join(parts)

    @staticmethod
    def _compute_scores(report: CodeQualityReport) -> None:
        """计算各项评分（0-100）。"""
        high = sum(1 for i in report.issues if i.severity == "high")
        med = sum(1 for i in report.issues if i.severity == "medium")
        low = sum(1 for i in report.issues if i.severity == "low")

        # 安全分：高风险问题扣 10 分，中风险扣 3 分
        sec_deduct = high * 10 + med * 3 + low * 0.5
        report.security_score = max(0.0, 100.0 - sec_deduct)

        # 质量分：高扣 5，中扣 2，低扣 0.5
        qual_deduct = high * 5 + med * 2 + low * 0.5
        report.quality_score = max(0.0, 100.0 - qual_deduct)

        # 架构分：循环依赖每个扣 15 分
        arch_deduct = len(report.circular_deps) * 15 + high * 3
        report.architecture_score = max(0.0, 100.0 - arch_deduct)

        # 总分
        report.overall_score = round(
            0.35 * report.security_score +
            0.35 * report.quality_score +
            0.30 * report.architecture_score,
            1,
        )

    @staticmethod
    def _generate_summary(report: CodeQualityReport) -> str:
        """生成人类可读的总结。"""
        high = sum(1 for i in report.issues if i.severity == "high")
        med = sum(1 for i in report.issues if i.severity == "medium")
        low = sum(1 for i in report.issues if i.severity == "low")

        grade = "A" if report.overall_score >= 90 else \
                "B" if report.overall_score >= 80 else \
                "C" if report.overall_score >= 70 else \
                "D" if report.overall_score >= 60 else "F"

        lines = [
            f"代码质量总评: {grade}（{report.overall_score:.1f}/100）",
            f"文件数: {report.total_files} | 行数: {report.total_lines} | "
            f"函数: {report.total_functions} | 类: {report.total_classes}",
            f"问题统计: 高风险 {high} | 中风险 {med} | 低风险 {low}",
            f"平均圈复杂度: {report.avg_complexity:.1f}",
            f"注释覆盖率: {report.comment_ratio * 100:.1f}%",
            f"重复代码率: {report.duplicate_code_ratio * 100:.1f}%",
            f"安全分: {report.security_score:.1f} | 质量分: {report.quality_score:.1f} | "
            f"架构分: {report.architecture_score:.1f}",
        ]

        if report.circular_deps:
            lines.append(f"⚠️ 发现 {len(report.circular_deps)} 组循环依赖")

        return "\n".join(lines)
