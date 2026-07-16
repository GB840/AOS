"""code_team 结果 → A2UI 可视化测试。

验证 run() 结果能正确转成 A2UI surface 并渲染为安全 HTML。
全部沙箱可跑，不依赖网络/真实 LLM（用合成的 result 字典）。
"""
from kernel.plugins.code_team import to_a2ui_surface, render_code_team
from core.fabric.a2ui import validate_surface


def _fake_result(ok: bool = True) -> dict:
    return {
        "requirement": "写一个计算器 <b>calc</b>",
        "lang": "python",
        "roles": ["architect", "coder", "reviewer", "executor"],
        "plan": ["calculator.py", "test_calculator.py"],
        "files": {
            "calculator.py": "def add(a, b):\n    return a + b\n",
            "test_calculator.py": "from calculator import add\ndef test_add():\n    assert add(1, 2) == 3\n",
        },
        "quality": {"passed": ok, "issues": [{"severity": "WARN", "msg": "缺少类型标注"}] if not ok else []},
        "execution": {
            "ok": ok,
            "stage": "test" if ok else "compile",
            "output": "1 passed" if ok else "",
            "error": "" if ok else "calculator.py 编译失败",
        },
        "ok": ok,
        "llm_used": False,
    }


def test_to_a2ui_surface_valid():
    """to_a2ui_surface 产出合法 surface（A2UI 校验通过）。"""
    surf = to_a2ui_surface(_fake_result(ok=True))
    errors = validate_surface(surf)
    assert errors == [], f"校验失败: {errors}"
    assert surf["root"] == "root"
    assert "files" in surf["components"]


def test_render_code_team_html_contains_requirement():
    """render_code_team 返回含 a2ui-surface 的 HTML，且需求文本被转义渲染。"""
    html = render_code_team(_fake_result(ok=True), standalone=True)
    assert "<div class='a2ui-surface'" in html
    # 需求含 HTML 特殊字符 <b>，渲染应被 html.escape 转义（不注入原始标签）
    assert "&lt;b&gt;" in html
    assert "<b>calc</b>" not in html  # 安全：未注入原始 HTML
    assert "代码团队" in html


def test_render_failed_result_ok():
    """失败 result（ok=False）也能渲染，不崩、含失败状态。"""
    html = render_code_team(_fake_result(ok=False), standalone=False)
    assert "<div class='a2ui-surface'" in html
    assert "✗" in html  # 失败标记
    assert "编译失败" in html  # 执行错误被诚实呈现
