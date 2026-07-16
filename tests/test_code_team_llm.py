"""code_team 真实 LLM 接电测试。

覆盖：默认不接电(全 heuristic)、env 开但真实调用失败诚实回落、
注入桩 LLM 走全链路真跑过门、桩 LLM 生成坏代码诚实暴露失败。
全部沙箱可跑，不依赖网络/真实 key（真实失败分支用 monkeypatch 模拟）。
"""
import os

import pytest

from kernel.plugins.code_team import CodeTeamOrchestrator, make_llm_generate


def test_make_llm_generate_default_none():
    """默认（不设 AOS_CODETEAM_LLM）返回 None → code_team 全 heuristic，零破坏。"""
    # 确保环境未开启
    os.environ.pop("AOS_CODETEAM_LLM", None)
    assert make_llm_generate() is None


def test_make_llm_generate_enabled_but_real_call_fails_honest_fallback(monkeypatch):
    """env=1 但真实 LLM 调用失败（无 key/网络）→ 回落空串，不崩、不编成功。"""
    monkeypatch.setenv("AOS_CODETEAM_LLM", "1")
    # 模拟 LiteLLMAdapter.invoke 真实失败（ok=False，等同无 key/网络错）
    from core.fabric.adapter import InvokeResult
    monkeypatch.setattr(
        "core.fabric.adapters.litellm_adapter.LiteLLMAdapter.invoke",
        lambda self, req: InvokeResult(ok=False, error="simulated network/key failure"),
    )
    gen = make_llm_generate()
    # 通道可用（import 成功）→ 返回 callable（非 None）
    assert callable(gen)
    # 真实调用失败 → 诚实回落空串（executor 会真跑失败 → ok=False）
    assert gen("生成计算器", "coder") == ""


def test_code_team_injects_llm_path_and_runs_real(monkeypatch):
    """注入桩 LLM → 走 LLM 路径、files 含桩代码、executor 真实跑过质量门+测试。"""
    monkeypatch.setenv("AOS_CODETEAM_LLM", "1")

    def fake_llm(prompt: str, role: str) -> str:
        if "test_calculator.py" in prompt:
            return ("from calculator import add\n"
                    "def test_add():\n    assert add(1, 2) == 3\n")
        if "calculator.py" in prompt:
            return "def add(a, b):\n    return a + b\n"
        return ""

    orch = CodeTeamOrchestrator(llm_generate=fake_llm)
    res = orch.run("写一个 calculator 计算器", lang="python")

    # 走 LLM 路径：文件内容来自桩 LLM，而非 heuristic 模板
    assert "def add" in res["files"].get("calculator.py", "")
    assert "assert add(1, 2)" in res["files"].get("test_calculator.py", "")
    # executor 真实跑 pytest 验证（不是编的「成功」）
    assert res["execution"]["ok"] is True
    assert res["ok"] is True


def test_code_team_llm_bad_code_fails_honestly(monkeypatch):
    """桩 LLM 返回非法 Python → executor 真实编译失败 → ok=False（诚实暴露，不谎报）。"""
    monkeypatch.setenv("AOS_CODETEAM_LLM", "1")

    def bad_llm(prompt: str, role: str) -> str:
        if "test_calculator.py" in prompt:
            return "from calculator import add\ndef test_add():\n    assert add(1,2)==3\n"
        if "calculator.py" in prompt:
            return "def add(a, b):\n    return a ++\n"  # 语法错误
        return ""

    orch = CodeTeamOrchestrator(llm_generate=bad_llm)
    res = orch.run("写一个 calculator 计算器", lang="python")

    # 编译阶段真实失败（py_compile），不被掩盖
    assert res["execution"]["ok"] is False
    assert res["execution"]["stage"] == "compile"
    assert res["ok"] is False
