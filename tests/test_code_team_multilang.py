"""多语言代码团队（code_team 多语言扩展）测试。

覆盖：
- Python 行为向后兼容（默认语言不变）；
- JavaScript 真跑（node --check + node --test），非模拟；
- 语言别名归一化（js/node → javascript，py → python）；
- 不支持的语言诚实回落（不伪造产物/通过）；
- 质量门对 JS 文件不再用 Python AST 误判（compliance 多语言修复）。

node 不可用时，JS 真跑用例会 skip（诚实，不假装通过）。
"""
import shutil

import pytest

from kernel.plugins.code_team import (
    CodeTeamOrchestrator,
    run_code_team,
    supported_languages,
)

_HAS_NODE = shutil.which("node") is not None
_need_node = pytest.mark.skipif(not _HAS_NODE, reason="node 运行时不可用")


def test_supported_languages():
    langs = supported_languages()
    assert "python" in langs
    assert "javascript" in langs


def test_python_backward_compatible():
    # 默认语言仍是 python，计划文件名与旧行为一致。
    res = run_code_team("写一个 python 计算器，支持加减乘除")
    assert res["lang"] == "python"
    assert res["plan"] == ["calculator.py", "test_calculator.py"]
    assert res["ok"] is True


@_need_node
def test_javascript_calculator_real_run():
    res = run_code_team("写一个计算器，支持加减乘除", lang="javascript")
    assert res["lang"] == "javascript"
    assert res["plan"] == ["calculator.js", "calculator.test.js"]
    # 质量门不再因 Python AST 误判 JS 语法（关键回归点）
    assert res["quality"]["passed"] is True
    # 真实 node --test 通过
    assert res["execution"]["stage"] == "test"
    assert res["execution"]["ok"] is True
    assert res["ok"] is True


@_need_node
def test_javascript_sort_real_run():
    res = run_code_team("写一个冒泡排序", lang="js")  # 别名 js → javascript
    assert res["lang"] == "javascript"
    assert res["plan"] == ["sorter.js", "sorter.test.js"]
    assert res["execution"]["ok"] is True


@_need_node
def test_javascript_fibonacci_real_run():
    res = run_code_team("生成斐波那契数列", lang="node")  # 别名 node → javascript
    assert res["plan"] == ["fibonacci.js", "fibonacci.test.js"]
    assert res["execution"]["ok"] is True


def test_language_alias_normalization():
    res = run_code_team("hello world", lang="py")
    assert res["lang"] == "python"


def test_unsupported_language_honest_fallback():
    res = run_code_team("写点东西", lang="rust")
    assert res["ok"] is False
    assert res["execution"]["stage"] == "lang_unsupported"
    assert res["files"] == {}
    assert res["plan"] == []


def test_js_quality_gate_no_python_ast_misjudge():
    # 即使 node 不可用，也应能验证「质量门不因 JS 语法误判」这一 compliance 修复。
    def skip_exec(files):
        return {"ok": True, "stage": "skipped"}

    orch = CodeTeamOrchestrator(executor=skip_exec)
    res = orch.run("写一个计算器", lang="javascript")
    # JS 代码用 Python ast.parse 必然语法错；修复后应 passed=True
    assert res["quality"]["passed"] is True


def test_js_dangerous_call_still_blocked():
    # 非 Python 文件的危险调用（eval）应被正则兜底拦截。
    def evil_llm(prompt, role):
        return 'const x = eval("1+1");\nmodule.exports = { x };\n'

    def skip_exec(files):
        return {"ok": True, "stage": "skipped"}

    orch = CodeTeamOrchestrator(llm_generate=evil_llm, executor=skip_exec)
    res = orch.run("do eval", lang="javascript")
    assert res["quality"]["passed"] is False
