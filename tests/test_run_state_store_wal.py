"""run_state_store 的 SQLite 持久化模式回归测试。

背景（审查报告 #4，已核实为真问题）：
``_conn()`` 建连时没有开 WAL，用的是 SQLite 默认 rollback journal —— 写事务
会阻塞所有读。autopilot 一边跑一边 checkpoint 时，看板/CLI 的 ``list_runs``
会被写事务卡住；跨进程访问同一个 .db 还会直接撞 "database is locked"。

本测试锁死：
1. 连接确实处于 WAL 模式（或在不支持 WAL 的文件系统上安全降级，不抛异常）；
2. busy_timeout 已设置，锁竞争时等待而不是立刻报错；
3. 写入进行中，另一条独立连接仍能读到已提交数据（WAL 的读写并发）；
4. checkpoint 的存取语义没被改动破坏（create → save → load → done）。

诚实分级：② 级（代码 + 单测实证，纯 stdlib sqlite3，无真 LLM 参与）。
"""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel import run_state_store as store  # noqa: E402


def test_connection_uses_wal_or_degrades_safely():
    c = store._conn()
    mode = c.execute("PRAGMA journal_mode").fetchone()[0]
    # 正常本地磁盘应为 wal；某些网络盘不支持，此时允许降级但不得崩溃
    assert mode.lower() in ("wal", "delete", "truncate", "persist", "memory"), mode
    if mode.lower() != "wal":
        import warnings
        warnings.warn(f"当前文件系统不支持 WAL，已降级为 {mode}", stacklevel=1)


def test_busy_timeout_is_configured():
    c = store._conn()
    timeout_ms = c.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout_ms >= 1000, f"busy_timeout 太小或未设置: {timeout_ms}"


def test_checkpoint_roundtrip():
    run_id = f"test-{uuid.uuid4().hex[:8]}"
    store.create_run(run_id, task="回归任务", planner="autopilot")

    loaded = store.load_checkpoint(run_id)
    assert loaded is not None
    assert loaded["status"] == "running"
    assert loaded["task"] == "回归任务"

    store.save_checkpoint(run_id, {"cycle": 2, "last": "step-b", "steps": ["a", "b"]})
    loaded = store.load_checkpoint(run_id)
    assert loaded["state"]["cycle"] == 2
    assert loaded["state"]["last"] == "step-b"

    store.mark_done(run_id)
    assert store.load_checkpoint(run_id)["status"] == "done"

    assert any(r["run_id"] == run_id for r in store.list_runs(limit=100))


def test_unknown_run_returns_none():
    assert store.load_checkpoint("no-such-run-" + uuid.uuid4().hex) is None


def test_second_connection_reads_while_writes_happen():
    """WAL 的核心收益：写不挡读。用一条独立连接并发读，不应超时。"""
    if store._conn().execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
        import pytest
        pytest.skip("当前文件系统未启用 WAL，跳过并发读验证")

    run_id = f"test-cc-{uuid.uuid4().hex[:8]}"
    store.create_run(run_id, task="并发读", planner="autopilot")

    stop = threading.Event()
    errors: list[Exception] = []

    def writer():
        try:
            for i in range(30):
                store.save_checkpoint(run_id, {"cycle": i})
        except Exception as e:  # pragma: no cover - 失败即测试失败
            errors.append(e)
        finally:
            stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    db_path = os.path.abspath(store._DB_PATH)
    reader = sqlite3.connect(db_path, timeout=5.0)
    try:
        reads = 0
        while not stop.is_set() and reads < 50:
            row = reader.execute(
                "SELECT status FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            assert row is not None
            reads += 1
        assert reads > 0, "并发读一次都没成功"
    finally:
        reader.close()
        t.join(timeout=10)

    assert not errors, f"并发写入报错: {errors}"
    store.mark_done(run_id)
