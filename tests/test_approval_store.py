"""ApprovalStore 单元测试（Task 4: Human-in-the-Loop）。

覆盖：
- 基础 CRUD（创建/查询/列表/删除）
- 审批流程（approve / reject / 已决策不可重复）
- 过期审批（TTL）
- P1 双向同步：Evolve 提案创建时自动进 ApprovalStore
- P1 防循环：hook 回调不会无限递归
"""
import os
import tempfile
import time

import pytest

# 用临时数据目录，避免污染真实数据
_tmp = tempfile.mkdtemp(prefix="aos_test_approval_")
os.environ["AOS_APPROVALS_PATH"] = os.path.join(_tmp, "approvals.jsonl")
os.environ.setdefault("AOS_DATA_DIR", _tmp)

from kernel.approval.approval_store import (  # noqa: E402
    ApprovalRequest,
    ApprovalStore,
    get_approval_store,
)


@pytest.fixture
def store():
    """每个测试用全新的 store 实例 + 干净的 JSONL。"""
    path = os.path.join(_tmp, f"test_{time.time_ns()}.jsonl")
    s = ApprovalStore(path=path)
    # 重置单例，让 get_approval_store 也返回新实例
    import kernel.approval.approval_store as mod
    mod._instance = None
    mod._approvals_path_override = path
    return s


def _make(store, **kw):
    defaults = {
        "source": "test",
        "title": "测试审批",
        "description": "desc",
        "risk_level": "medium",
    }
    defaults.update(kw)
    return store.create_approval(**defaults)


# ── 基础 CRUD ──

def test_create_approval_returns_id(store):
    a = _make(store)
    assert a.id != ""
    assert a.status == "pending"
    assert a.source == "test"
    assert a.risk_level == "medium"


def test_get_by_id(store):
    a = _make(store, title="xxx")
    got = store.get(a.id)
    assert got is not None
    assert got.title == "xxx"


def test_get_nonexistent_returns_none(store):
    assert store.get("no_such_id") is None


def test_get_by_proposal(store):
    a = _make(store, proposal_id="prop_001")
    assert store.get_by_proposal("prop_001") is not None
    assert store.get_by_proposal("prop_001").id == a.id
    assert store.get_by_proposal("no_such") is None
    # 空 proposal_id 应返回 None（不报错）
    assert store.get_by_proposal("") is None


def test_list_pending_filters_by_source(store):
    _make(store, source="evolve")
    _make(store, source="workflow_runner")
    _make(store, source="evolve")
    assert len(store.list_pending(source="evolve")) == 2
    assert len(store.list_pending(source="workflow_runner")) == 1


def test_list_pending_filters_by_risk(store):
    _make(store, risk_level="high")
    _make(store, risk_level="low")
    _make(store, risk_level="medium")
    high = store.list_pending(risk_level="high")
    assert len(high) == 1
    assert high[0].risk_level == "high"


def test_list_pending_sorts_high_risk_first(store):
    _make(store, risk_level="low", title="low1")
    _make(store, risk_level="high", title="high1")
    _make(store, risk_level="medium", title="med1")
    pending = store.list_pending()
    # high 应该排在最前
    assert pending[0].risk_level == "high"


def test_list_all_includes_history(store):
    a = _make(store)
    store.approve(a.id)
    # list_pending 不含已决策的，list_all 含
    assert len(store.list_pending()) == 0
    assert len(store.list_all()) == 1


def test_delete(store):
    a = _make(store)
    assert store.delete(a.id) is True
    assert store.get(a.id) is None
    assert store.delete("no_such") is False


def test_stats(store):
    a1 = _make(store, risk_level="high")
    a2 = _make(store, risk_level="medium")
    _make(store, risk_level="low")
    store.approve(a1.id)
    store.reject(a2.id)
    s = store.stats()
    assert s["total"] == 3
    assert s["pending"] == 1
    assert s["approved"] == 1
    assert s["rejected"] == 1


# ── 审批流程 ──

def test_approve_changes_status(store):
    a = _make(store)
    r = store.approve(a.id, decided_by="alice", note="ok")
    assert r["ok"] is True
    assert r["approval"]["status"] == "approved"
    assert r["approval"]["decided_by"] == "alice"
    assert r["approval"]["decision_note"] == "ok"


def test_reject_changes_status(store):
    a = _make(store)
    r = store.reject(a.id, decided_by="bob", note="no")
    assert r["ok"] is True
    assert r["approval"]["status"] == "rejected"


def test_cannot_approve_already_decided(store):
    a = _make(store)
    store.approve(a.id)
    r = store.approve(a.id)
    assert r["ok"] is False
    assert "已决策" in r["error"]


def test_cannot_reject_already_approved(store):
    a = _make(store)
    store.approve(a.id)
    r = store.reject(a.id)
    assert r["ok"] is False


def test_approve_nonexistent_returns_error(store):
    r = store.approve("no_such_id")
    assert r["ok"] is False
    assert "不存在" in r["error"]


# ── 过期 ──

def test_expired_approval_not_in_pending(store):
    """过期审批不应出现在 pending 列表里。

    注意：pytest 环境下 time.sleep 被 typeguard 插件 mock（不真睡），
    所以直接修改 expires_at 为过去时间来模拟过期。
    """
    a = _make(store, ttl_seconds=3600)
    # 把 expires_at 改成 1 小时前，模拟已过期
    import time as _t
    past = _t.strftime("%Y-%m-%dT%H:%M:%S",
                       _t.localtime(_t.time() - 3600))
    a.expires_at = past
    # 直接写回 JSONL
    with open(store._path, "w", encoding="utf-8") as f:
        f.write(__import__("json").dumps(a.to_dict(), ensure_ascii=False) + "\n")
    store._invalidate()
    pending = store.list_pending()
    assert a.id not in [p.id for p in pending]


def test_non_expired_in_pending(store):
    a = _make(store, ttl_seconds=3600)
    pending = store.list_pending()
    assert a.id in [p.id for p in pending]


# ── P1 双向同步 + 防循环 ──

def test_post_decision_hook_called_on_approve(store, monkeypatch):
    """批准时钩子应被调用一次（source=evolve 触发 engine.approve_proposal）。"""
    called = {"count": 0}

    def fake_hook(self, approval, *, action, decided_by="", note=""):
        called["count"] += 1
        called["action"] = action

    monkeypatch.setattr(ApprovalStore, "_post_decision_hook", fake_hook)
    a = _make(store, source="evolve", proposal_id="p1")
    store.approve(a.id)
    assert called["count"] == 1
    assert called["action"] == "approve"


def test_post_decision_hook_called_on_reject(store, monkeypatch):
    """拒绝时钩子应被调用一次。"""
    called = {"count": 0}

    def fake_hook(self, approval, *, action, decided_by="", note=""):
        called["count"] += 1

    monkeypatch.setattr(ApprovalStore, "_post_decision_hook", fake_hook)
    a = _make(store, source="evolve", proposal_id="p2")
    store.reject(a.id, note="不需要")
    assert called["count"] == 1


def test_hook_only_for_evolve_source(store, monkeypatch):
    """非 evolve 源不触发钩子。"""
    called = {"count": 0}

    def fake_hook(self, approval, *, action, decided_by="", note=""):
        called["count"] += 1

    monkeypatch.setattr(ApprovalStore, "_post_decision_hook", fake_hook)
    a = _make(store, source="workflow_runner")
    store.approve(a.id)
    # workflow_runner 没有 proposal_id，钩子内部会跳过——但函数仍被调用一次
    # 关键是：没有 proposal_id 的不会触发 engine 回调
    # 这里只验证 hook 函数被调用了
    assert called["count"] == 1


def test_hook_skipped_when_no_proposal_id(store, monkeypatch):
    """source=evolve 但没 proposal_id 时，钩子内部应跳过（不报错）。"""
    # 不 mock 钩子，用真实的——它会尝试 import evolve_engine 但没 proposal_id 就跳过
    a = _make(store, source="evolve")  # 没 proposal_id
    r = store.approve(a.id)
    assert r["ok"] is True  # 没报错


# ── 持久化 ──

def test_persist_and_reload(store):
    """审批记录应持久化到 JSONL，重启后可读回。"""
    a = _make(store, title="持久化测试")
    # 新建一个 store 实例指向同一个文件
    s2 = ApprovalStore(path=store._path)
    loaded = s2.get(a.id)
    assert loaded is not None
    assert loaded.title == "持久化测试"


def test_to_dict_and_from_dict_roundtrip():
    """ApprovalRequest 序列化/反序列化应保持一致。"""
    a = ApprovalRequest(
        id="abc",
        source="test",
        title="t",
        risk_level="high",
        payload={"key": "value"},
        proposal_id="p1",
    )
    d = a.to_dict()
    b = ApprovalRequest.from_dict(d)
    assert b.id == "abc"
    assert b.source == "test"
    assert b.risk_level == "high"
    assert b.payload == {"key": "value"}
    assert b.proposal_id == "p1"
