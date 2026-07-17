"""「think→do」闭环：route 回填执行引擎 + 预测器真实流量训练（离线验证）。

本文件验证两件事：
  A. route() 把**实际执行引擎 id** 回填进 InvokeResult（理念6：诚实呈现
     「哪个引擎跑的」）；编排 trace 与 A2UI 报告据此显示真相（不再 engine=None）。
  B. 编排流水线（hub.run_task, planner=heuristic）的真实流量会训练路由预测器
     （record_outcome 累计样本，sample_count 增长）。

关于离线限制（诚实，非 bug）：heuristic 规划把自然语言任务交给 action.code_exec
时，若没有 LLM 桥接生成代码、且任务本身不含代码块，code_exec 会**如实失败**
（"未能从输入提取可执行代码"）——这是正确降级，下游步骤因此被阻断（语义空转已
阻止）。本测试不要求 ok_steps>=1，只验证「引擎可追溯 + 预测器被训练」这一层。

重型说明：FabricHub() 构造较重（注册全部默认芯粒 + 健康探测），故构造失败则
skip；不阻断整体测试。
"""
import os

import pytest

from core.fabric.adapter import InvokeResult
from core.fabric import a2ui

# 离线、无 key、learned 策略（让预测器参与训练）；关记忆召回（避免 mem0 慢初始化）
os.environ.setdefault("AOS_ROUTE_STRATEGY", "learned")
os.environ.setdefault("AOS_MEM0_LOCAL", "1")
os.environ.setdefault("AOS_TASK_MEMORY", "0")


# ── 纯单元：不依赖重型 hub，验证 InvokeResult 契约与 A2UI 显示 ──

def test_invoke_result_has_engine_id_field():
    """InvokeResult 新增 engine_id 字段，默认 None，可赋值。"""
    r = InvokeResult(ok=True, data={})
    assert hasattr(r, "engine_id")
    assert r.engine_id is None
    r.engine_id = "code-exec"
    assert r.engine_id == "code-exec"


def test_a2ui_report_shows_engine():
    """编排报告应展示每步的实际执行引擎（@engine 标签）。"""
    trace = [
        {"step": 0, "capability": "action.code_exec", "engine": "code-exec",
         "ok": True, "out": "55"},
        {"step": 1, "capability": "inference.llm", "engine": None,
         "ok": False, "error": "no key"},
    ]
    surface = a2ui.build_a2ui_report(trace, ok_steps=1, failed_steps=1)
    assert a2ui.validate_surface(surface) == []
    html = a2ui.render_html(surface, standalone=True)
    # 真实执行引擎应出现在报告里
    assert "code-exec" in html
    assert "@code-exec" in html


# ── 端到端：需要构造重型 hub（失败则 skip）──

def _build_hub_or_skip():
    try:
        from kernel.plugins.fabric_hub import FabricHub
        hub = FabricHub()
    except Exception as e:  # pragma: no cover - 环境不可构造时跳过
        pytest.skip(f"FabricHub 构造不可用，跳过端到端测试: {e}")
    return hub


def test_run_task_trace_records_engine_id():
    """编排流水线的 trace 必须记录真实执行引擎（engine 字段非空）。"""
    hub = _build_hub_or_skip()
    task = "用 Python 执行代码计算 1 到 10 的和并打印结果"
    res = hub.run_task(task, planner="heuristic")
    execution = res.get("execution") or {}
    trace = execution.get("trace") or []
    assert trace, "trace 不应为空"
    # 关键断言：route() 已把真实执行引擎写回 trace（不再 engine=None/缺失）
    for step in trace:
        assert "engine" in step, f"trace 步缺 engine 字段: {step}"
    engines = {s.get("engine") for s in trace}
    assert any(engines), f"未记录任何真实执行引擎: {engines}"


def test_run_task_predictor_trained_by_real_traffic():
    """编排流水线的真实流量会训练路由预测器（record_outcome 累计样本）。"""
    hub = _build_hub_or_skip()
    before = hub._registry.predictor_diagnostics().get("sample_count", 0)
    task = "用 Python 执行代码打印 hello world"
    hub.run_task(task, planner="heuristic")
    after = hub._registry.predictor_diagnostics().get("sample_count", 0)
    assert after > before, f"预测器样本应随真实流量增长: {before} -> {after}"
