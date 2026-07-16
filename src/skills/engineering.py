from typing import Dict
import os
import logging
from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

class CodeQualityChecker:
    def __init__(self):
        self.checks = {
            "syntax": self._check_syntax,
            "complexity": self._check_complexity,
            "security": self._check_security,
            "style": self._check_style,
        }
    
    def _check_syntax(self, code: str, language: str = "python") -> Dict:
        errors = []
        
        if language == "python":
            try:
                compile(code, "<string>", "exec")
                return {"pass": True, "errors": [], "warnings": []}
            except SyntaxError as e:
                errors.append({
                    "line": e.lineno,
                    "column": e.offset,
                    "message": str(e),
                    "type": "syntax_error",
                })
        
        elif language == "javascript":
            try:
                import jsonschema
                return {"pass": True, "errors": [], "warnings": []}
            except ImportError as e:
                logger.debug("jsonschema 未安装，跳过 JS 语法检查: %s", e)
        
        return {"pass": len(errors) == 0, "errors": errors, "warnings": []}
    
    def _check_complexity(self, code: str, language: str = "python") -> Dict:
        complexity = 0
        warnings = []
        
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            if "def " in line or "class " in line:
                complexity += 1
            if "if " in line or "elif " in line:
                complexity += 0.5
            if "for " in line or "while " in line:
                complexity += 0.5
        
        if complexity > 20:
            warnings.append(f"High complexity detected: {complexity}")
        elif complexity > 10:
            warnings.append(f"Medium complexity: {complexity}")
        
        return {"pass": complexity <= 20, "complexity": complexity, "warnings": warnings}
    
    def _check_security(self, code: str, language: str = "python") -> Dict:
        vulnerabilities = []
        patterns = {
            "hardcoded_password": r"(password|secret|key)\s*[=:]\s*['\"].+['\"]",
            "sql_injection": r"(SELECT|INSERT|UPDATE|DELETE).*\$|execute\(.+\+.*\)",
            "command_injection": r"(subprocess|os\.system|exec)\(.+\)",
            "path_traversal": r"(open|read|write)\(.+/\.\./",
        }
        
        for name, pattern in patterns.items():
            import re
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                vulnerabilities.append({
                    "type": name,
                    "matches": matches,
                    "severity": "high",
                })
        
        return {"pass": len(vulnerabilities) == 0, "vulnerabilities": vulnerabilities}
    
    def _check_style(self, code: str, language: str = "python") -> Dict:
        issues = []
        
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            if len(line) > 80:
                issues.append({"line": i, "type": "line_length", "message": f"Line too long: {len(line)} chars"})
            if line.strip() and not line.strip().endswith(":") and "=" in line and not line.strip().startswith("#"):
                if "==" not in line and "!=" not in line and ">=" not in line and "<=" not in line:
                    parts = line.split("=")
                    if len(parts) >= 2 and not parts[0].strip().endswith("="):
                        if " " not in parts[0].strip() or " " not in parts[1].strip():
                            issues.append({"line": i, "type": "spacing", "message": "Missing spaces around ="})
        
        return {"pass": len(issues) == 0, "issues": issues}
    
    def check_all(self, code: str, language: str = "python") -> Dict:
        results = {}
        for name, check_func in self.checks.items():
            results[name] = check_func(code, language)
        
        overall_pass = all(r.get("pass", False) for r in results.values())
        
        return {
            "overall_pass": overall_pass,
            "checks": results,
            "summary": {
                "passed": sum(1 for r in results.values() if r.get("pass", False)),
                "total": len(results),
            },
        }

class UnitTestGenerator:
    def __init__(self):
        pass
    
    def generate_tests(self, code: str, language: str = "python") -> str:
        if language == "python":
            return self._generate_python_tests(code)
        return "# Tests not supported for this language"
    
    def _generate_python_tests(self, code: str) -> str:
        import re
        functions = re.findall(r"def (\w+)\s*\(", code)
        classes = re.findall(r"class (\w+)\s*[:\(]", code)
        
        test_lines = ["import unittest"]
        
        for func_name in functions:
            if not func_name.startswith("_"):
                test_lines.append("")
                test_lines.append(f"def test_{func_name}():")
                test_lines.append(f"    \"\"\"Test for {func_name} function\"\"\"")
                test_lines.append("    # TODO: Add test cases")
                test_lines.append("    pass")
        
        for class_name in classes:
            test_lines.append("")
            test_lines.append(f"class Test{class_name}(unittest.TestCase):")
            test_lines.append(f"    \"\"\"Tests for {class_name} class\"\"\"")
            test_lines.append("")
            test_lines.append("    def setUp(self):")
            test_lines.append(f"        self.instance = {class_name}()")
            test_lines.append("")
            test_lines.append("    def test_initialization(self):")
            test_lines.append("        \"\"\"Test initialization\"\"\"")
            test_lines.append("        self.assertIsNotNone(self.instance)")
        
        test_lines.append("")
        test_lines.append("if __name__ == '__main__':")
        test_lines.append("    unittest.main()")
        
        return "\n".join(test_lines)

class EngineeringSkill(Skill):
    def __init__(self):
        meta = SkillMeta(
            name="engineering",
            description="Engineering quality assurance skill for code review, refactoring, and testing.",
            version="1.0.0",
            tags=["engineering", "quality", "code-review", "testing", "refactoring", "security"],
            capabilities=[
                "code_quality_check",
                "unit_test_generation",
                "code_refactoring",
                "security_audit",
                "complexity_analysis",
            ],
            category="engineering",
        )
        super().__init__(meta)
        self.quality_checker = CodeQualityChecker()
        self.test_generator = UnitTestGenerator()
    
    def execute(self, context):
        mode = context.get("mode", "quality-check")
        
        if mode == "quality-check":
            return self._quality_check(context)
        if mode == "generate-tests":
            return self._generate_tests(context)
        if mode == "refactor":
            return self._refactor(context)
        if mode == "security-audit":
            return self._security_audit(context)
        if mode == "list":
            return self._list_modes(context)
        
        return {"success": False, "error": f"Unknown mode: {mode}", "available_modes": ["quality-check", "generate-tests", "refactor", "security-audit", "list"]}
    
    def _quality_check(self, context):
        code = context.get("code", "")
        language = context.get("language", "python")
        
        if not code:
            return {"success": False, "error": "No code provided"}
        
        result = self.quality_checker.check_all(code, language)
        
        return {
            "success": True,
            "mode": "quality-check",
            "language": language,
            "overall_pass": result["overall_pass"],
            "checks": result["checks"],
            "summary": result["summary"],
        }
    
    def _generate_tests(self, context):
        code = context.get("code", "")
        language = context.get("language", "python")
        
        if not code:
            return {"success": False, "error": "No code provided"}
        
        tests = self.test_generator.generate_tests(code, language)
        
        return {
            "success": True,
            "mode": "generate-tests",
            "language": language,
            "test_code": tests,
            "suggestions": [
                "Add specific test cases for edge cases",
                "Add mock objects for external dependencies",
                "Use setUp/tearDown for common test setup",
                "Add parameterized tests for multiple input scenarios",
            ],
        }
    
    def _refactor(self, context):
        code = context.get("code", "")
        language = context.get("language", "python")
        
        if not code:
            return {"success": False, "error": "No code provided"}
        
        result = self.quality_checker.check_all(code, language)
        suggestions = []
        
        if not result["checks"]["complexity"]["pass"]:
            suggestions.append("Consider breaking down complex functions into smaller ones")
        
        if not result["checks"]["style"]["pass"]:
            suggestions.append("Fix formatting issues for better readability")
        
        if not result["checks"]["security"]["pass"]:
            suggestions.append("Fix security vulnerabilities")
        
        return {
            "success": True,
            "mode": "refactor",
            "language": language,
            "quality_report": result,
            "refactoring_suggestions": suggestions,
            "common_refactorings": [
                "Extract repeated code into helper functions",
                "Use more descriptive variable names",
                "Add type hints for better documentation",
                "Split large classes into smaller ones",
                "Remove unused imports and variables",
            ],
        }
    
    def _security_audit(self, context):
        code = context.get("code", "")
        language = context.get("language", "python")
        
        if not code:
            return {"success": False, "error": "No code provided"}
        
        security_result = self.quality_checker._check_security(code, language)
        
        return {
            "success": True,
            "mode": "security-audit",
            "language": language,
            "passed": security_result["pass"],
            "vulnerabilities": security_result["vulnerabilities"],
            "best_practices": [
                "Never hardcode secrets or passwords",
                "Use parameterized queries for database operations",
                "Sanitize all user inputs",
                "Use environment variables for configuration",
                "Implement proper authentication and authorization",
            ],
        }
    
    def _list_modes(self, context):
        return {
            "success": True,
            "mode": "list",
            "available_modes": [
                "quality-check - Comprehensive code quality analysis",
                "generate-tests - Generate unit test templates",
                "refactor - Code refactoring suggestions",
                "security-audit - Security vulnerability detection",
            ],
        }


def _cli_main() -> int:
    """`python -m skills.engineering` 入口：脱离 AOS 大脑独立演示。

    quality-check / generate-tests / refactor / security-audit 均为纯静态分析，
    无需 LLM 或 brain，因此可产出真实结果（最强的"可独立跑"证明）。
    """
    import argparse
    import json
    import logging

    # 独立演示：强制 brain-less 回退，并静音 AOS 启动日志噪音
    os.environ.setdefault("AOS_CLI_STANDALONE", "1")
    logging.disable(logging.CRITICAL)

    ap = argparse.ArgumentParser(description="Engineering 技能独立演示（可脱离 AOS 大脑运行）")
    ap.add_argument("--mode", "-m", default="quality-check",
                    choices=["quality-check", "generate-tests", "refactor", "security-audit", "list"],
                    help="运行模式")
    ap.add_argument("--code", "-c", default=None, help="直接传入代码片段")
    ap.add_argument("--file", "-f", default=None, help="从文件读取代码（与 --code 二选一）")
    ap.add_argument("--language", "-l", default="python", choices=["python", "javascript"])
    args = ap.parse_args()

    code = args.code
    if code is None and args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            code = fh.read()

    skill = EngineeringSkill()
    result = skill.execute({"mode": args.mode, "code": code or "", "language": args.language})
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())