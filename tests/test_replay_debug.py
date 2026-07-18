"""Replay & Debug 单元测试（Task 5）。

覆盖 workflow_runner 的：
- replay_from_step（从指定步骤重放，可限 max_steps）
- debug_step（单步调试，max_steps=1）
- compare_traces（两条 trace 静态对比）
- list_traces / get_trace（trace 查询）

设计原则：
- 不依赖真 FabricHub——用 mock route_fn 返回固定数据
- 验证非侵入性：replay 不修改原 trace 文件
- 验证错误处理：trace 不存在 / step_index 越界
"""
import json
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="aos_test_replay_")
os.environ["AOS_WORKFLOWS_DIR"] = _tmp

from kernel.studio.workflow_models import (  # noqa: E402
    Workflow,
    WorkflowRun,
    WorkflowStep,
)
from kernel.studio.workflow_runner import WorkflowRunner
from kernel.studio.workflow_store import WorkflowStore


@pytest.fixture
def store():
    """每个测试用独立的 WorkflowStore（独立目录）。"""
    sub = os.path.join(_tmp, f"s_{os.urandom(4).hex()}")
    os.makedirs(sub, exist_ok=True)
    return WorkflowStore(base_dir=sub)


@pytest.fixture
def runner(store):
    """带 mock route_fn 的 runner——不依赖 FabricHub。

    mock 行为：
    - 输出含 "fail" 的 step 返回失败
    - 其他返回成功，output 含 "mock_output" + step_name
    """
    class MockResult:
        def __init__(self, ok, data=None, error="", engine_id="mock_engine"):
            self.ok = ok
            self.data = data or {}
            self.error = error
            self.engine_id = engine_id

    def mock_route(cap, payload):
        # payload 中含 "fail" 触发失败
        if isinstance(payload, dict):
            prompt = str(payload.get("prompt", ""))
            if "fail" in prompt.lower():
                return MockResult(False, error="模拟失败")
        return MockResult(True, data={"content": f"mock_output_{cap}"})

    return WorkflowRunner(route_fn=mock_route, store=store, pulse=None)


def _make_workflow():
    """造一个 3 步的工作流。"""
    wf = Workflow.create("测试工作流", "for replay test")
    wf.add_step(capability="web.search", name="搜索", prompt="search hello")
    wf.add_step(capability="inference.llm", name="推理", prompt="llm think")
    wf.add_step(capability="output.format", name="格式化", prompt="format result")
    return wf


def _make_trace(wf, *, fail_at_step=-1):
    """造一条已完成的 trace（含 step 结果）。

    fail_at_step: 若 >=0，该步骤标记为失败。
    """
    run = WorkflowRun.create(wf.id, wf.version)
    run.status = "success" if fail_at_step < 0 else "failed"
    run.input = {"query": "test"}
    run.steps = []
    for i, step in enumerate(wf.steps):
        ok = (i != fail_at_step)
        run.steps.append({
            "step_index": i,
            "step_name": step.name,
            "capability": step.capability,
            "ok": ok,
            "output": {"content": f"output_{i}"} if ok else {},
            "error": "" if ok else "模拟失败",
            "engine": "original_engine",
            "duration": 0.1 * (i + 1),
        })
    run.duration = sum(s["duration"] for s in run.steps)
    return run


# ── list_traces / get_trace ──

def test_list_traces_empty(store, runner):
    """无运行记录时，list_traces 应返回空列表。"""
    traces = runner.list_traces()
    assert traces == []


def test_list_traces_returns_all(store, runner):
    """list_traces 应返回所有工作流的运行记录，按 started_at 倒序。"""
    wf = _make_workflow()
    store.save(wf)
    run1 = _make_trace(wf)
    run2 = _make_trace(wf)
    # 让 run2 更晚（list_traces 按 started_at 倒序）
    run2.started_at = "2099-12-31T23:59:59"
    run1.started_at = "2099-01-01T00:00:00"
    store.save_run(run1)
    store.save_run(run2)

    traces = runner.list_traces()
    assert len(traces) == 2
    # 最新的在前
    assert traces[0]["run_id"] == run2.id
    assert traces[1]["run_id"] == run1.id
    # 摘要字段应齐全
    assert traces[0]["step_count"] == 3
    assert traces[0]["status"] == "success"


def test_list_traces_filter_by_wf(store, runner):
    """list_traces 按 wf_id 过滤。"""
    wf1 = _make_workflow()
    wf2 = _make_workflow()
    store.save(wf1)
    store.save(wf2)
    store.save_run(_make_trace(wf1))
    store.save_run(_make_trace(wf2))

    traces = runner.list_traces(wf_id=wf1.id)
    assert len(traces) == 1
    assert traces[0]["workflow_id"] == wf1.id


def test_list_traces_filter_by_status(store, runner):
    """list_traces 按 status 过滤。"""
    wf = _make_workflow()
    store.save(wf)
    store.save_run(_make_trace(wf, fail_at_step=-1))  # success
    store.save_run(_make_trace(wf, fail_at_step=1))   # failed

    success_only = runner.list_traces(status="success")
    assert len(success_only) == 1
    assert success_only[0]["status"] == "success"

    failed_only = runner.list_traces(status="failed")
    assert len(failed_only) == 1
    assert failed_only[0]["status"] == "failed"


def test_get_trace_returns_full_data(store, runner):
    """get_trace 应返回完整 trace（含 steps 详细内容）。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    trace = runner.get_trace(run.id)
    assert trace is not None
    assert trace["id"] == run.id
    assert trace["workflow_id"] == wf.id
    assert len(trace["steps"]) == 3
    # steps 含详细字段（与 list_traces 的摘要不同）
    assert "output" in trace["steps"][0]


def test_get_trace_nonexistent_returns_none(store, runner):
    """查询不存在的 trace 应返回 None。"""
    assert runner.get_trace("no_such_trace") is None


# ── replay_from_step ──

def test_replay_from_step_runs_remaining_steps(store, runner):
    """从 step_index 重放，应执行该步及之后所有步骤。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.replay_from_step(run.id, step_index=1)
    assert result["ok"] is True
    assert result["replay_from"] == 1
    # 从 step 1 开始，共 2 步（step 1 + step 2）
    assert result["step_count"] == 2
    assert all(r.get("replay") for r in result["results"])
    # 每步应有 started_at
    assert all(r.get("started_at") for r in result["results"])


def test_replay_from_step_max_steps_limit(store, runner):
    """max_steps 限制重放步数。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.replay_from_step(run.id, step_index=0, max_steps=2)
    assert result["ok"] is True
    assert result["step_count"] == 2  # 只跑 2 步，不是 3 步


def test_replay_from_step_uses_mock_route(store, runner):
    """replay 应走 mock route_fn，输出含 mock_output 标记。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.replay_from_step(run.id, step_index=0)
    # mock route 返回 {"content": "mock_output_<cap>"}
    first_step = result["results"][0]
    assert first_step["ok"] is True
    assert "mock_output" in str(first_step.get("output", ""))


def test_replay_from_step_trace_not_exist(store, runner):
    """trace 不存在时应返回错误。"""
    result = runner.replay_from_step("no_such", step_index=0)
    assert result["ok"] is False
    assert "trace 不存在" in result["error"]


def test_replay_from_step_index_out_of_range(store, runner):
    """step_index 越界时应返回错误。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.replay_from_step(run.id, step_index=999)
    assert result["ok"] is False
    assert "越界" in result["error"]


def test_replay_does_not_modify_original_trace(store, runner):
    """replay 不应修改原 trace 文件（非侵入）。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    # 记录原始 trace 内容
    original = json.loads(json.dumps(store.get_run(run.id)))

    # 跑一次 replay
    runner.replay_from_step(run.id, step_index=0)

    # 原 trace 应保持不变
    after = store.get_run(run.id)
    assert after == original


def test_replay_with_override_engine(store, runner):
    """override_engine 应注入到第一步的 payload。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    # 用一个能记录 payload 的 mock route
    captured = []

    class MockResult:
        ok = True
        data = {"content": "ok"}
        error = ""
        engine_id = "test"

    def capturing_route(cap, payload):
        captured.append({"cap": cap, "payload": payload})
        return MockResult()

    runner.set_route_fn(capturing_route)

    runner.replay_from_step(run.id, step_index=0, override_engine="ollama")
    # 第一步的 payload 应含 engine=ollama
    assert captured[0]["payload"].get("engine") == "ollama"
    # 第二步不应被注入（只对 step_index 步生效）
    assert captured[1]["payload"].get("engine") != "ollama" or "engine" not in captured[1]["payload"]


# ── debug_step ──

def test_debug_step_runs_only_one_step(store, runner):
    """debug_step 只跑指定一步（max_steps=1）。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.debug_step(run.id, step_index=1)
    assert result["ok"] is True
    assert result["single_step"] is True
    assert result["step_index"] == 1
    # result 字段是单个 dict（不是列表）
    assert isinstance(result["result"], dict)
    assert result["result"]["step_index"] == 1


def test_debug_step_trace_not_exist(store, runner):
    """debug_step 不存在的 trace 应返回错误。"""
    result = runner.debug_step("no_such", step_index=0)
    assert result["ok"] is False


def test_debug_step_index_out_of_range(store, runner):
    """debug_step 越界应返回错误。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.debug_step(run.id, step_index=999)
    assert result["ok"] is False


# ── compare_traces ──

def test_compare_traces_same_workflow(store, runner):
    """对比同工作流的两次运行。"""
    wf = _make_workflow()
    store.save(wf)
    run_a = _make_trace(wf)
    run_b = _make_trace(wf, fail_at_step=1)  # 第 1 步失败
    store.save_run(run_a)
    store.save_run(run_b)

    diff = runner.compare_traces(run_a.id, run_b.id)
    assert diff["ok"] is True
    assert diff["same_workflow"] is True
    assert diff["a_step_count"] == 3
    assert diff["b_step_count"] == 3
    assert diff["a_ok_steps"] == 3
    assert diff["b_ok_steps"] == 2  # 第 1 步失败
    # 应有 step 1 的状态差异
    step1_diff = next(d for d in diff["diffs"] if d["step_index"] == 1)
    assert "status_diff" in step1_diff


def test_compare_traces_different_step_count(store, runner):
    """对比步数不同的两条 trace。"""
    wf = _make_workflow()
    store.save(wf)
    run_a = _make_trace(wf)  # 3 步
    store.save_run(run_a)

    # 造一个只有 2 步的 run_b
    run_b = _make_trace(wf)
    run_b.steps = run_b.steps[:2]
    store.save_run(run_b)

    diff = runner.compare_traces(run_a.id, run_b.id)
    assert diff["a_step_count"] == 3
    assert diff["b_step_count"] == 2
    # 应有 only_in_a 的差异
    only_in_a = [d for d in diff["diffs"] if d.get("status") == "only_in_a"]
    assert len(only_in_a) == 1
    assert only_in_a[0]["step_index"] == 2


def test_compare_traces_trace_not_exist(store, runner):
    """对比不存在的 trace 应返回错误。"""
    wf = _make_workflow()
    store.save(wf)
    run = _make_trace(wf)
    store.save_run(run)

    result = runner.compare_traces("no_such_a", run.id)
    assert result["ok"] is False
    assert "trace A 不存在" in result["error"]

    result = runner.compare_traces(run.id, "no_such_b")
    assert result["ok"] is False
    assert "trace B 不存在" in result["error"]


def test_compare_traces_duration_delta(store, runner):
    """compare 应计算 duration 差异。"""
    wf = _make_workflow()
    store.save(wf)
    run_a = _make_trace(wf)
    run_b = _make_trace(wf)
    run_a.duration = 1.5
    run_b.duration = 2.8
    store.save_run(run_a)
    store.save_run(run_b)

    diff = runner.compare_traces(run_a.id, run_b.id)
    assert diff["a_duration"] == 1.5
    assert diff["b_duration"] == 2.8
    assert diff["duration_delta"] == 1.3  # b - a


# ── 非侵入性（重要）──

def test_compare_does_not_modify_traces(store, runner):
    """compare 不应修改任一 trace。"""
    wf = _make_workflow()
    store.save(wf)
    run_a = _make_trace(wf)
    run_b = _make_trace(wf, fail_at_step=0)
    store.save_run(run_a)
    store.save_run(run_b)

    original_a = json.loads(json.dumps(store.get_run(run_a.id)))
    original_b = json.loads(json.dumps(store.get_run(run_b.id)))

    runner.compare_traces(run_a.id, run_b.id)

    assert store.get_run(run_a.id) == original_a
    assert store.get_run(run_b.id) == original_b
