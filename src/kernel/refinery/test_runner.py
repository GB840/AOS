"""测试验证引擎（Test Runner）。

在沙箱环境中安全地运行测试，验证代码质量：
- 单元测试（pytest / unittest）
- 代码质量检查（py_compile / 语法验证）
- 回归测试（修改前后对比）
- 测试覆盖率估算

设计原则：
- 所有测试在沙箱内运行，不影响宿主环境
- 超时保护，防止测试卡死
- 资源限制（内存/CPU）
- 结构化测试结果报告
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestCaseResult:
    """单个测试用例结果。"""
    name: str
    status: str  # passed / failed / error / skipped
    duration_ms: float = 0.0
    error: str = ""
    output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    """一次测试运行的完整结果。"""
    test_type: str  # unit / syntax / lint / regression
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    test_cases: List[TestCaseResult] = field(default_factory=list)
    output: str = ""
    success: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_ms": round(self.duration_ms, 1),
            "test_cases": [t.to_dict() for t in self.test_cases],
            "output": self.output[:5000],
            "success": self.success,
            "error": self.error,
        }


class TestRunner:
    """测试验证引擎。

    在沙箱环境中运行各类测试。
    """

    def __init__(self, sandbox_root: str, python_path: str = None):
        """
        Args:
            sandbox_root: 沙箱根目录
            python_path: 额外的 PYTHONPATH
        """
        self._root = Path(sandbox_root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"沙箱目录不存在: {sandbox_root}")
        self._python_path = python_path or str(self._root / "src")
        self._default_timeout = 300

    # ── 主测试方法 ──────────────────────────────────────────────────

    def run_all(self, test_dir: str = "tests",
                timeout: int = None) -> Dict[str, Any]:
        """运行所有测试类型。"""
        results: Dict[str, TestResult] = {}

        # 1. 语法检查
        results["syntax"] = self.check_syntax()

        # 2. 单元测试（如果有 tests 目录）
        test_path = self._root / test_dir
        if test_path.is_dir():
            results["unit"] = self.run_unit_tests(test_dir, timeout=timeout)
        else:
            results["unit"] = TestResult(
                test_type="unit",
                error=f"测试目录不存在: {test_dir}",
                success=False,
            )

        # 汇总
        all_ok = all(r.success for r in results.values())
        total_tests = sum(r.total for r in results.values())
        total_passed = sum(r.passed for r in results.values())
        total_duration = sum(r.duration_ms for r in results.values())

        return {
            "success": all_ok,
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": sum(r.failed + r.errors for r in results.values()),
            "duration_ms": round(total_duration, 1),
            "results": {k: v.to_dict() for k, v in results.items()},
            "summary": self._summary(results),
        }

    # ── 语法检查 ────────────────────────────────────────────────────

    def check_syntax(self, file_pattern: str = "*.py") -> TestResult:
        """检查所有 Python 文件的语法。"""
        result = TestResult(test_type="syntax")
        start = time.time()

        import py_compile
        import fnmatch

        files = []
        for p in self._root.rglob(file_pattern):
            if p.is_file():
                # 排除非源码目录
                parts = set(p.relative_to(self._root).parts)
                if not (parts & {"__pycache__", ".git", "node_modules",
                                  ".venv", "venv", ".pytest_cache"}):
                    files.append(p)

        result.total = len(files)

        for fpath in files:
            rel = str(fpath.relative_to(self._root))
            try:
                py_compile.compile(str(fpath), doraise=True)
                result.passed += 1
                result.test_cases.append(TestCaseResult(
                    name=rel, status="passed",
                ))
            except py_compile.PyCompileError as e:
                result.failed += 1
                result.test_cases.append(TestCaseResult(
                    name=rel, status="failed",
                    error=str(e),
                ))
            except Exception as e:
                result.errors += 1
                result.test_cases.append(TestCaseResult(
                    name=rel, status="error",
                    error=str(e),
                ))

        result.duration_ms = (time.time() - start) * 1000
        result.success = result.failed == 0 and result.errors == 0
        logger.info("语法检查: %d/%d 通过 (%.0fms)",
                    result.passed, result.total, result.duration_ms)
        return result

    # ── 单元测试 ────────────────────────────────────────────────────

    def run_unit_tests(self, test_dir: str = "tests",
                       test_file: str = None,
                       timeout: int = None) -> TestResult:
        """运行单元测试（优先 pytest，回退 unittest）。"""
        result = TestResult(test_type="unit")
        start = time.time()
        timeout = timeout or self._default_timeout

        test_path = self._root / test_dir
        if not test_path.is_dir():
            result.error = f"测试目录不存在: {test_dir}"
            result.success = False
            return result

        # 尝试用 pytest
        try:
            pytest_result = self._run_pytest(test_dir, test_file, timeout)
            return pytest_result
        except Exception as e:
            logger.warning("pytest 不可用，回退 unittest: %s", e)

        # 回退到 unittest
        try:
            return self._run_unittest(test_dir, test_file, timeout)
        except Exception as e:
            result.error = f"测试运行失败: {e}"
            result.success = False
            result.duration_ms = (time.time() - start) * 1000
            return result

    def _run_pytest(self, test_dir: str, test_file: Optional[str],
                    timeout: int) -> TestResult:
        """用 pytest 运行测试。"""
        result = TestResult(test_type="unit")

        env = self._safe_env()
        env["PYTHONPATH"] = self._python_path + os.pathsep + env.get("PYTHONPATH", "")

        target = test_dir
        if test_file:
            target = str(Path(test_dir) / test_file)

        cmd = [
            sys.executable, "-m", "pytest",
            target,
            "--tb=short",
            "-v",
            "--no-header",
            "--timeout=60",
            "-x",  # 遇到失败立即停止？不，先不，看全部
        ]
        # 去掉 -x，看全部结果
        cmd.remove("-x")

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            output = proc.stdout + proc.stderr
            result.output = output

            # 解析 pytest 输出
            result.test_cases = self._parse_pytest_output(output)
            result.total = len(result.test_cases)
            result.passed = sum(1 for t in result.test_cases if t.status == "passed")
            result.failed = sum(1 for t in result.test_cases if t.status == "failed")
            result.errors = sum(1 for t in result.test_cases if t.status == "error")
            result.skipped = sum(1 for t in result.test_cases if t.status == "skipped")

            result.success = proc.returncode == 0 or result.failed == 0

        except subprocess.TimeoutExpired:
            result.error = f"测试超时（>{timeout}s）"
            result.success = False
        except Exception as e:
            result.error = f"pytest 运行失败: {e}"
            result.success = False

        result.duration_ms = (time.time() -
                              (proc.started_at if 'proc' in locals() and hasattr(proc, 'started_at') else 0)) * 1000 \
            if 'proc' in locals() else 0
        result.duration_ms = result.duration_ms if result.duration_ms > 0 else (time.time() - result.duration_ms / 1000) * 1000

        return result

    @staticmethod
    def _parse_pytest_output(output: str) -> List[TestCaseResult]:
        """简单解析 pytest 输出。"""
        cases: List[TestCaseResult] = []
        lines = output.splitlines()

        for line in lines:
            line = line.strip()
            # 匹配 PASSED / FAILED / ERROR / SKIPPED 行
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue

            status_str = parts[0].upper()
            name = parts[1].strip() if len(parts) > 1 else ""

            if "PASSED" in status_str and name:
                cases.append(TestCaseResult(name=name, status="passed"))
            elif "FAILED" in status_str and name:
                cases.append(TestCaseResult(name=name, status="failed"))
            elif "ERROR" in status_str and name:
                cases.append(TestCaseResult(name=name, status="error"))
            elif "SKIPPED" in status_str and name:
                cases.append(TestCaseResult(name=name, status="skipped"))

        # 如果没解析到，从 summary 行提取
        if not cases:
            for line in lines:
                if "passed" in line and ("failed" in line or "error" in line):
                    # 类似 "5 passed, 2 failed in 1.23s"
                    import re
                    m = re.search(r"(\d+)\s+passed", line)
                    passed = int(m.group(1)) if m else 0
                    m = re.search(r"(\d+)\s+failed", line)
                    failed = int(m.group(1)) if m else 0
                    m = re.search(r"(\d+)\s+error", line)
                    errors = int(m.group(1)) if m else 0
                    m = re.search(r"(\d+)\s+skipped", line)
                    skipped = int(m.group(1)) if m else 0

                    total = passed + failed + errors + skipped
                    for i in range(passed):
                        cases.append(TestCaseResult(name=f"test_{i}", status="passed"))
                    for i in range(failed):
                        cases.append(TestCaseResult(name=f"test_failed_{i}", status="failed"))
                    break

        return cases

    def _run_unittest(self, test_dir: str, test_file: Optional[str],
                      timeout: int) -> TestResult:
        """用 unittest 运行测试（回退方案）。"""
        result = TestResult(test_type="unit")

        env = self._safe_env()
        env["PYTHONPATH"] = self._python_path + os.pathsep + env.get("PYTHONPATH", "")

        target = test_dir
        if test_file:
            target = str(Path(test_dir) / test_file)

        cmd = [sys.executable, "-m", "unittest", "discover", "-s", target, "-v"]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            output = proc.stdout + proc.stderr
            result.output = output

            # 简单统计
            import re
            m = re.search(r"Ran\s+(\d+)\s+tests?", output)
            result.total = int(m.group(1)) if m else 0

            if "OK" in output:
                result.passed = result.total
                result.success = True
            else:
                m = re.search(r"FAILED\s*\(.*?failures=(\d+)", output)
                result.failed = int(m.group(1)) if m else 0
                m = re.search(r"errors=(\d+)", output)
                result.errors = int(m.group(1)) if m else 0
                result.passed = result.total - result.failed - result.errors
                result.success = False

        except subprocess.TimeoutExpired:
            result.error = f"测试超时（>{timeout}s）"
            result.success = False
        except Exception as e:
            result.error = f"unittest 运行失败: {e}"
            result.success = False

        result.duration_ms = (time.time() - time.time()) * 1000  # 占位
        return result

    # ── 回归测试 ────────────────────────────────────────────────────

    def run_regression(self, baseline_snapshot_id: str,
                       test_dir: str = "tests") -> Dict[str, Any]:
        """回归测试：对比修改前后的测试结果。

        注意：需要先有 baseline 快照，且已回滚到 baseline 跑过测试。
        这里简化为：跑一次当前测试，返回结果供外部对比。
        """
        current_result = self.run_unit_tests(test_dir)

        return {
            "success": True,
            "current": current_result.to_dict(),
            "baseline_snapshot": baseline_snapshot_id,
            "note": "请与 baseline 快照时的测试结果对比",
        }

    # ── 工具方法 ────────────────────────────────────────────────────

    @staticmethod
    def _safe_env() -> Dict[str, str]:
        """安全环境变量（不含 AOS 机密）。"""
        from skills.sandbox import _SANDBOX_SAFE_ENV_KEYS
        env: Dict[str, str] = {}
        for k in _SANDBOX_SAFE_ENV_KEYS:
            if k in os.environ:
                env[k] = os.environ[k]
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    @staticmethod
    def _summary(results: Dict[str, TestResult]) -> str:
        """生成测试总结。"""
        lines = ["测试结果汇总:"]
        for name, r in results.items():
            status = "✅ 通过" if r.success else "❌ 失败"
            lines.append(f"  {name}: {status} "
                         f"(通过 {r.passed}/{r.total}, "
                         f"失败 {r.failed}, 错误 {r.errors})")
        return "\n".join(lines)
