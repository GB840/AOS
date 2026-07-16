"""质量门三分规则（compliance.QualityGate）单元测试。"""
from kernel.compliance import (
    CAT_SECURITY,
    QualityGate,
    QualityRule,
    SEV_ERROR,
    SEV_WARN,
)


def test_syntax_error_blocks():
    rep = QualityGate().run({"bad.py": "def f(:\n pass"})
    assert rep.passed is False
    assert rep.summary["ERROR"] >= 1


def test_dangerous_call_blocks():
    rep = QualityGate().run({"e.py": 'import os\nos.system("x")\n'})
    assert rep.passed is False
    sevs = [(v.severity, v.category) for v in rep.violations]
    assert (SEV_ERROR, CAT_SECURITY) in sevs


def test_bare_except_warns_not_blocks():
    rep = QualityGate().run({"x.py": "def f():\n try:\n  pass\n except:\n  pass\n"})
    assert rep.passed is True  # WARN 不阻断
    assert any(v.severity == SEV_WARN for v in rep.violations)


def test_clean_code_passes():
    code = 'def add(a, b):\n    """返回和。"""\n    return a + b\n'
    rep = QualityGate().run({"m.py": code})
    assert rep.passed is True


def test_custom_rule_extensible():
    g = QualityGate(custom_rules=[
        QualityRule("custom1", CAT_SECURITY, SEV_ERROR, "no print",
                    lambda f, c: (1, "has print") if "print(" in c else None),
    ])
    rep = g.run({"p.py": "print(1)\n"})
    assert rep.passed is False
    assert any(v.rule_id == "custom1" for v in rep.violations)


def test_summary_counts():
    rep = QualityGate().run({"a.py": "x = 1\n", "b.py": "y = 2\n"})
    assert rep.files_checked == 2
    assert rep.summary["INFO"] >= 1  # 两个文件都缺 license 头
