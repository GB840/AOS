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
import logging
import os
import sqlite3
import threading
import time
import uuid

_LOG = logging.getLogger("run_state_store")

_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "_traces", "aos_runs.db"
)
_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None

# MEA 对齐（2026-08-05）：可选「只读审计关卡」。写入持久状态前若已注册 auditor，
# 则由 auditor 基于环境事实独立验证；未通过则拒绝覆盖旧快照（错误前提不污染状态）。
# 默认 None = 向后兼容（行为与旧版一致，任何调用方都不必改动）。
#   auditor 契约：callable(state: dict, run_id: str) -> bool
#     - True / truthy  → 放行写入
#     - False / falsy  → 拒绝写入（保留上一已验证快照）
#     - 抛异常          → 降级放行 + 告警（绝不因审计器故障阻塞 run）
_AUDITOR = None


def set_auditor(fn):
    """注册只读审计器（MEA AuditorGate）。传 None 关闭。"""
    global _AUDITOR
    _AUDITOR = fn


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
        # MEA Gap1：独立的「已验证事实」层。与 runs.state（executor 进度快照）分离——
        # 只有经 auditor 验证的里程碑才进此表；未验证的"声称"绝不落盘（错误前提不污染状态）。
        _CONN.execute(
            """CREATE TABLE IF NOT EXISTS verified_milestones (
                   run_id       TEXT,
                   milestone_id TEXT,
                   payload      TEXT,
                   verified_at  REAL,
                   PRIMARY KEY (run_id, milestone_id)
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


def save_checkpoint(run_id: str, state: dict) -> bool:
    """Persist a full run-state snapshot. Called after every cycle.

    ``default=str`` guards against any stray non-serializable leaf so a
    checkpoint never fails to write (a failed checkpoint must not crash the run).

    MEA AuditorGate：若已注册 ``_AUDITOR``，写盘前由其基于环境事实独立验证。
    验证未通过则**不覆盖**旧快照（错误前提不污染持久状态），返回 False；
    auditor 自身抛异常时降级放行并告警，绝不阻塞 run。
    无 auditor 时行为与原版完全一致。
    """
    if _AUDITOR is not None:
        try:
            verdict = _AUDITOR(state, run_id)
        except Exception as e:  # noqa: BLE001
            _LOG.warning("AuditorGate 异常，降级放行: %s", e)
            verdict = True
        if not verdict:
            _LOG.warning(
                "AuditorGate 拒绝写入 run=%s verdict=%r（保留上一已验证快照）",
                run_id, verdict,
            )
            # 仅刷新 updated 时间戳，state 保持旧值，避免错误前提污染。
            with _LOCK, _conn() as c:
                c.execute(
                    "UPDATE runs SET updated=? WHERE run_id=?",
                    (time.time(), run_id),
                )
            return False
    blob = json.dumps(state, ensure_ascii=False, default=str)
    with _LOCK, _conn() as c:
        c.execute(
            "UPDATE runs SET state=?, updated=?, status='running' WHERE run_id=?",
            (blob, time.time(), run_id),
        )
    return True


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


def propose_milestone(run_id: str, milestone: dict) -> str:
    """MEA Gap1：把一条里程碑写入「已验证事实」层。

    - 若已注册 ``_AUDITOR``：写盘前由其基于环境事实独立验证；
      验证未通过则**抛 ValueError 且不写入**（声称的里程碑不污染已验证状态）。
    - 若未注册 auditor：默认放行（向后兼容；设计意图是 autopilot 接上真实探针）。
    - auditor 自身抛异常：降级放行 + 告警（绝不因审计器故障阻塞 run）。

    返回 milestone_id。调用方（autopilot）应把"经此验证的里程碑"作为
    Manager 角色可依赖的「已验证进度」，而非依赖 runs.state 的原始快照。
    """
    mid = f"m_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
    if _AUDITOR is not None:
        try:
            verdict = _AUDITOR(
                {"type": "milestone", "milestone": milestone}, run_id
            )
        except Exception as e:  # noqa: BLE001
            _LOG.warning("AuditorGate(里程碑) 异常，降级放行: %s", e)
            verdict = True
        if not verdict:
            raise ValueError(
                f"auditor rejected milestone for run={run_id}: {milestone!r}"
            )
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO verified_milestones "
            "(run_id, milestone_id, payload, verified_at) VALUES (?,?,?,?)",
            (run_id, mid, json.dumps(milestone, ensure_ascii=False, default=str),
             time.time()),
        )
    return mid


def get_verified_milestones(run_id: str) -> list:
    """返回某 run 经审计验证的全部里程碑（按验证时间升序）。

    与 ``load_checkpoint(run_id)['state']['steps']`` 的关键区别：
    这里是**经 auditor 验证过的事实集**，而非 executor 自称的进度快照。
    """
    with _LOCK, _conn() as c:
        rows = c.execute(
            "SELECT payload FROM verified_milestones "
            "WHERE run_id=? ORDER BY verified_at ASC",
            (run_id,),
        ).fetchall()
    return [json.loads(r[0]) for r in rows]


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
