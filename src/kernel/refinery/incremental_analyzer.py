"""增量炼化引擎（Incremental Refinery）。

基于文件修改时间戳和内容哈希，只分析自上次分析以来发生变化的文件，
大幅减少大项目的分析时间。

核心机制：
1. 首次分析 = 全量分析，记录每个文件的 mtime + content_hash
2. 后续分析 = 只分析 mtime 变化 或 hash 变化的文件
3. 合并增量结果与上次缓存结果，生成完整报告
4. 支持文件删除/新增检测

遵循 AOS 全局约定：
- 与 CodeAnalyzer 无缝对接
- 增量结果可回退到全量（缓存失效时自动降级）
- 结构化输出，可机读
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .code_analyzer import CodeAnalyzer, CodeQualityReport, CodeIssue

logger = logging.getLogger(__name__)

# 缓存文件名
_CACHE_FILE = ".refinery_cache.json"


@dataclass
class FileSnapshot:
    """单个文件的快照信息。"""
    path: str
    mtime: float
    content_hash: str
    size: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IncrementalResult:
    """增量分析结果。"""
    mode: str = "full"  # "full" | "incremental"
    total_files: int = 0
    changed_files: int = 0
    new_files: int = 0
    deleted_files: int = 0
    unchanged_files: int = 0
    analysis_duration_ms: float = 0.0
    report: Optional[Dict[str, Any]] = None
    changed_file_list: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "total_files": self.total_files,
            "changed_files": self.changed_files,
            "new_files": self.new_files,
            "deleted_files": self.deleted_files,
            "unchanged_files": self.unchanged_files,
            "analysis_duration_ms": round(self.analysis_duration_ms, 1),
            "changed_file_list": self.changed_file_list,
            "report": self.report,
        }


class IncrementalAnalyzer:
    """增量代码分析器。

    用法：
        inc = IncrementalAnalyzer("/path/to/sandbox")
        result = inc.analyze()
        # 首次 = full，后续 = incremental（只分析变化文件）
    """

    def __init__(self, root_dir: str, cache_dir: str = None):
        """
        Args:
            root_dir: 分析根目录
            cache_dir: 缓存存储目录（默认为 root_dir/.refinery）
        """
        self._root = Path(root_dir).resolve()
        self._analyzer = CodeAnalyzer(root_dir)
        self._cache_dir = Path(cache_dir) if cache_dir else self._root / ".refinery"
        self._cache_file = self._cache_dir / _CACHE_FILE
        self._file_cache: Dict[str, FileSnapshot] = {}

    def analyze(self, categories: Optional[List[str]] = None) -> IncrementalResult:
        """执行增量分析。

        Args:
            categories: 分析类别（传给 CodeAnalyzer）

        Returns:
            IncrementalResult 包含模式信息和完整报告
        """
        start = time.time()
        self._load_cache()

        # 获取当前所有 Python 文件
        current_files = self._scan_files()
        current_paths = set(current_files.keys())

        # 与缓存对比
        cached_paths = set(self._file_cache.keys())
        changed: List[str] = []
        new: List[str] = []
        deleted: List[str] = []

        for path, snap in current_files.items():
            if path not in self._file_cache:
                new.append(path)
            else:
                cached = self._file_cache[path]
                if snap.mtime != cached.mtime or snap.content_hash != cached.content_hash:
                    changed.append(path)

        for path in cached_paths - current_paths:
            deleted.append(path)

        has_changes = bool(changed or new or deleted)
        is_first_run = len(self._file_cache) == 0

        result = IncrementalResult()

        if is_first_run or not has_changes:
            # 全量分析
            result.mode = "full" if is_first_run else "incremental"
            if not has_changes and not is_first_run:
                # 无变化，用缓存报告（如果有的话）
                cached_report = self._load_cached_report()
                if cached_report:
                    result.report = cached_report
                    result.total_files = len(current_files)
                    result.unchanged_files = len(current_files)
                    result.analysis_duration_ms = (time.time() - start) * 1000
                    return result

            # 执行全量分析
            report = self._analyzer.analyze(categories=categories)
            result.report = report.to_dict()
            result.total_files = report.total_files
            result.unchanged_files = len(current_files) - len(new) - len(changed)
            result.new_files = len(new)
            result.changed_files = len(changed)
            result.deleted_files = len(deleted)
        else:
            # 增量分析：只分析变化的文件
            result.mode = "incremental"
            result.total_files = len(current_files)
            result.changed_files = len(changed)
            result.new_files = len(new)
            result.deleted_files = len(deleted)
            result.unchanged_files = len(current_files) - len(changed) - len(new)
            result.changed_file_list = sorted(changed + new)

            # 对变化的文件逐个分析
            changed_issues = self._analyze_files(changed + new, categories)

            # 合并：从缓存报告中删除已变文件的旧 issues + 删除文件的 issues，
            # 再加入新 issues
            merged_report = self._merge_report(changed, new, deleted, changed_issues)
            result.report = merged_report

        # 更新缓存
        self._update_cache(current_files)
        self._save_cached_report(result.report)
        self._save_cache()

        result.analysis_duration_ms = (time.time() - start) * 1000
        logger.info("增量分析完成: mode=%s, total=%d, changed=%d, new=%d, deleted=%d, %.0fms",
                    result.mode, result.total_files, result.changed_files,
                    result.new_files, result.deleted_files, result.analysis_duration_ms)
        return result

    # ── 内部方法 ────────────────────────────────────────────────────

    def _scan_files(self) -> Dict[str, FileSnapshot]:
        """扫描当前所有 Python 文件，生成快照。"""
        result: Dict[str, FileSnapshot] = {}
        for p in sorted(self._root.rglob("*.py")):
            if not p.is_file():
                continue
            if any(part in ("__pycache__", ".git", ".venv", "venv", "node_modules")
                   for part in p.parts):
                continue
            try:
                content = p.read_bytes()
                stat = p.stat()
                rel = str(p.relative_to(self._root)).replace("\\", "/")
                result[rel] = FileSnapshot(
                    path=rel,
                    mtime=stat.st_mtime,
                    content_hash=hashlib.sha256(content).hexdigest()[:16],
                    size=stat.st_size,
                )
            except (OSError, PermissionError):
                continue
        return result

    def _analyze_files(self, file_list: List[str],
                       categories: Optional[List[str]] = None) -> List[CodeIssue]:
        """对指定文件列表做分析，返回 issues。"""
        issues: List[CodeIssue] = []
        for rel in file_list:
            full = self._root / rel
            if not full.is_file():
                continue
            try:
                content = full.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # 安全扫描
            for rule_id, pattern, severity, desc in self._get_security_patterns():
                for match in pattern.finditer(content):
                    line_no = content[:match.start()].count("\n") + 1
                    issues.append(CodeIssue(
                        file=rel, line=line_no, severity=severity,
                        category="security", rule=rule_id,
                        message=f"{desc}: {match.group()[:80]}",
                    ))

            # 质量检查（AST）
            try:
                import ast
                tree = ast.parse(content, filename=rel)
                # 未使用 import
                imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
                used_names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        used_names.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        if isinstance(node.value, ast.Name):
                            used_names.add(node.value.id)
                for imp in imports:
                    if isinstance(imp, ast.Import):
                        for alias in imp.names:
                            name = alias.asname or alias.name.split(".")[0]
                            if name not in used_names:
                                issues.append(CodeIssue(
                                    file=rel, line=imp.lineno, severity="low",
                                    category="quality", rule="unused_import",
                                    message=f"未使用的导入: {alias.name}",
                                ))
                # 复杂度
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        comp = self._cyclomatic_complexity(node)
                        if comp > 15:
                            issues.append(CodeIssue(
                                file=rel, line=node.lineno, severity="high",
                                category="complexity", rule="cyclomatic_complexity_high",
                                message=f"函数 {node.name} 圈复杂度 {comp}（>15）",
                                suggestion="建议拆分函数",
                            ))
                        elif comp > 10:
                            issues.append(CodeIssue(
                                file=rel, line=node.lineno, severity="medium",
                                category="complexity", rule="cyclomatic_complexity_medium",
                                message=f"函数 {node.name} 圈复杂度 {comp}（>10）",
                            ))
            except SyntaxError:
                issues.append(CodeIssue(
                    file=rel, line=0, severity="medium",
                    category="quality", rule="syntax_error",
                    message="语法错误，无法解析",
                ))

        return issues

    def _merge_report(self, changed: List[str], new: List[str],
                      deleted: List[str], new_issues: List[CodeIssue]) -> Dict[str, Any]:
        """合并增量结果与缓存报告。"""
        cached = self._load_cached_report()
        if not cached:
            # 无缓存，降级为全量
            report = self._analyzer.analyze()
            return report.to_dict()

        # 从缓存 issues 中删除 changed/new/deleted 文件的旧 issues
        old_issues = cached.get("issues", [])
        exclude_files = set(changed + new + deleted)
        kept_issues = [i for i in old_issues if i.get("file") not in exclude_files]

        # 加入新 issues
        merged_issues = kept_issues + [i.to_dict() if hasattr(i, "to_dict") else i
                                       for i in new_issues]

        # 更新统计
        cached["issues"] = merged_issues
        cached["issue_count"] = len(merged_issues)

        # 重新计算分数
        by_severity = {"high": 0, "medium": 0, "low": 0}
        for i in merged_issues:
            sev = i.get("severity", "low")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        penalty = (by_severity.get("high", 0) * 5 +
                   by_severity.get("medium", 0) * 2 +
                   by_severity.get("low", 0) * 0.5)
        cached["overall_score"] = max(0.0, 100.0 - penalty)
        cached["issues_by_severity"] = by_severity

        return cached

    def _load_cache(self) -> None:
        """从磁盘加载文件缓存。"""
        self._file_cache = {}
        if self._cache_file.is_file():
            try:
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                for path, snap in data.get("files", {}).items():
                    self._file_cache[path] = FileSnapshot(
                        path=path, mtime=snap["mtime"],
                        content_hash=snap["content_hash"], size=snap["size"],
                    )
            except (json.JSONDecodeError, KeyError, OSError):
                logger.warning("缓存文件损坏，将执行全量分析")

    def _save_cache(self) -> None:
        """保存文件缓存到磁盘。"""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "files": {p: s.to_dict() for p, s in self._file_cache.items()},
                "updated_at": time.time(),
            }
            self._cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.warning("缓存保存失败: %s", e)

    def _update_cache(self, current_files: Dict[str, FileSnapshot]) -> None:
        """更新内存缓存。"""
        self._file_cache = dict(current_files)

    def _load_cached_report(self) -> Optional[Dict[str, Any]]:
        """加载上次的分析报告缓存。"""
        report_file = self._cache_dir / ".refinery_report.json"
        if report_file.is_file():
            try:
                return json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _save_cached_report(self, report: Dict[str, Any]) -> None:
        """保存分析报告到缓存。"""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            report_file = self._cache_dir / ".refinery_report.json"
            report_file.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _get_security_patterns():
        """获取安全模式（从 code_analyzer 复用）。"""
        from .code_analyzer import _SECURITY_PATTERNS
        return _SECURITY_PATTERNS

    @staticmethod
    def _cyclomatic_complexity(func) -> int:
        """计算圈复杂度（从 code_analyzer 复用）。"""
        import ast
        complexity = 1
        for node in ast.walk(func):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, (ast.ExceptHandler,)):
                complexity += 1
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                complexity += 1
            elif isinstance(node, ast.Assert):
                complexity += 1
        return complexity

    def invalidate_cache(self) -> None:
        """手动使缓存失效，下次分析将全量执行。"""
        self._file_cache = {}
        try:
            self._cache_file.unlink(missing_ok=True)
            (self._cache_dir / ".refinery_report.json").unlink(missing_ok=True)
        except OSError:
            pass
        logger.info("增量分析缓存已失效")
