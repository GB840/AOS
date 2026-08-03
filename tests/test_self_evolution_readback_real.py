"""自进化闭环「写→读」读回实证（②级：代码 + 单测实证，不连外网、不谎称③）。

证明：autopilot.run() 主路径不再「只写不读」——
  run1 失败 → 写入 AdaptiveCore 持有的同一记忆实例
  run2 同任务 → 规划前 PREFLIGHT 命中已知修复 → 注入规划输入（行为输入真变）

这把「失败即训练 / 白盒才可进化」理念从「死日志」变成真正的 OODA 回调。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import kernel.autopilot as ap
from kernel.adaptive import AdaptiveCore, set_adaptive_core


class _StubResult:
    """模拟 _execute 真实返回值（InvokeResult 形态：.data 持有执行结果）。"""
    def __init__(self, data: dict) -> None:
        self.data = data


def test_autopilot_self_evolution_readback(tmp_path):
    """run1 失败记入共享记忆；run2 规划前 PREFLIGHT 命中并把已知修复注入计划输入。"""
    # 注入隔离的临时记忆库（不污染生产），run1/run2 共用同一实例 → 写读即时闭环
    core = AdaptiveCore(memory_path=str(tmp_path / "fm.json"))
    set_adaptive_core(core)

    captured = {}
    state = {"run": 0}
    orig_plan = ap._plan
    orig_exec = ap._execute
    orig_reflect = ap._reflect_and_redesign
    orig_assemble = ap._assemble

    def fake_plan(task, planner, *a, **k):
        captured["plan_task"] = task  # 捕获本轮规划看到的任务文本
        return ("fake plan", [{"capability": "action.code_exec", "description": "do it"}], None, planner)

    def fake_exec(*a, **k):
        state["run"] += 1
        if state["run"] == 1:
            # run1：执行环节返回失败（真实失败模式：超时），但不崩、不级联
            return (_StubResult({
                "trace": [{
                    "ok": False, "capability": "action.code_exec",
                    "summary": "Connection timeout occurred", "error": "timeout",
                }],
                "ok_steps": 0, "failed_steps": 1,
            }), [])
        # run2：成功
        return (_StubResult({
            "trace": [{
                "ok": True, "capability": "action.code_exec", "summary": "ok",
            }],
            "ok_steps": 1, "failed_steps": 0,
        }), [])

    def fake_assemble(task, used_planner, plan_text, steps, exe_res, cycle, start):
        # 直接产出带 trace 的结构化执行结果（不依赖真实 _assemble 的 InvokeResult 类型检查）
        data = exe_res.data if hasattr(exe_res, "data") else exe_res
        trace = data.get("trace", []) or []
        return {
            "task": task, "planner": used_planner,
            "execution": {
                "ok_steps": data.get("ok_steps", 0),
                "failed_steps": data.get("failed_steps", 0),
                "trace": [{
                    "ok": t.get("ok"), "capability": t.get("capability", ""),
                    "summary": t.get("summary", ""), "error": t.get("error", ""),
                } for t in trace],
            },
            "verdict": {"status": "ok" if data.get("failed_steps", 0) == 0 else "fail"},
            "confidence": 1.0,
        }

    def fake_reflect(*a, **k):
        return None

    ap._plan = fake_plan
    ap._execute = fake_exec
    ap._assemble = fake_assemble
    ap._reflect_and_redesign = fake_reflect
    try:
        ap.run("部署一个网站服务", planner="heuristic")
        ap.run("部署一个网站服务", planner="heuristic")
    finally:
        ap._plan = orig_plan
        ap._execute = orig_exec
        ap._assemble = orig_assemble
        ap._reflect_and_redesign = orig_reflect
        set_adaptive_core(None)

    # 1) run1 已把超时失败写入共享记忆（同源同实例）
    assert core.memory_stats["total_patterns"] >= 1, "run1 失败未写入共享记忆库"
    # 2) run2 规划输入包含 PREFLIGHT 注入的已知修复（读回生效，行为输入真变）
    assert "已知修复方案" in captured["plan_task"], "PREFLIGHT 未把已知修复注入规划输入"
    assert "网络超时" in captured["plan_task"], "注入的修复内容不是 run1 记录的根因"


def test_autopilot_preflight_no_hit_on_fresh_task(tmp_path):
    """全新任务（无历史失败）PREFLIGHT 不注入，规划输入保持原样。"""
    core = AdaptiveCore(memory_path=str(tmp_path / "fm.json"))
    set_adaptive_core(core)

    captured = {}
    orig_plan = ap._plan
    orig_exec = ap._execute
    orig_reflect = ap._reflect_and_redesign

    def fake_plan(task, planner, *a, **k):
        captured["plan_task"] = task
        return ("fake plan", [{"capability": "action.code_exec", "description": "do it"}], None, planner)

    ap._plan = fake_plan
    ap._execute = lambda *a, **k: ({"trace": [{"ok": True, "capability": "action.code_exec"}]}, [])
    ap._reflect_and_redesign = lambda *a, **k: None
    try:
        ap.run("一个从未失败过的新任务", planner="heuristic")
    finally:
        ap._plan = orig_plan
        ap._execute = orig_exec
        ap._reflect_and_redesign = orig_reflect
        set_adaptive_core(None)

    assert "已知修复方案" not in captured["plan_task"], "无历史失败时不应注入修复"
    assert captured["plan_task"] == "一个从未失败过的新任务"
