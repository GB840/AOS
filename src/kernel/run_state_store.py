"""Durable run-state store for autopilot — Step-level Checkpointing.

Local-first, zero external dependency: Python stdlib ``sqlite3`` (matches the
project's "本地零成本" philosophy, on par with mem0's local mode).

Every autonomous run checkpoints its state after each reflection cycle, so a
crashed / interrupted process can ``resume_run`` from the last *completed*
cycle instead of re-running everything from scratch.

State is a JSON-serializable dict produced by ``autopilot._RunState.to_dict``:
    {run_id, task, planner, plan_text, steps, prior_success,
     reflection_log, last, cycle, start}
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "_traces", "aos_runs.db"
)
_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def _conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        _CONN = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=5.0)
        # WAL: 读不阻塞写、写不阻塞读。autopilot 边跑边 checkpoint 时，
        # 看板/CLI 的 list_runs 不会再被写事务卡住（默认 rollback journal 读写互斥）。
        # 进程内并发仍由 _LOCK 串行化，WAL 解决的是"多进程/多连接同时访问同一个库文件"。
        for pragma in (
            "PRAGMA journal_mode=WAL",      # 崩溃安全 + 读写并发
            "PRAGMA synchronous=NORMAL",    # WAL 下的推荐档位，掉电最多丢最后一批已提交事务
            "PRAGMA busy_timeout=5000",     # 锁竞争时等 5s 而不是立刻 database is locked
        ):
            try:
                _CONN.execute(pragma)
            except sqlite3.Error:
                # 某些文件系统（部分网络盘）不支持 WAL，降级为默认日志模式继续跑，
                # 不能因为一条 PRAGMA 让整个 checkpoint 能力不可用。
                pass
        _CONN.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                   run_id  TEXT PRIMARY KEY,
                   task    TEXT,
                   planner TEXT,
                   status  TEXT,
                   created REAL,
                   updated REAL,
                   state   TEXT
               )"""
        )
    return _CONN


def create_run(run_id: str, task: str, planner: str) -> None:
    """Register a new run (status=running). Idempotent."""
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?)",
            (run_id, task, planner, "running", time.time(), time.time(), "{}"),
        )


def save_checkpoint(run_id: str, state: dict) -> None:
    """Persist a full run-state snapshot. Called after every cycle.

    ``default=str`` guards against any stray non-serializable leaf so a
    checkpoint never fails to write (a failed checkpoint must not crash the run).
    """
    blob = json.dumps(state, ensure_ascii=False, default=str)
    with _LOCK, _conn() as c:
        c.execute(
            "UPDATE runs SET state=?, updated=?, status='running' WHERE run_id=?",
            (blob, time.time(), run_id),
        )


def load_checkpoint(run_id: str):
    """Return {state, status, task, planner} or None if unknown run_id."""
    with _LOCK, _conn() as c:
        row = c.execute(
            "SELECT state, status, task, planner FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "state": json.loads(row[0]),
        "status": row[1],
        "task": row[2],
        "planner": row[3],
    }


def mark_done(run_id: str) -> None:
    with _LOCK, _conn() as c:
        c.execute(
            "UPDATE runs SET status='done', updated=? WHERE run_id=?",
            (time.time(), run_id),
        )


def mark_failed(run_id: str) -> None:
    with _LOCK, _conn() as c:
        c.execute(
            "UPDATE runs SET status='failed', updated=? WHERE run_id=?",
            (time.time(), run_id),
        )


def list_runs(limit: int = 20) -> list:
    with _LOCK, _conn() as c:
        rows = c.execute(
            "SELECT run_id, task, status, updated FROM runs "
            "ORDER BY updated DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"run_id": r[0], "task": r[1], "status": r[2], "updated": r[3]}
        for r in rows
    ]
