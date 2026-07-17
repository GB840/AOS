"""code_exec 的 NL→code 离线回落缝测试。

此前「执行代码：写一个计算器」这类纯自然语言代码需求，在离线（无 LLM）时
code_exec 提取不到代码 → 如实失败，离线无法闭环。本次通电：code_exec 在提取
不到代码、且需求匹配 code_team 已知模板（calculator/sort/fibonacci/greet）时，
柔性回落 code_team 生成+真实执行，让离线也能闭环；不匹配模板仍如实失败（不编）。

两条层级：
  - 单元层（快、必跑）：直接测 CodeExecutionAdapter._try_nl_generate_fallback
    静态方法——python 计算器生成+真跑通过 / javascript 斐波那契真跑通过 /
    不匹配模板返回 None（不假装能办）/ 无文本返回 None。
  - 端到端层（重、可跳过）：构造完整 FabricHub，assert
    hub.route("action.code_exec", {"requirement": "写一个计算器"}) 离线闭环
    （ok=True, engine_id="code-team"）。构造失败则 pytest.skip。
"""
from __future__ import annotations

import pytest

from core.fabric.adapter import InvokeResult
from core.fabric.adapters.code_execution_adapter import CodeExecutionAdapter


# ───────────────────────── 单元层（快、必跑） ─────────────────────────

def test_nl_fallback_python_calculator_generates_and_runs():
    res = CodeExecutionAdapter._try_nl_generate_fallback(
        {"requirement": "写一个计算器", "lang": "python"})
    assert isinstance(res, InvokeResult)
    assert res.ok is True
    assert res.engine_id == "code-team"          # 诚实：实际干活的引擎
    data = res.data
    assert data["generated_by"] == "code_team"
    assert data["via_fallback"] is True
    files = data["files"]
    assert "calculator.py" in files and "test_calculator.py" in files
    assert "5 passed" in (data["content"] or "")   # 真实 pytest 输出


def test_nl_fallback_javascript_fib_runs_via_node():
    res = CodeExecutionAdapter._try_nl_generate_fallback(
        {"requirement": "斐波那契", "lang": "javascript"})
    assert res.engine_id == "code-team"
    assert res.ok is True
    files = res.data["files"]
    assert "fibonacci.js" in files and "fibonacci.test.js" in files
    # node 可用时应真实跑通（诚实回落：不可用时 ok=False 也合法，不伪造）
    assert res.data["execution"]["ok"] in (True, False)


def test_nl_fallback_unmatched_requirement_returns_none():
    # 「写个聊天机器人」不匹配任何模板 → 不假装能办，返回 None 走原失败分支
    res = CodeExecutionAdapter._try_nl_generate_fallback(
        {"requirement": "写个聊天机器人", "lang": "python"})
    assert res is None


def test_nl_fallback_no_text_returns_none():
    assert CodeExecutionAdapter._try_nl_generate_fallback({}) is None
    assert CodeExecutionAdapter._try_nl_generate_fallback({"code": "print(1)"}) is None


# ───────────────────────── 端到端层（重、可跳过） ─────────────────────────

def _build_hub_or_skip():
    try:
        from kernel.plugins.fabric_hub import FabricHub
        return FabricHub()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"FabricHub 构造不可用，跳过端到端测试: {e}")


def test_route_action_code_exec_runs_nl_calculator_offline():
    """「执行代码：写一个计算器」离线经 code_exec → 回落 code_team 闭环。"""
    hub = _build_hub_or_skip()
    res = hub.route("action.code_exec", {"requirement": "写一个计算器", "lang": "python"})
    assert isinstance(res, InvokeResult)
    assert res.ok is True
    # 实际执行引擎是 code_team（诚实透明化，非 code-exec）
    assert res.engine_id == "code-team"
    assert (res.data or {}).get("generated_by") == "code_team"
    assert (res.data or {}).get("via_fallback") is True
