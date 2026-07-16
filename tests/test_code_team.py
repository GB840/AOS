"""多智能体代码团队（code_team）单元测试。"""
from kernel.plugins.code_team import CodeTeamOrchestrator, run_code_team


def test_calculator_end_to_end():
    res = run_code_team("写一个 python 计算器，支持加减乘除")
    assert res["plan"] == ["calculator.py", "test_calculator.py"]
    assert res["quality"]["passed"] is True
    assert res["execution"]["ok"] is True
    assert res["ok"] is True


def test_sort_end_to_end():
    res = run_code_team("写一个冒泡排序算法")
    assert res["plan"] == ["sorter.py", "test_sorter.py"]
    assert res["execution"]["ok"] is True


def test_roles_present():
    orch = CodeTeamOrchestrator()
    assert orch.ROLES == ["architect", "coder", "reviewer", "executor"]


def test_quality_gate_blocks_in_pipeline():
    # 注入会生成危险代码的"伪 LLM"，并跳过真实执行（不真跑危险代码）
    def evil_llm(prompt, role):
        return 'import os\nos.system("rm -rf /")\n'

    def safe_exec(files):
        return {"ok": True, "stage": "skipped"}

    orch = CodeTeamOrchestrator(llm_generate=evil_llm, executor=safe_exec)
    res = orch.run("do something dangerous")
    assert res["quality"]["passed"] is False  # 质量门拦截
    assert res["ok"] is False


def test_llm_injection_used():
    calls = []

    def fake_llm(prompt, role):
        calls.append((role, prompt))
        return "def main():\n    return 1\n"

    orch = CodeTeamOrchestrator(llm_generate=fake_llm)
    res = orch.run("make a thing")
    assert len(calls) >= 1
    main_file = res["plan"][0]
    assert res["files"][main_file] == "def main():\n    return 1\n"


def test_executor_injection():
    captured = {}

    def fake_exec(files):
        captured["files"] = files
        return {"ok": True, "stage": "test"}

    orch = CodeTeamOrchestrator(executor=fake_exec)
    orch.run("写一个排序算法")
    assert captured["files"]  # executor 收到生成的文件


def test_fib_pattern():
    res = run_code_team("生成斐波那契数列函数")
    assert res["plan"] == ["fibonacci.py", "test_fibonacci.py"]
    assert res["execution"]["ok"] is True
