"""②级实证：run_state_store 的 MEA AuditorGate。

验证核心纪律：写入持久状态前须经独立只读审计；未通过的事实不污染快照。
不改动任何 autopilot 生产行为，仅测 store 层钩子（默认关闭=向后兼容）。
"""
from __future__ import annotations

import logging

import pytest

from kernel import run_state_store as rs


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """每个测试用独立 sqlite，并重置模块级连接与 auditor，避免跨测试污染。"""
    monkeypatch.setattr(rs, "_DB_PATH", str(tmp_path / "aos_runs_gate.db"))
    monkeypatch.setattr(rs, "_CONN", None)
    monkeypatch.setattr(rs, "_AUDITOR", None)
    yield
    # 清理：关闭可能占用的连接
    conn = rs._CONN
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        monkeypatch.setattr(rs, "_CONN", None)


def _new_run(run_id: str = "r1") -> None:
    rs.create_run(run_id, "task", "planner")


def test_no_auditor_backward_compatible():
    """无 auditor 时行为与原版一致：照常写盘。"""
    _new_run()
    ok = rs.save_checkpoint("r1", {"a": 1, "steps": []})
    assert ok is True
    assert rs.load_checkpoint("r1")["state"]["a"] == 1


def test_auditor_rejects_blocks_write():
    """auditor 返回 False → 拒绝写入，旧快照保留（错误前提不污染状态）。"""
    _new_run()
    rs.save_checkpoint("r1", {"a": 1})
    rs.set_auditor(lambda state, run_id: False)
    ok = rs.save_checkpoint("r1", {"a": 999})
    assert ok is False
    # 关键：旧快照仍完整，脏数据未进库
    assert rs.load_checkpoint("r1")["state"]["a"] == 1


def test_auditor_passes_writes():
    """auditor 返回 True → 放行写入。"""
    _new_run()
    rs.set_auditor(lambda state, run_id: True)
    ok = rs.save_checkpoint("r1", {"a": 7})
    assert ok is True
    assert rs.load_checkpoint("r1")["state"]["a"] == 7


def test_auditor_exception_downgrades_to_pass(caplog):
    """auditor 抛异常 → 降级放行 + 告警，绝不阻塞 run。"""
    _new_run()
    def boom(state, run_id):
        raise RuntimeError("auditor died")
    rs.set_auditor(boom)
    with caplog.at_level(logging.WARNING, logger="run_state_store"):
        ok = rs.save_checkpoint("r1", {"a": 5})
    assert ok is True
    assert rs.load_checkpoint("r1")["state"]["a"] == 5
    assert any("AuditorGate 异常" in r.message for r in caplog.records)


def test_auditor_can_verify_env_fact_and_reject_fake_completion():
    """真实场景：executor 声称 step 完成但环境事实不符 → 拒绝。

    模拟 auditor 检查「state 声明的 completed 步数」与「reflection_log 实际记录」是否一致。
    """
    def env_fact_auditor(state, run_id):
        steps = state.get("steps") or []
        claimed_done = sum(1 for s in steps if s.get("status") == "completed")
        logged = state.get("reflection_log") or []
        # 环境事实：每完成一步都应留下一条带「完成」标记的 reflection 记录
        verified_done = sum(
            1 for e in logged if e.get("action") == "step_done"
        )
        return claimed_done <= verified_done  # 不允许凭空宣称多于实际验证

    rs.set_auditor(env_fact_auditor)
    _new_run()
    # 合法：宣称 1 步完成，reflection 有 1 条证据
    ok = rs.save_checkpoint("r1", {
        "steps": [{"status": "completed", "id": 0}],
        "reflection_log": [{"action": "step_done", "id": 0}],
    })
    assert ok is True

    # 非法：宣称 2 步完成，但 reflection 仅有 1 条证据 → 拒绝
    ok2 = rs.save_checkpoint("r1", {
        "steps": [
            {"status": "completed", "id": 0},
            {"status": "completed", "id": 1},  # 凭空多宣称一步
        ],
        "reflection_log": [{"action": "step_done", "id": 0}],
    })
    assert ok2 is False
    # 库里仍是上一合法快照，未被脏数据覆盖
    assert rs.load_checkpoint("r1")["state"]["steps"][0]["id"] == 0
    assert len(rs.load_checkpoint("r1")["state"]["steps"]) == 1
