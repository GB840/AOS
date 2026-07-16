"""编排芯粒 → A2UI 可视化：转换函数 + 渲染端点的轻量测试。

全部沙箱可跑（仅依赖 a2ui 渲染器，不触发真实下游芯粒 / 网络）。
"""
import pytest

from core.fabric.adapter import InvokeResult
from core.fabric import a2ui
from kernel.plugins.orchestration_chiplet import (
    orchestration_result_to_a2ui,
    render_orchestration_result,
)


def _ok_result():
    trace = [
        {"step": 0, "capability": "bench.ping", "ok": True, "out": {"result": "pong"}},
        {"step": 1, "capability": "mem0.search", "ok": True, "out": {"hits": 3}},
    ]
    return InvokeResult(
        ok=True,
        data={"ok_steps": 2, "failed_steps": 0,
              "final": {"result": "done"}, "trace": trace},
    )


def test_orchestration_to_a2ui_success_is_valid_surface():
    surface = orchestration_result_to_a2ui(_ok_result())
    assert isinstance(surface, dict)
    # 合法 surface：validate_surface 返回空错误列表（不抛、无错误）
    assert a2ui.validate_surface(surface) == []


def test_orchestration_to_a2ui_failure_returns_none():
    # 诚实：编排失败时不伪造报告 surface
    res = InvokeResult(ok=False, error="所有步骤均失败（见 trace）")
    assert orchestration_result_to_a2ui(res) is None


def test_orchestration_to_a2ui_missing_trace_returns_none():
    # 诚实：无 trace 时不编造报告
    res = InvokeResult(ok=True, data={"ok_steps": 0, "failed_steps": 0})
    assert orchestration_result_to_a2ui(res) is None


def test_render_orchestration_result_html():
    html = render_orchestration_result(_ok_result(), standalone=True)
    assert isinstance(html, str)
    assert "a2ui-surface" in html
    # 成功报告应含各步 capability 文本
    assert "bench.ping" in html
    assert "mem0.search" in html


def test_render_orchestration_result_failure_degrades_honestly():
    fail = InvokeResult(ok=False, error="依赖的上游步骤尚未成功产出，本步无法获取输入")
    html = render_orchestration_result(fail, standalone=True)
    assert isinstance(html, str)
    assert "a2ui-surface" in html
    # 失败诚实降级为错误 surface，而非伪造成功报告
    assert "失败" in html
    assert "依赖的上游步骤尚未成功产出" in html
