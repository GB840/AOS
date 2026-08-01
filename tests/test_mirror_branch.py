"""L5 演进层 · 镜像分支试错 单元测试（诚实度 ②）。"""
from __future__ import annotations

import pytest

from kernel.evolve.mirror_branch import (
    MirrorBranch, MirrorLab, ShadowLeak, BranchClosed, two_proportion_z,
    BASELINE, CANDIDATE, TRIAL, PROMOTED, ROLLED_BACK, BLOCKED,
    HOLD, PROMOTE, ROLLBACK, NEEDS_APPROVAL, CONSTITUTION_BLOCK,
)


def _fill(br: MirrorBranch, n: int, base_succ: int, cand_succ: int,
          cost_b: float = 0.01, cost_c: float = 0.01) -> None:
    """给两臂各灌 n 条样本，成功数分别为 base_succ / cand_succ。"""
    for i in range(n):
        br.record(f"t{i}", BASELINE, i < base_succ, cost=cost_b, now=1000.0 + i)
        br.record(f"t{i}", CANDIDATE, i < cand_succ, cost=cost_c, now=1000.0 + i)


# ---------------- 统计检验 ----------------

def test_two_proportion_z_no_samples_is_no_evidence():
    r = two_proportion_z(0, 0, 0, 0)
    assert r["z"] == 0.0 and r["p_value"] == 1.0


def test_two_proportion_z_detects_real_lift():
    # 候选 90/100 vs 基线 60/100 —— 应该显著
    r = two_proportion_z(90, 100, 60, 100)
    assert r["z"] > 2.0 and r["p_value"] < 0.01


def test_two_proportion_z_small_sample_not_significant():
    # 4/5 vs 3/5 看着"更好"，但样本太小，p 值不显著
    r = two_proportion_z(4, 5, 3, 5)
    assert r["p_value"] > 0.05


# ---------------- 影子纪律 ----------------

def test_candidate_emitted_raises_shadow_leak():
    br = MirrorBranch("b1", "v1", "v2")
    with pytest.raises(ShadowLeak):
        br.record("t1", CANDIDATE, True, emitted=True, now=1.0)


def test_baseline_may_emit():
    br = MirrorBranch("b1", "v1", "v2")
    s = br.record("t1", BASELINE, True, emitted=True, now=1.0)
    assert s.emitted is True


def test_shadow_run_records_both_arms_and_swallows_no_error():
    br = MirrorBranch("b1", "v1", "v2")

    def good(_tid):
        return {"success": True, "cost": 0.02}

    def boom(_tid):
        raise RuntimeError("候选炸了")

    out = br.shadow_run("t1", good, boom, now=1.0)
    assert out[BASELINE].success is True
    assert out[CANDIDATE].success is False
    # 真实错误必须留证据，不许吞
    assert "候选炸了" in out[CANDIDATE].detail["error"]


def test_shadow_run_blocks_candidate_emission():
    br = MirrorBranch("b1", "v1", "v2")
    # 候选 runner 谎称已投放，shadow_run 也不给它 emitted（强制置 False）
    out = br.shadow_run("t1", lambda _t: {"success": True},
                        lambda _t: {"success": True, "emitted": True}, now=1.0)
    assert out[CANDIDATE].emitted is False


# ---------------- 闸门 ----------------

def test_gate_holds_without_enough_samples():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 5, 2, 5)
    d = br.gate()
    assert d.verdict == HOLD and "样本不足" in d.reason


def test_gate_promotes_on_significant_lift():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 60, 90)
    d = br.gate()
    assert d.verdict == PROMOTE
    assert d.lift == pytest.approx(0.30, abs=1e-6)
    assert d.p_value < 0.05


def test_gate_holds_when_lift_too_small():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 60, 62)          # 只涨 2 个点，低于 5 点阈值
    d = br.gate()
    assert d.verdict == HOLD and "提升不足" in d.reason


def test_gate_holds_when_lift_big_but_not_significant():
    # 20 例里涨 10 个点：lift 达标但样本少，p 值不显著 → 不许上线（防噪声）
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 20, 12, 14)
    d = br.gate()
    assert d.verdict == HOLD and "统计显著" in d.reason


def test_gate_recommends_rollback_when_much_worse():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 80, 50)
    d = br.gate()
    assert d.verdict == ROLLBACK and d.lift < 0


def test_gate_holds_when_candidate_too_expensive():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 60, 90, cost_b=0.01, cost_c=0.05)   # 贵 5 倍
    d = br.gate()
    assert d.verdict == HOLD and "成本过高" in d.reason


def test_irreversible_branch_needs_approval():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20, irreversible=True)
    _fill(br, 100, 60, 90)
    assert br.gate().verdict == NEEDS_APPROVAL


# ---------------- 宪法红线 ----------------

def test_single_harm_event_blocks_branch_forever():
    br = MirrorBranch("b1", "v1", "v2", min_samples=5)
    _fill(br, 10, 5, 10)
    br.record("bad", CANDIDATE, True, harm=True, now=2000.0)
    assert br.state == BLOCKED
    assert br.gate().verdict == CONSTITUTION_BLOCK
    # 拉黑后不再收样本
    with pytest.raises(BranchClosed):
        br.record("t99", CANDIDATE, True, now=2001.0)


def test_blocked_branch_cannot_be_promoted():
    br = MirrorBranch("b1", "v1", "v2", min_samples=5)
    _fill(br, 10, 5, 10)
    br.record("bad", CANDIDATE, True, harm=True, now=2000.0)
    with pytest.raises(PermissionError):
        br.promote(approver="human")


# ---------------- 晋升 / 回滚 ----------------

def test_promote_swaps_baseline_and_keeps_audit():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 60, 90)
    rec = br.promote(now=5000.0)
    assert br.state == PROMOTED
    assert br.baseline_ref == "v2"
    assert rec["from"] == "v1" and rec["to"] == "v2"
    assert br.audit[-1]["event"] == "promote"


def test_promote_rejected_when_gate_holds():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 60, 61)
    with pytest.raises(PermissionError):
        br.promote()


def test_irreversible_promote_requires_approver_or_consensus():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20, irreversible=True)
    _fill(br, 100, 60, 90)
    with pytest.raises(PermissionError):
        br.promote()
    rec = br.promote(consensus_ok=True, now=5000.0)
    assert rec["consensus_ok"] is True and br.state == PROMOTED


def test_rollback_restores_snapshot_after_promote():
    br = MirrorBranch("b1", "v1", "v2", min_samples=20)
    _fill(br, 100, 60, 90)
    br.promote(now=5000.0)
    assert br.baseline_ref == "v2"
    br.rollback("线上炸了", now=6000.0)
    assert br.state == ROLLED_BACK
    assert br.baseline_ref == "v1"          # 回到快照
    assert br.audit[-1]["reason"] == "线上炸了"


# ---------------- 实验室并发约束 ----------------

def test_lab_limits_concurrent_branches():
    lab = MirrorLab(max_concurrent=2)
    lab.open("a", "v1", "v2")
    lab.open("b", "v1", "v2")
    with pytest.raises(PermissionError):
        lab.open("c", "v1", "v2")


def test_lab_reopen_after_branch_closed():
    lab = MirrorLab(max_concurrent=1)
    br = lab.open("a", "v1", "v2")
    br.rollback("放弃", now=1.0)
    lab.open("b", "v1", "v3")       # 前一条已终局，可以再开
    assert lab.report()["active"] == 1


def test_lab_report_lists_promotable_and_blocked():
    lab = MirrorLab(max_concurrent=3)
    good = lab.open("good", "v1", "v2", min_samples=20)
    _fill(good, 100, 60, 90)
    bad = lab.open("bad", "v1", "v3", min_samples=5)
    _fill(bad, 10, 5, 10)
    bad.record("x", CANDIDATE, True, harm=True, now=1.0)
    rep = lab.report()
    assert rep["promotable"] == ["good"]
    assert rep["blocked"] == ["bad"]
