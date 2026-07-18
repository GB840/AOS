"""EvalHarness 单元测试（Task 3）。

覆盖：
- 数据集 CRUD：create / list / get / delete
- 基线管理：set / get / delete / compare
- _run_case 的 6 类 check（mock _exec_task，不依赖真 FabricHub）
- EvalCase / EvalRun / CaseResult 的 to_dict / from_dict 往返
- run_dataset 端到端（mock _exec_task）

注意：避免真实 FabricHub 调用——eval_harness._exec_task 内部会
`from kernel.plugins.fabric_hub import get_fabric_hub`，测试用 monkeypatch
替换 EvalHarness._exec_task 直接返回固定数据。
"""
import json
import os
import tempfile
import time

import pytest

_tmp = tempfile.mkdtemp(prefix="aos_test_eval_")
os.environ["AOS_EVAL_DIR"] = _tmp

from kernel.eval.eval_harness import (  # noqa: E402
    CaseResult,
    EvalCase,
    EvalHarness,
    EvalRun,
    get_eval_harness,
)


@pytest.fixture
def harness():
    """每个测试用全新的 harness + 干净的 EVAL_DIR。"""
    # 重置单例
    import kernel.eval.eval_harness as emod
    emod._eval_singleton = None

    # 用独立目录避免测试间互相污染
    sub = os.path.join(_tmp, f"sub_{time.time_ns()}")
    os.environ["AOS_EVAL_DIR"] = sub
    os.makedirs(os.path.join(sub, "datasets"), exist_ok=True)
    os.makedirs(os.path.join(sub, "baselines"), exist_ok=True)
    os.makedirs(os.path.join(sub, "runs"), exist_ok=True)

    return EvalHarness()


def _make_case(**kw):
    defaults = {
        "id": f"c_{time.time_ns()}",
        "name": "测试用例",
        "task": "hello",
        "input_data": {},
        "expected_keywords": [],
        "expected_success": True,
        "expected_min_steps": 0,
        "expected_max_duration": 0.0,
        "expected_max_cost_usd": 0.0,
        "tags": [],
    }
    defaults.update(kw)
    return EvalCase(**defaults)


# ── 数据集 CRUD ──

def test_create_and_get_dataset(harness):
    """create_dataset 后，get_dataset 应返回相同的用例列表。"""
    cases = [_make_case(name="c1"), _make_case(name="c2")]
    harness.create_dataset("ds1", cases)

    loaded = harness.get_dataset("ds1")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].name == "c1"
    assert loaded[1].name == "c2"


def test_list_datasets(harness):
    """list_datasets 应列出所有已创建的数据集。"""
    harness.create_dataset("list_a", [_make_case()])
    harness.create_dataset("list_b", [_make_case(), _make_case()])

    datasets = harness.list_datasets()
    names = [d["name"] for d in datasets]
    assert "list_a" in names
    assert "list_b" in names
    # cases 字段应反映用例数
    b_info = next(d for d in datasets if d["name"] == "list_b")
    assert b_info["cases"] == 2


def test_get_nonexistent_dataset_returns_none(harness):
    """查询不存在的数据集应返回 None。"""
    assert harness.get_dataset("no_such_dataset") is None


def test_delete_dataset(harness):
    """删除数据集后，get 应返回 None。"""
    harness.create_dataset("to_delete", [_make_case()])
    assert harness.get_dataset("to_delete") is not None

    ok = harness.delete_dataset("to_delete")
    assert ok is True
    assert harness.get_dataset("to_delete") is None


def test_delete_nonexistent_dataset_returns_false(harness):
    """删除不存在的数据集应返回 False。"""
    assert harness.delete_dataset("never_existed") is False


def test_dataset_persistence_across_instances(harness):
    """数据集应持久化，新 harness 实例能读回。"""
    harness.create_dataset("persist_ds", [_make_case(name="p1")])
    # 新实例指向同一 EVAL_DIR
    e2 = EvalHarness()
    loaded = e2.get_dataset("persist_ds")
    assert loaded is not None
    assert loaded[0].name == "p1"


# ── 基线管理 ──

def _make_run(pass_rate=0.9, avg_duration=1.0, avg_cost=0.001, **kw):
    defaults = {
        "id": f"run_{time.time_ns()}",
        "dataset_name": "bl_ds",
        "started_at": "",
        "ended_at": "",
        "total_cases": 10,
        "passed_cases": 9,
        "failed_cases": 1,
        "pass_rate": pass_rate,
        "avg_duration": avg_duration,
        "avg_cost_usd": avg_cost,
        "total_tokens": 100,
        "results": [],
        "baseline_diff": {},
        "error": "",
    }
    defaults.update(kw)
    return EvalRun(**defaults)


def test_set_and_get_baseline(harness):
    """set_baseline 后，get_baseline 应返回相同数据。"""
    run = _make_run(pass_rate=0.85)
    harness.set_baseline("bl1", run)

    bl = harness.get_baseline("bl1")
    assert bl is not None
    assert bl["pass_rate"] == 0.85
    assert bl["dataset_name"] == "bl_ds"


def test_get_nonexistent_baseline_returns_none(harness):
    """查询不存在的基线应返回 None。"""
    assert harness.get_baseline("no_bl") is None


def test_delete_baseline(harness):
    """删除基线后，get 应返回 None。"""
    run = _make_run()
    harness.set_baseline("bl_del", run)
    assert harness.get_baseline("bl_del") is not None

    ok = harness.delete_baseline("bl_del")
    assert ok is True
    assert harness.get_baseline("bl_del") is None


def test_compare_baseline_no_baseline(harness):
    """无基线时，compare 应返回 has_baseline=False。"""
    run = _make_run()
    diff = harness._compare_baseline("no_compare_bl", run)
    assert diff["has_baseline"] is False
    assert diff["regressions"] == []
    assert diff["improvements"] == []


def test_compare_baseline_detects_regression(harness):
    """pass_rate 下降应被识别为退化。"""
    base_run = _make_run(pass_rate=0.9)
    harness.set_baseline("bl_reg", base_run)

    # 当前 run pass_rate 下降到 0.7
    current = _make_run(pass_rate=0.7)
    diff = harness._compare_baseline("bl_reg", current)
    assert diff["has_baseline"] is True
    assert any("pass_rate 退化" in r for r in diff["regressions"])


def test_compare_baseline_detects_improvement(harness):
    """pass_rate 上升应被识别为改善。"""
    base_run = _make_run(pass_rate=0.7)
    harness.set_baseline("bl_imp", base_run)

    current = _make_run(pass_rate=0.95)
    diff = harness._compare_baseline("bl_imp", current)
    assert diff["has_baseline"] is True
    assert any("pass_rate 改善" in r for r in diff["improvements"])


def test_compare_baseline_duration_regression(harness):
    """avg_duration 增加 50% 以上应被识别为退化。"""
    base_run = _make_run(avg_duration=1.0)
    harness.set_baseline("bl_dur", base_run)

    current = _make_run(avg_duration=2.0)  # 翻倍，超过 1.5x
    diff = harness._compare_baseline("bl_dur", current)
    assert any("avg_duration 退化" in r for r in diff["regressions"])


# ── _run_case 的 6 类 check ──

def test_run_case_all_checks_pass(harness, monkeypatch):
    """所有 check 都通过时，CaseResult.ok 应为 True。"""
    case = _make_case(
        expected_success=True,
        expected_keywords=["hello"],
        expected_min_steps=1,
        expected_max_duration=10.0,
        expected_max_cost_usd=1.0,
    )
    # mock _exec_task 返回成功 + 含 "hello" 的输出
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "hello world"}, {
            "success": True, "duration": 0.5, "ok_steps": 2,
            "failed_steps": 0, "total_tokens": 50, "cost_usd": 0.01,
        })
    )

    result = harness._run_case(case, "test")
    assert result.ok is True
    assert result.success is True
    assert len(result.checks) == 6
    assert all(c["passed"] for c in result.checks)


def test_run_case_missing_keyword_fails(harness, monkeypatch):
    """缺少期望关键词时，expected_keywords check 应失败。"""
    case = _make_case(expected_keywords=["missing_kw"])
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "hello world"}, {
            "success": True, "duration": 0.1, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 0, "cost_usd": 0.0,
        })
    )

    result = harness._run_case(case, "test")
    assert result.ok is False
    kw_check = next(c for c in result.checks if c["name"] == "expected_keywords")
    assert kw_check["passed"] is False
    assert "缺失关键词" in kw_check["detail"]


def test_run_case_unexpected_success_fails(harness, monkeypatch):
    """expected_success=False 但实际成功时，应判失败。"""
    case = _make_case(expected_success=False)
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "ok"}, {
            "success": True, "duration": 0.1, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 0, "cost_usd": 0.0,
        })
    )

    result = harness._run_case(case, "test")
    assert result.ok is False
    succ_check = next(c for c in result.checks if c["name"] == "expected_success")
    assert succ_check["passed"] is False


def test_run_case_empty_output_fails(harness, monkeypatch):
    """空字符串输出时，output_not_empty check 应失败。

    注：_extract_text({}) 会 fallback 到 json.dumps 返回 "{}"（非空），
    所以要测真正的空输出，需要让 _extract_text 返回空字符串。
    """
    case = _make_case()
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ("", {
            "success": True, "duration": 0.1, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 0, "cost_usd": 0.0,
        })
    )

    result = harness._run_case(case, "test")
    ne_check = next(c for c in result.checks if c["name"] == "output_not_empty")
    assert ne_check["passed"] is False


def test_run_case_min_steps_not_met(harness, monkeypatch):
    """ok_steps 低于 expected_min_steps 时应失败。"""
    case = _make_case(expected_min_steps=3)
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "ok"}, {
            "success": True, "duration": 0.1, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 0, "cost_usd": 0.0,
        })
    )

    result = harness._run_case(case, "test")
    step_check = next(c for c in result.checks if c["name"] == "min_success_steps")
    assert step_check["passed"] is False


def test_run_case_duration_exceeds_max(harness, monkeypatch):
    """duration 超过 expected_max_duration 时应失败。"""
    case = _make_case(expected_max_duration=1.0)
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "ok"}, {
            "success": True, "duration": 2.5, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 0, "cost_usd": 0.0,
        })
    )

    result = harness._run_case(case, "test")
    dur_check = next(c for c in result.checks if c["name"] == "max_duration")
    assert dur_check["passed"] is False


# ── run_dataset 端到端（mock _exec_task）──

def test_run_dataset_returns_run_report(harness, monkeypatch):
    """run_dataset 应返回完整的 EvalRun 报告。"""
    cases = [_make_case(name="c1"), _make_case(name="c2"), _make_case(name="c3")]
    harness.create_dataset("run_ds", cases)
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "ok output"}, {
            "success": True, "duration": 0.5, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 10, "cost_usd": 0.001,
        })
    )

    run = harness.run_dataset("run_ds")
    assert run.dataset_name == "run_ds"
    assert run.total_cases == 3
    assert run.passed_cases == 3
    assert run.failed_cases == 0
    assert run.pass_rate == 1.0
    assert run.avg_duration == 0.5
    assert run.avg_cost_usd == 0.001
    assert run.total_tokens == 30


def test_run_dataset_nonexistent_returns_error(harness):
    """跑不存在的数据集应返回 error run。"""
    run = harness.run_dataset("no_such")
    assert run.error != ""
    assert "数据集不存在" in run.error


def test_run_dataset_persists_run_report(harness, monkeypatch):
    """run_dataset 应把报告持久化到 runs/，list_runs 能查到。"""
    harness.create_dataset("persist_run_ds", [_make_case()])
    monkeypatch.setattr(
        harness, "_exec_task",
        lambda case, prefix: ({"content": "ok"}, {
            "success": True, "duration": 0.1, "ok_steps": 1,
            "failed_steps": 0, "total_tokens": 0, "cost_usd": 0.0,
        })
    )

    run = harness.run_dataset("persist_run_ds")
    # 通过 get_run 能读回
    loaded = harness.get_run(run.id)
    assert loaded is not None
    assert loaded["id"] == run.id
    # list_runs 也能查到
    runs = harness.list_runs(limit=10)
    assert any(r["id"] == run.id for r in runs)


# ── 数据往返（to_dict / from_dict）──

def test_eval_case_roundtrip():
    """EvalCase.to_dict → from_dict 应保持数据一致。"""
    case = _make_case(
        name="roundtrip",
        task="do something",
        expected_keywords=["a", "b"],
        expected_success=False,
        expected_min_steps=5,
        expected_max_duration=30.0,
        expected_max_cost_usd=0.5,
        tags=["regression", "smoke"],
    )
    d = case.to_dict()
    restored = EvalCase.from_dict(d)
    assert restored.name == "roundtrip"
    assert restored.task == "do something"
    assert restored.expected_keywords == ["a", "b"]
    assert restored.expected_success is False
    assert restored.expected_min_steps == 5
    assert restored.expected_max_duration == 30.0
    assert restored.expected_max_cost_usd == 0.5
    assert restored.tags == ["regression", "smoke"]


def test_eval_run_roundtrip():
    """EvalRun.to_dict → from_dict 应保持数据一致。"""
    run = _make_run(
        pass_rate=0.75,
        avg_duration=2.5,
        total_tokens=500,
    )
    d = run.to_dict()
    restored = EvalRun.from_dict(d)
    assert restored.id == run.id
    assert restored.pass_rate == 0.75
    assert restored.avg_duration == 2.5
    assert restored.total_tokens == 500
    assert restored.dataset_name == "bl_ds"


def test_case_result_to_dict():
    """CaseResult.to_dict 应包含所有 6 类 check。"""
    checks = [
        {"name": "expected_success", "passed": True, "detail": "ok"},
        {"name": "expected_keywords", "passed": True, "detail": "全部命中"},
        {"name": "min_success_steps", "passed": True, "detail": "ok"},
        {"name": "max_duration", "passed": True, "detail": "ok"},
        {"name": "max_cost", "passed": True, "detail": "ok"},
        {"name": "output_not_empty", "passed": True, "detail": "ok"},
    ]
    cr = CaseResult(
        case_id="c1", name="t1", ok=True, success=True, output="hello",
        duration=0.5, ok_steps=2, failed_steps=0,
        total_tokens=100, cost_usd=0.01, checks=checks,
    )
    d = cr.to_dict()
    assert d["ok"] is True
    assert d["success"] is True
    assert len(d["checks"]) == 6
    assert all(c["passed"] for c in d["checks"])
