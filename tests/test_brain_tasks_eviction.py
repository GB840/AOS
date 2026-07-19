"""DeerFlowGatewayClient 任务记录有界淘汰测试（审计 P1-7：防长运行内存泄漏）。

DeerFlowGatewayClient.__init__ 仅设属性、无网络调用，可直接轻量构造。
_evict_terminal_tasks 在 cancel_task / cancel_subagent / submit_task._worker /
execute_subagent_async._worker 的终态处被持锁调用，仅淘汰最旧终态记录，
running 永不淘汰。
"""
import os

import pytest

from src.core.brain import DeerFlowGatewayClient


def _client_with_tasks(tasks: dict) -> DeerFlowGatewayClient:
    c = DeerFlowGatewayClient()
    c._tasks = tasks
    return c


def test_eviction_drops_oldest_terminal_keeps_running(monkeypatch):
    monkeypatch.setenv("AOS_TASK_RETENTION_MAX", "3")
    # 插入有序：t1 completed(最旧) / t2 running / t3 failed / t4 completed / t5 running(最新)
    c = _client_with_tasks({
        "t1": {"status": "completed"},
        "t2": {"status": "running"},
        "t3": {"status": "failed"},
        "t4": {"status": "completed"},
        "t5": {"status": "running"},
    })
    c._evict_terminal_tasks()
    # 仅淘汰 2 条最旧终态(t1, t3)；running(t2,t5) 与最新终态(t4) 保留
    assert "t2" in c._tasks and "t5" in c._tasks, "running 任务不得被淘汰"
    assert "t4" in c._tasks, "最新终态任务不应被淘汰"
    assert "t1" not in c._tasks and "t3" not in c._tasks, "最旧终态应被淘汰"
    assert len(c._tasks) == 3


def test_eviction_noop_under_cap(monkeypatch):
    monkeypatch.setenv("AOS_TASK_RETENTION_MAX", "10")
    c = _client_with_tasks({f"t{i}": {"status": "completed"} for i in range(5)})
    c._evict_terminal_tasks()
    assert len(c._tasks) == 5, "未超上限不应淘汰"


def test_eviction_never_drops_running_even_over_cap(monkeypatch):
    monkeypatch.setenv("AOS_TASK_RETENTION_MAX", "2")
    c = _client_with_tasks({f"r{i}": {"status": "running"} for i in range(5)})
    c._evict_terminal_tasks()
    assert len(c._tasks) == 5, "全 running 时即使超上限也不淘汰"


def test_cancel_subagent_evicts_under_lock(monkeypatch):
    monkeypatch.setenv("AOS_TASK_RETENTION_MAX", "1")
    c = DeerFlowGatewayClient()
    c._tasks = {
        "old": {"status": "completed"},
        "cur": {"status": "running"},
    }
    assert c.cancel_subagent("cur") is True
    # cur 转为 cancelled(终态)，old 为最旧终态应被淘汰，cur 保留
    assert "cur" in c._tasks
    assert "old" not in c._tasks
    assert c._tasks["cur"]["status"] == "cancelled"
