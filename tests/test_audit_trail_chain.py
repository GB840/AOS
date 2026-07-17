"""测试审计链式哈希（V8修复验证）"""
import pytest
from kernel.compliance import AuditTrail


def test_audit_trail_chain_hash():
    """测试AuditEntry使用chain_hash字段"""
    trail = AuditTrail()

    # 记录3条审计
    entry1 = trail.record("agent1", "chat", "resource1")
    entry2 = trail.record("agent1", "skill_call", "resource2")
    entry3 = trail.record("agent2", "agent_register", "resource3")

    # 验证每条记录都有chain_hash
    assert entry1.chain_hash != ""
    assert entry2.chain_hash != ""
    assert entry3.chain_hash != ""

    # 验证链式关系
    assert entry2.prev_hash == entry1.entry_hash
    assert entry3.prev_hash == entry2.entry_hash

    # 验证chain_hash计算正确
    import hashlib
    assert entry1.chain_hash == hashlib.sha256(f"{entry1.prev_hash}|{entry1.entry_hash}".encode()).hexdigest()
    assert entry2.chain_hash == hashlib.sha256(f"{entry2.prev_hash}|{entry2.entry_hash}".encode()).hexdigest()
    assert entry3.chain_hash == hashlib.sha256(f"{entry3.prev_hash}|{entry3.entry_hash}".encode()).hexdigest()


def test_audit_trail_chain_consistency():
    """测试审计链的一致性"""
    trail = AuditTrail()

    entries = []
    for i in range(10):
        entry = trail.record(f"agent{i}", f"action{i}", f"resource{i}")
        entries.append(entry)

    # 验证每条记录的chain_hash都正确
    import hashlib
    for entry in entries:
        expected_chain_hash = hashlib.sha256(f"{entry.prev_hash}|{entry.entry_hash}".encode()).hexdigest()
        assert entry.chain_hash == expected_chain_hash

    # 验证链的连续性
    for i in range(1, len(entries)):
        assert entries[i].prev_hash == entries[i-1].entry_hash


def test_audit_trail_query():
    """测试审计查询功能"""
    trail = AuditTrail()

    trail.record("agent1", "chat", "resource1")
    trail.record("agent1", "skill_call", "resource2")
    trail.record("agent2", "agent_register", "resource3")

    # 按actor查询
    results = trail.query(actor="agent1")
    assert len(results) == 2
    assert all(r.actor == "agent1" for r in results)

    # 按action查询
    results = trail.query(action="chat")
    assert len(results) == 1
    assert results[0].action == "chat"