"""Autopilot 自主闭环功能测试。"""
from __future__ import annotations
import sys
sys.path.insert(0, "D:/AOS/src")
import pytest
from core.fabric.adapter import InvokeResult


def test_search_real_metrics_zero_results_fails():
    from kernel.autopilot import _search_real_metrics
    res = InvokeResult(ok=True, data={"results": [], "engine": "test"})
    metrics = _search_real_metrics(res)
    assert metrics["is_real"] is False
    assert metrics["result_count"] == 0


def test_search_real_metrics_with_results_succeeds():
    from kernel.autopilot import _search_real_metrics
    res = InvokeResult(ok=True, data={"results": [{"url": "http://example.com/1", "title": "Test 1"}], "engine": "test"})
    metrics = _search_real_metrics(res)
    assert metrics["is_real"] is True
    assert metrics["result_count"] == 1


def test_code_exec_real_metrics_empty_output_fails():
    from kernel.autopilot import _code_exec_real_metrics
    res = InvokeResult(ok=True, data={"output": ""})
    metrics = _code_exec_real_metrics(res, write_path=None)
    assert metrics["is_real"] is False


def test_code_exec_real_metrics_with_stdout_succeeds():
    from kernel.autopilot import _code_exec_real_metrics
    res = InvokeResult(ok=True, data={"output": "Hello, World!"})
    metrics = _code_exec_real_metrics(res, write_path=None)
    assert metrics["is_real"] is True
    assert metrics["stdout_len"] == 13


def test_refuse_if_dangerous_blocks_git_push():
    from kernel.autopilot import _refuse_if_dangerous
    result = _refuse_if_dangerous("git push origin main")
    assert result is not None
    assert "git push" in result


def test_refuse_if_dangerous_blocks_sudo():
    from kernel.autopilot import _refuse_if_dangerous
    result = _refuse_if_dangerous("sudo apt-get install something")
    assert result is not None
    assert "sudo" in result


def test_refuse_if_dangerous_allows_safe_command():
    from kernel.autopilot import _refuse_if_dangerous
    result = _refuse_if_dangerous("ls -la")
    assert result is None


def test_substitute_file_content_replaces_placeholder():
    from kernel.autopilot import _substitute_file_content
    code = 'open("test.txt", "w").write("...")'
    prev_text = "This is the actual content from upstream"
    result = _substitute_file_content(code, prev_text)
    assert "..." not in result
    assert "This is the actual content from upstream" in result


def test_substitute_file_content_preserves_real_content():
    from kernel.autopilot import _substitute_file_content
    code = 'open("test.txt", "w").write("Real content here")'
    prev_text = "Upstream text"
    result = _substitute_file_content(code, prev_text)
    assert "Real content here" in result


def test_build_structured_trace_includes_memory_recall():
    from kernel.autopilot import _build_structured_trace
    data = {
        "initial": {
            "memory": [
                {"text": "Related info", "score": 0.85, "ts": "2024-01-01", "task": "previous task"}
            ]
        },
        "ok_steps": 1,
        "failed_steps": 0,
    }
    trace_obj = _build_structured_trace("test task", "ag2", "plan", [], data, 1.0, [])
    assert "memory_recall" in trace_obj
    assert trace_obj["memory_recall"]["query"] == "test task"
    assert trace_obj["memory_recall"]["similarity"] == 0.85
    assert trace_obj["memory_recall"]["count"] == 1


def test_build_structured_trace_omits_memory_recall_when_empty():
    from kernel.autopilot import _build_structured_trace
    data = {
        "initial": {},
        "ok_steps": 1,
        "failed_steps": 0,
    }
    trace_obj = _build_structured_trace("test task", "ag2", "plan", [], data, 1.0, [])
    assert "memory_recall" not in trace_obj
