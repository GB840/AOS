"""MEA Auditor 角色真实落地（②级实证）。

覆盖 kernel.auditor.EnvironmentAuditor + 其在 run_state_store Gate / verified 层的接线：
- 无 verify 规格 → 放行（向后兼容）
- verify 文件存在 → 放行
- verify 文件缺失 → 拒绝（Gate 拒写 / propose_milestone 抛错）
- 未知核查类型 → 跳过不阻断
"""
from __future__ import annotations

import importlib

import pytest

import src.kernel.auditor as auditor_mod
import src.kernel.run_state_store as rs
from src.kernel.auditor import build_default_auditor


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path):
    rs._CONN = None
    rs._AUDITOR = None
    rs._DB_PATH = str(tmp_path / "aos_runs_test.db")
    yield
    rs._CONN = None
    rs._AUDITOR = None


def _touch(p):
    open(p, "w", encoding="utf-8").write("ok")


def test_build_default_auditor_callable():
    a = build_default_auditor()
    assert callable(a)
    # 无 verify → 放行
    assert a({"steps": [1, 2, 3]}, "r1") is True


def test_accept_when_file_exists(tmp_path):
    f = tmp_path / "out.txt"
    _touch(f)
    a = build_default_auditor()
    assert a({"verify": {"file": str(f)}}, "r1") is True


def test_reject_when_file_missing(tmp_path):
    a = build_default_auditor()
    # 指向不存在的文件 → 拒绝
    assert a({"verify": {"file": str(tmp_path / "nope.txt")}}, "r1") is False


def test_unknown_check_skipped(tmp_path):
    a = build_default_auditor()
    # 未知核查类型 → 跳过（不阻断），但需同规格里没有失败项才能放行
    assert a({"verify": {"bogus_type": "x"}}, "r1") is True


def test_gate_rejects_checkpoint_when_verify_file_missing(tmp_path):
    rs.set_auditor(build_default_auditor())
    rs.create_run("r1", "t", "p")
    rs.save_checkpoint("r1", {"steps": [{"id": 0, "ok": True}]})  # 首写（无 verify）
    # 第二写带 verify 指向不存在文件 → 应拒绝且不覆盖
    ok = rs.save_checkpoint("r1", {
        "steps": [{"id": 0, "ok": True}, {"id": 1, "ok": True}],
        "verify": {"file": str(tmp_path / "missing.txt")},
    })
    assert ok is False
    # 库里仍是上一合法快照（1 步），未被脏数据覆盖
    saved = rs.load_checkpoint("r1")["state"]
    assert len(saved["steps"]) == 1


def test_gate_accepts_checkpoint_when_verify_file_exists(tmp_path):
    f = tmp_path / "ok.txt"
    _touch(f)
    rs.set_auditor(build_default_auditor())
    rs.create_run("r1", "t", "p")
    ok = rs.save_checkpoint("r1", {
        "steps": [{"id": 0, "ok": True}],
        "verify": {"file": str(f)},
    })
    assert ok is True
    assert len(rs.load_checkpoint("r1")["state"]["steps"]) == 1


def test_propose_milestone_rejected_by_real_auditor(tmp_path):
    rs.set_auditor(build_default_auditor())
    rs.create_run("r1", "t", "p")
    # 里程碑声称完成且 verify 指向不存在文件 → 抛 ValueError 且不写入
    with pytest.raises(ValueError):
        rs.propose_milestone("r1", {
            "id": 1, "done": True,
            "verify": {"file": str(tmp_path / "gone.txt")},
        })
    assert rs.get_verified_milestones("r1") == []


def test_propose_milestone_accepted_when_verify_file_exists(tmp_path):
    f = tmp_path / "proof.txt"
    _touch(f)
    rs.set_auditor(build_default_auditor())
    rs.create_run("r1", "t", "p")
    rs.propose_milestone("r1", {
        "id": 1, "done": True,
        "verify": {"file": str(f)},
    })
    m = rs.get_verified_milestones("r1")
    assert len(m) == 1 and m[0]["id"] == 1


# ===== auditor.py 边路覆盖（补齐 61%→~95% 的漏测分支） =====


def test_contains_regex_match_pass(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("epoch 7 finished ok", encoding="utf-8")
    a = build_default_auditor()
    assert a({"verify": {"contains": {"path": str(f), "pattern": r"epoch\s+\d+"}}}, "r1") is True


def test_contains_regex_no_match(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("nothing here", encoding="utf-8")
    a = build_default_auditor()
    assert a({"verify": {"contains": {"path": str(f), "pattern": r"epoch\s+\d+"}}}, "r1") is False


def test_contains_missing_path(tmp_path):
    a = build_default_auditor()
    # 路径不存在 → 核查失败
    assert a({"verify": {"contains": {"path": str(tmp_path / "x.log"), "pattern": "."}}}, "r1") is False


def test_contains_non_dict_spec(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("data", encoding="utf-8")
    a = build_default_auditor()
    # contains 的值非 dict → _check_contains 返回 False（拒绝）
    assert a({"verify": {"contains": str(f)}}, "r1") is False


def test_custom_checks_injection(tmp_path):
    calls = []

    def my_check(val):
        calls.append(val)
        return val == "good"

    a = build_default_auditor()
    a._checks["mykind"] = my_check  # 注入自定义核查类型
    assert a({"verify": {"mykind": "good"}}, "r1") is True
    assert a({"verify": {"mykind": "bad"}}, "r1") is False
    assert calls == ["good", "bad"]


def test_non_dict_state_passes():
    a = build_default_auditor()
    # 非 dict 状态（异常输入）→ 保守放行，不崩
    assert a("not-a-dict", "r1") is True


def test_verify_spec_not_dict_passes():
    a = build_default_auditor()
    # verify 非 dict（如字符串/列表）→ 跳过核查，放行
    assert a({"verify": "should-be-dict"}, "r1") is True
    assert a({"verify": ["list", "not", "dict"]}, "r1") is True


def test_check_raises_returns_false():
    def boom(_val):
        raise RuntimeError("injected failure")

    a = build_default_auditor()
    a._checks["boom"] = boom
    # 核查抛异常 → 视为失败，拒绝
    assert a({"verify": {"boom": "x"}}, "r1") is False


def test_files_check_wraps_single_path(tmp_path):
    f = tmp_path / "a.txt"
    _touch(f)
    a = build_default_auditor()
    # files 给定单条（非列表）→ _check_files 内部包成列表仍能核查
    assert a({"verify": {"files": str(f)}}, "r1") is True
