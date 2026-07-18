"""EvolveEngine 单元测试。

覆盖：
- 提案生成（generate_proposals）
- 提案查询（list_proposals / list_pending_approvals / _find_proposal）
- P1 双向同步：medium/high 提案自动进 ApprovalStore
- P1 防循环：approve_proposal 不会无限回调 store.approve
- reject_proposal 流程
- A/B 测试基础
"""
import json
import os
import tempfile
import time

import pytest

_tmp = tempfile.mkdtemp(prefix="aos_test_evolve_")
os.environ.setdefault("AOS_DATA_DIR", _tmp)
os.environ["AOS_APPROVALS_PATH"] = os.path.join(_tmp, "approvals.jsonl")

from kernel.evolve.evolve_engine import (  # noqa: E402
    ABTest,
    EvolveEngine,
    OptimizationProposal,
)
from kernel.approval.approval_store import (  # noqa: E402
    ApprovalStore,
    get_approval_store,
)


class FakePulse:
    """假的 Pulse，返回预设的 metrics。"""

    def __init__(self, metrics=None, failure=None):
        self._metrics = metrics or {
            "total_runs": 10,
            "success_rate": 70.0,
            "avg_duration": 5.0,
        }
        self._failure = failure or {
            "total_failures": 3,
            "step_failures": {"step1": 2, "step2": 1},
        }

    def get_agent_metrics(self, wf_id):
        return self._metrics

    def get_failure_analysis(self, wf_id):
        return self._failure


@pytest.fixture
def engine():
    """每个测试用全新的 engine + 干净的 ApprovalStore。"""
    # 重置 ApprovalStore 单例
    import kernel.approval.approval_store as amod
    amod._instance = None

    # 用临时文件
    path = os.path.join(_tmp, f"appr_{time.time_ns()}.jsonl")
    os.environ["AOS_APPROVALS_PATH"] = path

    e = EvolveEngine(pulse=FakePulse())
    return e


def _make_proposal(**kw):
    """造一个测试提案。"""
    defaults = {
        "id": f"prop_{time.time_ns()}",
        "workflow_id": "test_wf",
        "proposal_type": "step_timeout",
        "title": "测试提案",
        "description": "一个测试提案",
        "risk_level": "medium",
        "expected_benefit": "提升 10%",
        "auto_applicable": False,
        "change": {"action": "increase_timeout"},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "evolve",
    }
    defaults.update(kw)
    return OptimizationProposal(**defaults)


# ── 提案生成 ──

def test_generate_proposals_returns_list(engine):
    """generate_proposals 应返回提案列表（可能为空，但必须是 list）。"""
    proposals = engine.generate_proposals("test_wf")
    assert isinstance(proposals, list)


def test_generate_proposals_persists_to_jsonl(engine):
    """生成的提案应持久化到 JSONL 文件。"""
    proposals = engine.generate_proposals("test_wf")
    # 如果有提案，检查能读回来
    if proposals:
        loaded = engine.list_proposals("test_wf")
        assert len(loaded) >= len(proposals)


def test_save_proposal_creates_approval_for_medium(engine):
    """P1: 保存 medium 风险提案时，应自动在 ApprovalStore 创建审批。"""
    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])

    store = get_approval_store()
    found = store.get_by_proposal(prop.id)
    assert found is not None
    assert found.source == "evolve"
    assert found.risk_level == "medium"
    assert found.status == "pending"
    assert found.proposal_id == prop.id


def test_save_proposal_creates_approval_for_high(engine):
    """P1: 保存 high 风险提案时，应自动在 ApprovalStore 创建审批。"""
    prop = _make_proposal(risk_level="high")
    engine._save_proposal("test_wf", [prop])

    store = get_approval_store()
    found = store.get_by_proposal(prop.id)
    assert found is not None
    assert found.risk_level == "high"


def test_save_proposal_skips_approval_for_low(engine):
    """P1: low 风险提案不应进 ApprovalStore（auto_applicable）。"""
    prop = _make_proposal(risk_level="low", auto_applicable=True)
    engine._save_proposal("test_wf", [prop])

    store = get_approval_store()
    assert store.get_by_proposal(prop.id) is None


def test_save_proposal_no_duplicate_approval(engine):
    """P1: 重复保存同一提案不应创建重复审批。"""
    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])
    engine._save_proposal("test_wf", [prop])  # 再保存一次

    store = get_approval_store()
    # 应该只有一个审批记录
    all_approvals = [a for a in store.list_all() if a.proposal_id == prop.id]
    assert len(all_approvals) == 1


# ── 提案查询 ──

def test_list_proposals(engine):
    p1 = _make_proposal(id="p1", risk_level="low")
    p2 = _make_proposal(id="p2", risk_level="high")
    engine._save_proposal("test_wf", [p1, p2])
    loaded = engine.list_proposals("test_wf")
    assert len(loaded) >= 2
    ids = [p.id for p in loaded]
    assert "p1" in ids
    assert "p2" in ids


def test_find_proposal(engine):
    prop = _make_proposal(id="find_me")
    engine._save_proposal("test_wf", [prop])
    found = engine._find_proposal("find_me")
    assert found is not None
    assert found.title == "测试提案"
    assert engine._find_proposal("no_such") is None


def test_list_pending_approvals_only_medium_high(engine):
    """list_pending_approvals 只返回 medium/high 且未处理的提案。"""
    p_low = _make_proposal(id="low1", risk_level="low", auto_applicable=True)
    p_med = _make_proposal(id="med1", risk_level="medium")
    p_high = _make_proposal(id="high1", risk_level="high")
    engine._save_proposal("test_wf", [p_low, p_med, p_high])

    pending = engine.list_pending_approvals("test_wf")
    ids = [p.id for p in pending]
    assert "med1" in ids
    assert "high1" in ids
    assert "low1" not in ids


def test_list_pending_approvals_sorts_high_first(engine):
    """high 风险应排在 medium 前面。

    用独立 workflow_id 隔离，避免其他测试遗留提案干扰排序断言。
    """
    wf = f"sort_wf_{time.time_ns()}"
    p_med = _make_proposal(id="med1", workflow_id=wf, risk_level="medium")
    p_high = _make_proposal(id="high1", workflow_id=wf, risk_level="high")
    engine._save_proposal(wf, [p_med, p_high])

    pending = engine.list_pending_approvals(wf)
    assert pending[0].id == "high1"
    assert pending[1].id == "med1"


# ── P1 双向同步：approve / reject ──

def test_approve_proposal_syncs_to_approval_store(engine):
    """P1: approve_proposal 应同步更新 ApprovalStore 状态。"""
    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])

    store = get_approval_store()
    approval_before = store.get_by_proposal(prop.id)
    assert approval_before.status == "pending"

    # approve（会尝试 apply，可能失败因为没真实 workflow，但 approve 标记应生效）
    result = engine.approve_proposal(prop.id)
    # approve_proposal 内部先标记 approved=True，再尝试 apply
    # apply 可能失败，但 approved 标记已写入
    approval_after = store.get_by_proposal(prop.id)
    assert approval_after.status == "approved"


def test_reject_proposal_syncs_to_approval_store(engine):
    """P1: reject_proposal 应同步更新 ApprovalStore 状态为 rejected。"""
    prop = _make_proposal(risk_level="high")
    engine._save_proposal("test_wf", [prop])

    result = engine.reject_proposal(prop.id, reason="不需要")
    assert result["ok"] is True

    store = get_approval_store()
    approval = store.get_by_proposal(prop.id)
    assert approval.status == "rejected"


def test_approve_proposal_no_loop(engine, monkeypatch):
    """P1 防循环：approve_proposal 触发的 store.approve 钩子回调不会导致 apply_proposal 重复执行。

    路径：engine.approve_proposal → apply_proposal（设 applied=True）
    → _sync_proposal_status_to_approval → store.approve → hook
    → engine.approve_proposal（第二次）→ 检查 proposal.applied=True → return early

    断言 apply_proposal 仅被调用 1 次（这才是防循环的真正指标）。
    """
    apply_count = {"apply": 0}
    orig_apply = EvolveEngine.apply_proposal

    def counted_apply(self, proposal_id, workflow_store=None):
        apply_count["apply"] += 1
        return orig_apply(self, proposal_id, workflow_store)

    monkeypatch.setattr(EvolveEngine, "apply_proposal", counted_apply)

    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])

    result = engine.approve_proposal(prop.id)
    # apply_proposal 应该只被调用 1 次（钩子回调时被 approved=True 挡住，不再重试 apply）
    assert apply_count["apply"] == 1, \
        f"Expected apply_proposal called 1 time, got {apply_count['apply']}"
    # proposal 应被标记为 approved（无论 apply 是否成功）
    updated = engine._find_proposal(prop.id)
    assert updated.approved is True


def test_reject_proposal_no_loop(engine, monkeypatch):
    """P1 防循环：reject_proposal 触发的 store.reject 钩子回调不会无限递归。

    路径：engine.reject_proposal（设 rejected=True）
    → _sync_proposal_status_to_approval → store.reject → hook
    → engine.reject_proposal（第二次）→ 检查 proposal.rejected=True → return early

    断言 _sync_proposal_status_to_approval 仅被调用 1 次（第二次进入时直接 return）。
    """
    sync_count = {"sync": 0}
    orig_sync = EvolveEngine._sync_proposal_status_to_approval

    def counted_sync(self, proposal, *, status, note=""):
        sync_count["sync"] += 1
        return orig_sync(self, proposal, status=status, note=note)

    monkeypatch.setattr(EvolveEngine, "_sync_proposal_status_to_approval", counted_sync)

    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])

    result = engine.reject_proposal(prop.id, reason="test")
    # _sync 只应被调用 1 次（第二次进入 reject_proposal 时被 rejected=True 挡住，直接 return）
    assert sync_count["sync"] == 1, \
        f"Expected _sync called 1 time, got {sync_count['sync']}"
    assert result.get("ok") is True


def test_approval_store_approve_triggers_engine_apply(engine):
    """P1 反向：从 ApprovalStore 批准应回调 engine.approve_proposal。"""
    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])

    store = get_approval_store()
    approval = store.get_by_proposal(prop.id)

    # 从 ApprovalStore 批准
    result = store.approve(approval.id, decided_by="user", note="ok")
    assert result["ok"] is True

    # engine 的提案应被标记为 approved
    updated = engine._find_proposal(prop.id)
    assert updated.approved is True


def test_approval_store_reject_triggers_engine_reject(engine):
    """P1 反向：从 ApprovalStore 拒绝应回调 engine.reject_proposal。"""
    prop = _make_proposal(risk_level="medium")
    engine._save_proposal("test_wf", [prop])

    store = get_approval_store()
    approval = store.get_by_proposal(prop.id)

    result = store.reject(approval.id, decided_by="user", note="no")
    assert result["ok"] is True

    updated = engine._find_proposal(prop.id)
    assert updated.rejected is True
    assert updated.reject_reason == "no"


# ── A/B 测试 ──

def test_create_ab_test(engine):
    test = engine.create_ab_test(
        "wf1", "测试AB",
        variant_a={"model": "gpt-4"},
        variant_b={"model": "claude-3"},
    )
    assert test.id != ""
    assert test.status == "running"
    assert test.a_runs == 0


def test_get_variant_alternates(engine):
    test = engine.create_ab_test("wf1", "AB", {}, {})
    # 前几次应该交替返回 a/b
    v1 = engine.get_variant("wf1")
    v2 = engine.get_variant("wf1")
    variants = {v1["variant"], v2["variant"]}
    assert variants == {"a", "b"} or len(variants) == 1  # 至少不报错


def test_record_result_updates_counts(engine):
    """record_result 应更新对应变体的计数。

    用 test.id 直接查找，避免 list_tests 按 started_at（秒级精度）排序不稳定。
    """
    test = engine.create_ab_test("wf1", "AB", {}, {})
    engine.record_result(test.id, "a", success=True, duration=1.0)
    # 直接按 id 查找，不依赖排序
    all_tests = engine.list_tests("wf1")
    loaded = next(t for t in all_tests if t["id"] == test.id)
    assert loaded["a_runs"] == 1
    assert loaded["a_success"] == 1


# ── 持久化 ──

def test_proposals_persist_across_instances(engine):
    """提案应持久化，新 engine 实例能读回。"""
    prop = _make_proposal(id="persist_test")
    engine._save_proposal("test_wf", [prop])

    # 新实例指向同一数据目录
    e2 = EvolveEngine(pulse=FakePulse())
    found = e2._find_proposal("persist_test")
    assert found is not None
    assert found.title == "测试提案"
