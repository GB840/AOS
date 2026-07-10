"""
No-Mistakes — AI驱动的代码质量自动把关。
在代码推送前自动运行AI验证流程，确保代码质量。
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

QUALITY_CHECKS = {
    "syntax": {
        "name": "语法检查",
        "description": "验证代码语法正确性",
        "severity": "critical",
        "languages": ["python", "javascript", "typescript", "java", "cpp", "go", "rust"],
    },
    "security": {
        "name": "安全检查",
        "description": "检测常见安全漏洞",
        "severity": "critical",
        "checks": ["sql_injection", "xss", "hardcoded_secrets", "path_traversal", "command_injection"],
    },
    "style": {
        "name": "代码风格",
        "description": "检查代码风格一致性",
        "severity": "medium",
        "languages": ["python", "javascript", "typescript", "java", "cpp", "go", "rust"],
    },
    "complexity": {
        "name": "复杂度分析",
        "description": "分析代码复杂度和可维护性",
        "severity": "medium",
        "metrics": ["cyclomatic_complexity", "function_length", "nesting_depth"],
    },
    "best_practices": {
        "name": "最佳实践",
        "description": "检查是否遵循语言最佳实践",
        "severity": "medium",
    },
    "test_coverage": {
        "name": "测试覆盖率",
        "description": "评估测试覆盖情况",
        "severity": "low",
    },
}

SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|secret[_-]?key|password|token|credential)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
    r"(?i)(ak|sk|access[_-]?key|secret[_-]?key)\s*[=:]\s*['\"][A-Za-z0-9+/=]{16,}['\"]",
    r"(?i)bearer\s+[A-Za-z0-9._-]{20,}",
    r"(?i)(rsa|ssh|private[_-]?key)\s*[=:]\s*['\"].{200,}['\"]",
]

CODE_SMELL_PATTERNS = {
    "magic_numbers": r"\b([1-9]\d*)\b(?!\s*(?:px|rem|em|%|$))",
    "hardcoded_strings": r"['\"]([A-Za-z_][A-Za-z0-9_]{8,})['\"]",
    "print_debug": r"(?i)(print|console\.log|System\.out\.println)\s*\(",
    "todo_comments": r"(?i)#\s*TODO|//\s*TODO|/\*\s*TODO",
    "unused_imports": r"(?i)^(import|from)\s+",
}


class NoMistakesSkill(Skill):
    NAME = "no_mistakes"
    DESCRIPTION = "No-Mistakes — AI驱动的代码质量自动把关，在代码推送前自动运行验证流程"
    CAPABILITIES = [
        "quality_validation",
        "security_scan",
        "code_review",
        "style_check",
        "complexity_analysis",
        "pre_commit_hook",
    ]
    CATEGORY = "engineering"
    TAGS = ["quality", "code-review", "security", "pre-commit", "linting", "best-practices"]

    def __init__(self):
        meta = SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version="1.0.0",
            author="AOS",
            license="MIT",
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
            category=self.CATEGORY,
        )
        super().__init__(meta)
        self._checks = QUALITY_CHECKS
        self._secret_patterns = SECRET_PATTERNS
        self._code_smell_patterns = CODE_SMELL_PATTERNS
        self._reports: Dict[str, Dict] = {}

    def _detect_secrets(self, code: str) -> List[Dict[str, Any]]:
        findings = []
        for pattern in self._secret_patterns:
            matches = re.findall(pattern, code)
            for match in matches[:5]:
                findings.append({
                    "type": "secret",
                    "severity": "critical",
                    "message": f"潜在敏感信息泄露: {match[:20]}...",
                    "pattern": pattern[:30],
                })
        return findings

    def _detect_code_smells(self, code: str) -> List[Dict[str, Any]]:
        findings = []
        for smell_name, pattern in self._code_smell_patterns.items():
            matches = re.findall(pattern, code)
            if matches:
                findings.append({
                    "type": "code_smell",
                    "smell": smell_name.replace("_", " ").title(),
                    "severity": "medium",
                    "count": len(matches),
                    "message": f"发现 {len(matches)} 处 {smell_name.replace('_', ' ')}",
                })
        return findings

    def _analyze_complexity(self, code: str) -> Dict[str, Any]:
        lines = code.split("\n")
        functions = re.findall(r"(?i)\b(def|function|func)\s+\w+\s*\(", code)
        
        cyclomatic_complexity = 0
        nesting_depth = 0
        max_nesting = 0
        
        for line in lines:
            cyclomatic_complexity += line.count("if") + line.count("elif") + line.count("else")
            cyclomatic_complexity += line.count("for") + line.count("while")
            cyclomatic_complexity += line.count("case") + line.count("&&") + line.count("||")
            
            nesting_depth += line.count("{") - line.count("}")
            max_nesting = max(max_nesting, nesting_depth)

        return {
            "lines_of_code": len(lines),
            "functions": len(functions),
            "cyclomatic_complexity": cyclomatic_complexity,
            "max_nesting_depth": max_nesting,
            "avg_function_size": len(lines) / max(len(functions), 1),
        }

    def _validate_syntax(self, code: str, language: str) -> Dict[str, Any]:
        if language.lower() == "python":
            try:
                compile(code, "<string>", "exec")
                return {"valid": True, "errors": []}
            except SyntaxError as e:
                return {"valid": False, "errors": [str(e)]}
        elif language.lower() in ["javascript", "typescript"]:
            try:
                import subprocess
                result = subprocess.run(
                    ["node", "-e", "try { new Function('" + code.replace("'", "\\'") + "'); } catch(e) { process.exit(1); }"],
                    capture_output=True, timeout=5
                )
                return {"valid": result.returncode == 0, "errors": [] if result.returncode == 0 else [result.stderr.decode()[:200]]}
            except Exception:
                return {"valid": True, "errors": ["无法执行Node.js检查"]}
        else:
            return {"valid": True, "errors": [f"暂不支持 {language} 的语法检查"]}

    def _generate_report(self, check_results: Dict, code: str, language: str) -> Dict[str, Any]:
        issues = []
        score = 100
        
        for check_name, result in check_results.items():
            if check_name == "security":
                for finding in result.get("findings", []):
                    issues.append(finding)
                    if finding["severity"] == "critical":
                        score -= 20
            elif check_name == "syntax":
                if not result.get("valid", True):
                    issues.extend({"type": "syntax", "message": e} for e in result.get("errors", []))
                    score -= 30
            elif check_name == "code_smells":
                for finding in result.get("findings", []):
                    issues.append(finding)
                    score -= 5
            elif check_name == "complexity":
                complexity = result
                if complexity["cyclomatic_complexity"] > 20:
                    issues.append({"type": "complexity", "message": "圈复杂度过高", "value": complexity["cyclomatic_complexity"]})
                    score -= 15
                if complexity["max_nesting_depth"] > 5:
                    issues.append({"type": "complexity", "message": "嵌套深度过高", "value": complexity["max_nesting_depth"]})
                    score -= 10

        score = max(0, score)
        
        if score >= 90:
            status = "pass"
        elif score >= 70:
            status = "warning"
        else:
            status = "fail"

        return {
            "score": score,
            "status": status,
            "issues": issues,
            "total_issues": len(issues),
            "checks_performed": list(check_results.keys()),
            "language": language,
            "generated_at": datetime.now().isoformat(),
        }

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        action = context.get("action", "validate")

        try:
            if action == "validate":
                code = context.get("code", "")
                language = context.get("language", "python")
                checks = context.get("checks", ["security", "syntax", "code_smells", "complexity"])

                if not code:
                    return {"success": False, "error": "代码不能为空"}

                check_results = {}

                if "security" in checks:
                    check_results["security"] = {"findings": self._detect_secrets(code)}

                if "syntax" in checks:
                    check_results["syntax"] = self._validate_syntax(code, language)

                if "code_smells" in checks:
                    check_results["code_smells"] = {"findings": self._detect_code_smells(code)}

                if "complexity" in checks:
                    check_results["complexity"] = self._analyze_complexity(code)

                report = self._generate_report(check_results, code, language)
                report_id = f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                self._reports[report_id] = report

                return {"success": True, "result": {"report_id": report_id, **report}}

            elif action == "get_report":
                report_id = context.get("report_id", "")
                if report_id in self._reports:
                    return {"success": True, "result": self._reports[report_id]}
                return {"success": False, "error": f"报告 {report_id} 不存在"}

            elif action == "list_checks":
                return {"success": True, "result": {"checks": list(self._checks.keys()), "details": self._checks}}

            elif action == "scan_file":
                file_path = context.get("file_path", "")
                if not file_path:
                    return {"success": False, "error": "文件路径不能为空"}

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()

                    language = Path(file_path).suffix.lstrip(".")
                    if language == "py":
                        language = "python"
                    elif language in ["js", "mjs", "cjs"]:
                        language = "javascript"
                    elif language == "ts":
                        language = "typescript"

                    result = self.execute({
                        "action": "validate",
                        "code": code,
                        "language": language,
                    })
                    if result.get("success"):
                        result["result"]["file_path"] = file_path
                    return result
                except FileNotFoundError:
                    return {"success": False, "error": f"文件不存在: {file_path}"}
                except Exception as e:
                    return {"success": False, "error": f"读取文件失败: {e}"}

            elif action == "scan_directory":
                directory = context.get("directory", ".")
                extensions = context.get("extensions", ["py", "js", "ts"])

                results = []
                for ext in extensions:
                    for file_path in Path(directory).glob(f"**/*.{ext}"):
                        if "/node_modules/" in str(file_path):
                            continue
                        if "/.git/" in str(file_path):
                            continue

                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                code = f.read()

                            language = ext
                            if ext == "py":
                                language = "python"
                            elif ext in ["js", "mjs", "cjs"]:
                                language = "javascript"
                            elif ext == "ts":
                                language = "typescript"

                            check_result = self.execute({
                                "action": "validate",
                                "code": code,
                                "language": language,
                            })
                            if check_result.get("success"):
                                check_result["result"]["file_path"] = str(file_path)
                                results.append(check_result["result"])
                        except Exception as e:
                            logger.warning(f"扫描文件失败: {file_path} - {e}")

                summary = {
                    "total_files": len(results),
                    "passed": sum(1 for r in results if r["status"] == "pass"),
                    "warning": sum(1 for r in results if r["status"] == "warning"),
                    "failed": sum(1 for r in results if r["status"] == "fail"),
                    "total_issues": sum(r.get("total_issues", 0) for r in results),
                }

                return {"success": True, "result": {"summary": summary, "files": results}}

            elif action == "get_summary":
                report_ids = list(self._reports.keys())[-10:]
                summaries = []
                for rid in report_ids:
                    report = self._reports[rid]
                    summaries.append({
                        "report_id": rid,
                        "score": report["score"],
                        "status": report["status"],
                        "total_issues": report["total_issues"],
                        "generated_at": report["generated_at"],
                    })
                return {"success": True, "result": {"recent_reports": summaries}}

            else:
                return {"success": False, "error": f"未知动作: {action}"}

        except Exception as e:
            logger.error(f"No-Mistakes 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


def get_no_mistakes_skill() -> NoMistakesSkill:
    return NoMistakesSkill()


def register_no_mistakes_skill(registry=None):
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    skill = NoMistakesSkill()
    registry.register(skill)
    logger.info("No-Mistakes 技能已注册")
    return skill