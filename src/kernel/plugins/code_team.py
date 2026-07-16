"""多智能体代码团队 —— 借鉴华为云码道(CodeArts) Agent Team 的协作生成思路。

把「自然语言需求 → 可运行代码」拆成四个角色协作（对应 CodeArts 的代码智能体团队）：

  - architect（架构师）：把需求拆成文件级任务（plan）
  - coder（工程师）：  为每个文件生成代码（code）
  - reviewer（审查员）：对每个文件跑三分质量门（gate）
  - executor（执行器）：在隔离临时目录里真实跑 pytest / py_compile 验证（execute）

设计原则（与 AOS 现有「ag2→ollama→heuristic 降级」一致）：
  - LLM 生成是可注入的（llm_generate(prompt, role)）；未注入时走 heuristic 生成器，
    保证无 GPU / 无 key 的沙箱环境仍能产出**可运行、过质量门**的代码，真跑验证不编。
  - 质量门复用 kernel.compliance.QualityGate（安全/质量/合规 × ERROR/WARN/INFO）。
  - 执行验证默认用隔离临时目录 + 真实 subprocess（与 code_execution_adapter 的沙箱
    隔离理念一致，但适配多文件测试场景）。

这不是把 CodeArts 整体搬进来（那违反「零付费 / 主权在己」），而是借其「多角色协作写代码」
的编排形态，落到 AOS 已有的 SubAgentRegistry / OrchestrationChiplet / compliance 之上。
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional

from kernel.compliance import QualityGate

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Heuristic 代码生成器（无 LLM 时的降级，保证可运行、过质量门）
# ═══════════════════════════════════════════════════════════════════

def _mod_calculator(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 四则运算。

由 AOS 多智能体代码团队（heuristic 模式）生成的安全脚手架。
"""


def add(left: float, right: float) -> float:
    """返回两数之和。"""
    return left + right


def subtract(left: float, right: float) -> float:
    """返回两数之差。"""
    return left - right


def multiply(left: float, right: float) -> float:
    """返回两数之积。"""
    return left * right


def divide(left: float, right: float) -> float:
    """返回两数之商；除零安全返回 0.0。"""
    if right == 0:
        return 0.0
    return left / right
'''


def _test_calculator(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import add, subtract, multiply, divide


def test_add():
    assert add(1, 2) == 3


def test_subtract():
    assert subtract(5, 3) == 2


def test_multiply():
    assert multiply(2, 4) == 8


def test_divide():
    assert divide(8, 2) == 4


def test_divide_zero():
    assert divide(1, 0) == 0.0
'''


def _mod_sort(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 排序工具。"""
from typing import List


def bubble_sort(items: List[float]) -> List[float]:
    """返回升序排列的新列表（不修改入参）。"""
    result = list(items)
    for i in range(len(result)):
        for j in range(len(result) - i - 1):
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
    return result
'''


def _test_sort(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import bubble_sort


def test_sort_basic():
    assert bubble_sort([3, 1, 2]) == [1, 2, 3]


def test_sort_empty():
    assert bubble_sort([]) == []
'''


def _mod_fib(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 斐波那契。"""
def fibonacci(n: int) -> int:
    """返回第 n 项斐波那契数（n 从 0 开始）。"""
    if n < 0:
        return 0
    if n < 2:
        return n
    prev, curr = 0, 1
    for _ in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr
'''


def _test_fib(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import fibonacci


def test_fib():
    assert [fibonacci(i) for i in range(7)] == [0, 1, 1, 2, 3, 5, 8]
'''


def _mod_greet(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 问候。"""
def greet(name: str) -> str:
    """返回对 name 的问候语。"""
    return f"Hello, {{name}}!"
'''


def _test_greet(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import greet


def test_greet():
    assert greet("AOS") == "Hello, AOS!"
'''


def _mod_default(base: str, requirement: str = "") -> str:
    summary = requirement.strip().replace('"', "'")[:80] or "未提供需求描述"
    return f'''"""{base} 模块。

需求：{summary}

由 AOS 多智能体代码团队（heuristic 模式）生成的通用脚手架。
"""


def main() -> str:
    """返回模块标识。"""
    return "{base}"


if __name__ == "__main__":
    print(main())
'''


def _test_default(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import main


def test_main():
    assert main() == "{base}"
'''


def _resolve(requirement: str) -> Optional[tuple]:
    """返回 (base文件名, mod生成器, test生成器) 或 None。"""
    r = requirement.lower()
    if any(k in r for k in ("calculator", "计算器", "加减乘除", "四则")):
        return "calculator", _mod_calculator, _test_calculator
    if any(k in r for k in ("sort", "排序", "冒泡")):
        return "sorter", _mod_sort, _test_sort
    if any(k in r for k in ("fib", "斐波那契", "fibonacci")):
        return "fibonacci", _mod_fib, _test_fib
    if any(k in r for k in ("hello", "greet", "问候", "打招呼")):
        return "greeter", _mod_greet, _test_greet
    return None


# ═══════════════════════════════════════════════════════════════════
# 默认执行器 —— 隔离临时目录 + 真实 pytest / py_compile
# ═══════════════════════════════════════════════════════════════════

def _default_executor(files: Dict[str, str]) -> Dict[str, Any]:
    """把 {文件名: 代码} 写到隔离临时目录，真实跑编译 + 测试。

    返回 {ok, stage, output, error}。优先跑 test_* 文件（pytest），
    否则跑主模块的 __main__。
    """
    import os
    d = tempfile.mkdtemp(prefix="aos_codeteam_")
    try:
        for name, code in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(code)

        # 1) 语法/编译校验
        for name in files:
            r = subprocess.run(
                [sys.executable, "-m", "py_compile", os.path.join(d, name)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return {"ok": False, "stage": "compile",
                        "error": f"{name} 编译失败", "detail": r.stderr}

        # 2) 测试 / 运行
        test_files = [n for n in files if n.startswith("test_")]
        if test_files:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", d],
                capture_output=True, text=True, timeout=60,
            )
            return {
                "ok": r.returncode == 0, "stage": "test",
                "output": r.stdout[-1600:], "error": r.stderr[-1600:],
            }
        mains = [n for n in files if not n.startswith("test_")]
        if mains:
            r = subprocess.run(
                [sys.executable, mains[0]], cwd=d,
                capture_output=True, text=True, timeout=30,
            )
            return {"ok": r.returncode == 0, "stage": "run",
                    "output": r.stdout, "error": r.stderr}
        return {"ok": True, "stage": "none", "output": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "exception", "error": str(e)}
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 编排器
# ═══════════════════════════════════════════════════════════════════

class CodeTeamOrchestrator:
    """多智能体代码团队编排器。

    四角色：architect（plan）/ coder（code）/ reviewer（gate）/ executor（execute）。
    llm_generate 可注入：(prompt: str, role: str) -> str；未注入走 heuristic。
    """

    ROLES = ["architect", "coder", "reviewer", "executor"]

    def __init__(self,
                 llm_generate: Optional[Callable[[str, str], str]] = None,
                 quality_gate: Optional[QualityGate] = None,
                 executor: Optional[Callable[[Dict[str, str]], Dict[str, Any]]] = None):
        self._llm = llm_generate
        self._gate = quality_gate or QualityGate()
        self._exec = executor or _default_executor

    # ── architect ──
    def _base_name(self, requirement: str) -> str:
        resolved = _resolve(requirement)
        if resolved:
            return resolved[0]
        m = re.search(r"[a-zA-Z][a-zA-Z0-9_]+", requirement)
        base = (m.group(0) if m else "module").lower()
        return re.sub(r"[^a-z0-9_]", "_", base)[:20] or "module"

    def _plan(self, requirement: str, lang: str) -> List[str]:
        base = self._base_name(requirement)
        return [f"{base}.py", f"test_{base}.py"]

    # ── coder ──
    def _generate(self, fname: str, requirement: str, lang: str) -> str:
        if self._llm is not None:
            prompt = (
                f"你是一个资深软件工程师（coder 角色）。\n"
                f"需求：{requirement}\n请生成文件 `{fname}` 的完整代码"
                f"（Python，含 docstring，不要使用 eval/exec/os.system 等危险调用，"
                f"不要裸 except）。只返回代码本身。"
            )
            return self._llm(prompt, "coder")
        base = self._base_name(requirement)
        is_test = fname.startswith("test_")
        resolved = _resolve(requirement)
        if resolved:
            _, mod_fn, test_fn = resolved
        else:
            mod_fn, test_fn = _mod_default, _test_default
        return (test_fn(base, requirement) if is_test
                else mod_fn(base, requirement))

    # ── 主流程 ──
    def run(self, requirement: str, lang: str = "python") -> Dict[str, Any]:
        plan = self._plan(requirement, lang)
        files: Dict[str, str] = {}
        for fname in plan:
            files[fname] = self._generate(fname, requirement, lang)

        # reviewer：三分质量门
        report = self._gate.run(files)
        # executor：真实跑测试
        exec_res = self._exec(files)

        return {
            "requirement": requirement,
            "lang": lang,
            "roles": self.ROLES,
            "plan": plan,
            "files": files,
            "quality": report.to_dict(),
            "execution": exec_res,
            "ok": report.passed and bool(exec_res.get("ok", False)),
        }


def run_code_team(requirement: str, lang: str = "python", **kw) -> Dict[str, Any]:
    """模块级便捷函数。"""
    return CodeTeamOrchestrator(**kw).run(requirement, lang=lang)


__all__ = [
    "CodeTeamOrchestrator",
    "run_code_team",
    "QualityGate",
]
