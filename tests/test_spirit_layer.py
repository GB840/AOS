"""L4 精神层单测：价值观市场 / 师徒协议 / 大同指数 / 文明镜像 / 共识通道。"""
import pytest

from kernel.spirit import (
    ValuePlugin, ValuesMarket, ValueConflict,
    Mentorship, DatongIndex, CivilizationMirror,
    ConsensusChannel,
)
from kernel.spirit.consensus import (
    CONSTITUTIONAL, ORDINARY, ImmutableClause, PASSED, REJECTED,
)
from kernel.spirit.mentorship import OBSERVE, SHADOW, LIMITED, AUTONOMOUS


# --------------------------------------------------- L4B 价值观插件市场
def test_plugin_cannot_break_constitution_redline():
    mk = ValuesMarket()
    with pytest.raises(PermissionError) as e:
        mk.publish(ValuePlugin("evil", {"no_harm": 0.1}))
    assert "红线" in str(e.value)
    assert mk.rejected and mk.rejected[0][1] == ["no_harm"]


def test_unknown_dimension_rejected():
    mk = ValuesMarket()
    with pytest.raises(ValueError):
        mk.publish(ValuePlugin("weird", {"vibes": 0.9}))


def test_conflict_is_explicit_not_silently_averaged():
    mk = ValuesMarket()
    mk.publish(ValuePlugin("privacy_first", {"privacy": 0.95, "speed": 0.2}))
    mk.publish(ValuePlugin("speed_first", {"privacy": 0.5, "speed": 0.95}))
    mk.install("privacy_first"); mk.install("speed_first")
    assert len(mk.conflicts()) >= 1
    with pytest.raises(ValueConflict):
        mk.resolve(strict=True)
    eff = mk.resolve(strict=False)        # 非严格模式才合并
    assert 0.5 <= eff["privacy"] <= 0.95


def test_priority_wins_over_average():
    mk = ValuesMarket()
    mk.publish(ValuePlugin("tenant", {"speed": 0.9}, priority=2))
    mk.publish(ValuePlugin("community", {"speed": 0.1}, priority=1))
    mk.install("tenant"); mk.install("community")
    assert mk.resolve(strict=False)["speed"] == 0.9


def test_redline_floor_applied_even_if_no_plugin():
    mk = ValuesMarket()
    eff = mk.resolve()
    assert eff["no_harm"] == 1.0 and eff["honesty"] >= 0.9


def test_explain_is_human_readable():
    mk = ValuesMarket()
    mk.publish(ValuePlugin("p", {"privacy": 0.8}))
    mk.install("p")
    s = mk.explain("privacy")
    assert "privacy" in s and "p=0.80" in s


# ------------------------------------------------------ L4C 师徒协议
def test_new_apprentice_has_read_only():
    ms = Mentorship()
    a = ms.enroll("newbie", mentor="master")
    assert a.stage == OBSERVE and a.can("read") and not a.can("write")
    with pytest.raises(PermissionError):
        ms.require("newbie", "write")


def test_promotion_requires_real_trials():
    ms = Mentorship()
    ms.enroll("n", mentor="m")
    ok, why = ms.can_promote("n")
    assert ok is False and "考核次数" in why
    for i in range(3):
        ms.record("n", f"task{i}", passed=True, evidence="exit_code=0")
    assert ms.promote("n") == SHADOW
    assert ms.get("n").trials == []      # 新阶段重新考核


def test_signoff_required_at_shadow_and_no_self_signoff():
    ms = Mentorship()
    ms.enroll("n", mentor="m")
    ms.get("n").stage = SHADOW
    for i in range(5):
        ms.record("n", f"t{i}", passed=True)
    ok, why = ms.can_promote("n")
    assert ok is False and "签字" in why
    with pytest.raises(PermissionError):
        ms.signoff("n", "impostor")
    ms.signoff("n", "m")
    assert ms.promote("n") == LIMITED


def test_severe_fault_demotes_immediately():
    ms = Mentorship()
    ms.enroll("n", mentor="m")
    ms.get("n").stage = LIMITED
    ms.record("n", "删了不该删的", passed=False, severe_fault=True)
    assert ms.get("n").stage == SHADOW
    assert ms.get("n").demotions == 1


def test_autonomous_has_full_caps():
    ms = Mentorship()
    ms.enroll("n")
    ms.get("n").stage = AUTONOMOUS
    assert ms.get("n").can("spend") and ms.get("n").can("spawn")
    ok, why = ms.can_promote("n")
    assert ok is False and "已是完全自主" in why


# ------------------------------------------- L4D 大同指数 / L4E 镜像
def test_datong_perfect_world_scores_high():
    d = DatongIndex()
    m = d.compute(value_shares=[1, 1, 1, 1], resource_shares=[10, 10, 10, 10],
                  votes_passed=8, votes_total=10, harm_events=0, total_events=100)
    assert m["diversity"] == 1.0 and m["fairness"] > 0.99
    assert m["harm_free"] == 1.0 and m["alert"] is False


def test_datong_monopoly_and_unfairness_trigger_actions():
    d = DatongIndex()
    m = d.compute(value_shares=[100, 0, 0, 0], resource_shares=[100, 1, 1, 1],
                  votes_passed=1, votes_total=10, harm_events=5, total_events=100)
    assert m["alert"] is True
    assert "open_values_market:invite_more_plugins" in m["actions"]
    assert "rebalance_quota:cap_top_consumer" in m["actions"]
    assert "freeze_risky_actions:require_approval" in m["actions"]


def test_datong_trend():
    d = DatongIndex()
    d.compute(value_shares=[1, 9], resource_shares=[1, 9], votes_passed=1, votes_total=10,
              harm_events=1, total_events=10)
    d.compute(value_shares=[1, 1], resource_shares=[1, 1], votes_passed=9, votes_total=10,
              harm_events=0, total_events=10)
    assert d.trend() > 0


def _measure(world):
    return DatongIndex().compute(
        value_shares=world["values"], resource_shares=world["res"],
        votes_passed=world["yes"], votes_total=world["total"],
        harm_events=world["harm"], total_events=world["events"])


def test_mirror_does_not_pollute_real_world():
    """试错在镜像里：真身必须零改动。"""
    world = {"values": [1, 1], "res": [1, 1], "yes": 5, "total": 10,
             "harm": 0, "events": 10}

    def change(w):
        w["res"] = [100, 1]
        return w

    mir = CivilizationMirror()
    res = mir.rehearse(world, change, _measure)
    assert world["res"] == [1, 1]                # 真身没被改
    assert res.accepted is False                 # 公平性恶化 → 拒绝
    assert any("fairness" in s for s in res.side_effects)


def test_mirror_rejects_any_harm_increase():
    world = {"values": [1, 1], "res": [1, 1], "yes": 9, "total": 10,
             "harm": 0, "events": 10}

    def change(w):
        w["harm"] = 3
        w["values"] = [1, 1, 1, 1]     # 即便别的指标变好
        return w

    res = CivilizationMirror().rehearse(world, change, _measure)
    assert res.accepted is False and "无害性" in res.reason


def test_mirror_accepts_improvement_and_applies():
    world = {"values": [9, 1], "res": [9, 1], "yes": 3, "total": 10,
             "harm": 0, "events": 10}

    def change(w):
        w["values"] = [1, 1]
        w["res"] = [1, 1]
        w["yes"] = 9
        return w

    mir = CivilizationMirror()
    new_world, res = mir.apply_if_accepted(world, change, _measure)
    assert res.accepted is True and res.delta > 0
    assert new_world["res"] == [1, 1]


def test_mirror_catches_exception_instead_of_crashing_real_world():
    world = {"values": [1, 1], "res": [1, 1], "yes": 5, "total": 10,
             "harm": 0, "events": 10}

    def boom(w):
        raise RuntimeError("变更脚本自己炸了")

    res = CivilizationMirror().rehearse(world, boom, _measure)
    assert res.accepted is False and "镜像内变更抛错" in res.reason


# --------------------------------------------------- L4F 共识自演化通道
def _channel():
    c = ConsensusChannel()
    c.register_voter("h1", "human")
    c.register_voter("g1", "guardian")
    c.register_voter("w1", "worker")
    c.register_voter("w2", "worker")
    c.register_voter("a1", "archivist")
    c.register_voter("s1", "sensor")
    return c


def test_immutable_clause_cannot_even_be_proposed():
    c = _channel()
    with pytest.raises(ImmutableClause):
        c.propose("放松伤害限制", "no_harm_to_humans", kind=CONSTITUTIONAL)


def test_single_role_majority_blocked_in_strict_mode():
    """strict 模式：名册一失衡当场拒收。"""
    c = ConsensusChannel(strict_electorate=True)
    c.register_voter("h1", "human")
    with pytest.raises(PermissionError) as e:
        c.register_voter("g1", "guardian")   # human 5.0 vs guardian 3.0 → human 62%
    assert "单方不得过半" in str(e.value)


def test_incremental_registration_not_blocked_but_weight_capped():
    """默认模式：允许逐个注册（中间态必然失衡），失衡靠结算时权重折算兜底。"""
    c = ConsensusChannel()
    c.register_voter("h1", "human")          # 5.0
    c.register_voter("w1", "worker")         # 2.0 → human 71% 失衡但不报错
    c.register_voter("w2", "worker")         # 2.0 → human 5/9 = 56% 仍失衡
    rep = c.validate_electorate()
    assert rep["balanced"] is False and "human" in rep["offenders"]
    eff = c.effective_role_weights()
    # human 被压到与其他角色合计相等：others=4.0 → allowed=4.0
    assert eff["human"] == pytest.approx(4.0)
    assert eff["worker"] == pytest.approx(2.0)
    # 制度保证：名义口径 human(5) > 两个 worker(4) 本可独断通过，
    # 折算后 human 被压到 4.0，与 worker 打平 → 无法独裁，提案不通过。
    p = c.propose("单方能否独裁", "clause.dictator", proposer="h1")
    c.vote(p.pid, "h1", True)
    c.vote(p.pid, "w1", False)
    c.vote(p.pid, "w2", False)
    nominal = c.get(p.pid).tally()                     # 存档口径＝名义权重
    assert nominal["yes"] == pytest.approx(5.0) and nominal["no"] == pytest.approx(4.0)
    c.close(p.pid)
    assert c.get(p.pid).status == REJECTED
    assert "折算" in c.get(p.pid).outcome_reason


def test_ordinary_proposal_passes_by_majority():
    c = _channel()
    p = c.propose("默认搜索源改为 anysearch", "search.default", proposer="w1")
    for v in ("h1", "g1", "w1"):
        c.vote(p.pid, v, True)
    c.vote(p.pid, "s1", False)
    c.close(p.pid)
    assert c.get(p.pid).status == PASSED


def test_constitutional_needs_supermajority_and_turnout():
    c = _channel()
    p = c.propose("新增条款", "new.clause", kind=CONSTITUTIONAL, proposer="g1")
    c.vote(p.pid, "h1", True)
    c.vote(p.pid, "g1", True)
    c.close(p.pid)
    assert c.get(p.pid).status == REJECTED
    assert "投票率" in c.get(p.pid).outcome_reason


def test_constitutional_passes_with_enough_support():
    c = _channel()
    p = c.propose("新增条款", "new.clause2", kind=CONSTITUTIONAL, proposer="g1")
    for v in ("h1", "g1", "w1", "w2", "a1"):
        c.vote(p.pid, v, True)
    c.vote(p.pid, "s1", False)
    c.close(p.pid)
    assert c.get(p.pid).status == PASSED


def test_no_double_voting_and_no_unregistered_voter():
    c = _channel()
    p = c.propose("x", "clause.x")
    c.vote(p.pid, "w1", True)
    with pytest.raises(PermissionError):
        c.vote(p.pid, "w1", False)
    with pytest.raises(PermissionError):
        c.vote(p.pid, "stranger", True)


def test_debate_period_blocks_early_vote():
    c = ConsensusChannel(debate_seconds=60)
    c.register_voter("h1", "human")
    c.register_voter("w1", "worker")
    c.register_voter("w2", "worker")
    p = c.propose("急提案", "clause.rush", now=0)
    with pytest.raises(PermissionError) as e:
        c.vote(p.pid, "w1", True, now=10)
    assert "辩论期" in str(e.value)
    c.vote(p.pid, "w1", True, now=61)     # 辩论期满可投


def test_closed_proposal_locked_and_archived():
    c = _channel()
    p = c.propose("y", "clause.y")
    c.vote(p.pid, "h1", True)
    c.close(p.pid)
    with pytest.raises(PermissionError):
        c.vote(p.pid, "g1", True)
    assert len(c.archive) == 1 and c.pass_rate() == 1.0


def test_withdraw_only_by_proposer():
    c = _channel()
    p = c.propose("z", "clause.z", proposer="w1")
    with pytest.raises(PermissionError):
        c.withdraw(p.pid, "w2")
    assert c.withdraw(p.pid, "w1").status == "withdrawn"
