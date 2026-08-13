"""MEA Gap1：已验证里程碑状态层（②级实证）。

验证 run_state_store 的 propose_milestone / get_verified_milestones：
- 无 auditor：默认放行（向后兼容）
- 有 auditor 且拒绝：抛 ValueError 且不写入（声称不污染已验证状态）
- 有 auditor 且放行：写入
- auditor 异常：降级放行
- 关键隔离：runs.state 的原始 steps 不会自动变成 verified_milestones，必须显式 propose
"""
from __future__ import annotations

import pytest

import src.kernel.run_state_store as rs


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path):
    """每测试用全新临时库文件 + 清空 auditor，避免跨测试串扰。"""
    rs._CONN = None
    rs._AUDITOR = None
    rs._DB_PATH = str(tmp_path / "aos_runs_test.db")
    yield
    rs._CONN = None
    rs._AUDITOR = None


def _new_run(rid: str = "r1"):
    rs.create_run(rid, "task-x", "p")


def test_propose_without_auditor_accepted():
    _new_run()
    mid = rs.propose_milestone("r1", {"id": 1, "done": True})
    assert isinstance(mid, str) and mid.startswith("m_")
    assert rs.get_verified_milestones("r1") == [{"id": 1, "done": True}]


def test_propose_rejected_by_auditor_raises_and_not_written():
    _new_run()
    rs.set_auditor(lambda state, run_id: False)  # 永远拒绝
    with pytest.raises(ValueError):
        rs.propose_milestone("r1", {"id": 99, "done": True})
    # 什么都没写进去
    assert rs.get_verified_milestones("r1") == []


def test_propose_accepted_by_auditor_written():
    _new_run()
    rs.set_auditor(lambda state, run_id: True)
    rs.propose_milestone("r1", {"id": 2, "done": True})
    assert rs.get_verified_milestones("r1") == [{"id": 2, "done": True}]


def test_auditor_exception_degrades_to_accept():
    _new_run()
    def _boom(state, run_id):
        raise RuntimeError("auditor crashed")
    rs.set_auditor(_boom)
    # 异常降级放行，不抛、写入
    mid = rs.propose_milestone("r1", {"id": 3, "done": True})
    assert mid.startswith("m_")
    assert rs.get_verified_milestones("r1") == [{"id": 3, "done": True}]


def test_raw_checkpoint_steps_not_auto_verified():
    """关键隔离：executor 在 runs.state 里自称完成 3 步，
    但未显式 propose 的，绝不出现在已验证层。"""
    _new_run()
    rs.save_checkpoint("r1", {
        "steps": [
            {"id": 0, "status": "done"},
            {"id": 1, "status": "done"},
            {"id": 2, "status": "done"},
        ]
    })
    # 断言：verified 层为空（因为没 propose）
    assert rs.get_verified_milestones("r1") == []
    # 但原始快照里确实有 3 步（证明两层是分开的）
    assert len(rs.load_checkpoint("r1")["state"]["steps"]) == 3
    # 只有显式 propose 才进 verified 层
    rs.propose_milestone("r1", {"id": 0, "status": "done"})
    assert rs.get_verified_milestones("r1") == [{"id": 0, "status": "done"}]


def test_multiple_milestones_ordered():
    _new_run()
    rs.propose_milestone("r1", {"id": 1})
    rs.propose_milestone("r1", {"id": 2})
    rs.propose_milestone("r1", {"id": 3})
    assert [m["id"] for m in rs.get_verified_milestones("r1")] == [1, 2, 3]
