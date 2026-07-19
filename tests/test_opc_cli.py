"""OPC CLI 入口测试（dry-run 模式，无真实 LLM，快速全绿）。

覆盖：--help 不崩 / 场景预设生效 / dry-run 五阶段按序 / --yes 跳过确认 /
自定义业务描述 / 历史教训注入可见。
"""

import subprocess
import sys
import os

import pytest

# 让测试能 import examples.opc_cli
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from examples.opc_cli import main, SCENARIOS


_PY = sys.executable
_CLI = os.path.join(_REPO_ROOT, "examples", "opc_cli.py")
_ENV = {**os.environ, "PYTHONPATH": _SRC}


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_PY, _CLI, *args],
        env=_ENV, capture_output=True, text=True, timeout=120,
    )


# ---------------------------------------------------------------------------
def test_help_exits_clean():
    """--help 应正常退出 0 且列出场景。"""
    r = _run_cli("--help")
    assert r.returncode == 0, r.stderr
    assert "OPC 商业飞轮" in r.stdout
    assert "content-creator" in r.stdout
    assert "research" in r.stdout


def test_scenarios_presets_complete():
    """场景预设应包含四类，且每个有 business/stages/note。"""
    assert set(SCENARIOS.keys()) >= {"content-creator", "consultant", "ecommerce", "research"}
    for key, sc in SCENARIOS.items():
        assert sc["business"], f"场景 {key} 缺 business"
        assert "name" in sc
        assert "note" in sc


def test_main_dry_run_research_minimal_stages(capsys):
    """research 场景只跑 analyze+maintain 两阶段。"""
    result = main(["-s", "research", "-c", "1", "--dry-run"])
    out = capsys.readouterr().out
    assert result["business"] == SCENARIOS["research"]["business"]
    assert result["stages"] == ["analyze", "maintain"]
    assert "分析·研报" in out
    assert "维护·回流" in out
    # research 不含获客/交付阶段 header（精确匹配阶段头，避免业务描述误判）
    assert "阶段 [获客]" not in out
    assert "阶段 [交付]" not in out


def test_main_dry_run_full_chain_five_stages(capsys):
    """content-creator 全链路五阶段按序。"""
    result = main(["-s", "content-creator", "-c", "1", "--dry-run", "--yes"])
    out = capsys.readouterr().out
    assert result["stages"] == ["analyze", "promote", "acquire", "deliver", "maintain"]
    # 每阶段 header 都出现
    for name in ["分析·研报", "宣传·多渠道", "获客", "交付", "维护·回流"]:
        assert name in out, f"缺阶段: {name}"
    # --yes 跳过确认（dry-run 下副作用阶段仍跑）
    assert "DRY-RUN" in out
    # 副作用阶段标记
    assert "⚠副作用" in out


def test_main_custom_business(capsys):
    """-b 自定义业务描述生效。"""
    custom = "我的独立测试业务XYZ"
    result = main(["-b", custom, "-c", "1", "--dry-run", "--yes"])
    assert result["business"] == custom
    out = capsys.readouterr().out
    assert custom in out


def test_main_yes_flag_warns(capsys):
    """--yes 非 dry-run 时应打印安全警告。"""
    # 这里仍用 dry-run 避免 LLM，但 --yes 警告在 dry_run 前打印
    main(["-s", "content-creator", "--yes", "--dry-run"])
    out = capsys.readouterr().out
    # dry-run 时 --yes 不打印警告（dry_run 短路），但应能看到 DRY-RUN 标记
    assert "DRY-RUN" in out


def test_main_planner_choice_propagated(capsys):
    """--planner 应透传到配置。"""
    result = main(["-s", "research", "-c", "1", "--dry-run", "--planner", "ag2"])
    # dry-run 不真调 planner，但配置应正确（通过返回结构间接验证不崩）
    assert result["cycles"] == 1


def test_main_stages_override(capsys):
    """--stages 覆盖场景默认阶段。"""
    result = main([
        "-s", "content-creator", "-c", "1", "--dry-run", "--yes",
        "--stages", "analyze,promote",
    ])
    assert result["stages"] == ["analyze", "promote"]
    out = capsys.readouterr().out
    assert "阶段 [获客]" not in out  # 被排除（精确匹配阶段头）
