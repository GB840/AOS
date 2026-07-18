"""概念2 农耕层循环记忆（memory_lifecycle）专项测试。

覆盖：TTL 过期降级、访问热度延缓降级、偏好记忆永生、分层降级、
量化报告、与 MemoryDistiller 端到端接入、无 lifecycle 向后兼容。
纯标准库、用可控 now_provider，秒级运行，不触发重型冷导入。
"""
import json
import os
import tempfile

from kernel.memory_lifecycle import (
    MemoryLifecycleManager,
    TIER_ETERNAL, TIER_IMPORTANT, TIER_NORMAL, TIER_ARCHIVED,
)
from kernel.memory_distiller import DistilledMemory, MemoryDistiller


def _mgr(d, now=1000.0):
    return MemoryLifecycleManager(os.path.join(d, "lc.json"),
                                  now_provider=lambda: now)


def test_register_tier_mapping():
    with tempfile.TemporaryDirectory() as d:
        mgr = _mgr(d)
        items = [
            DistilledMemory(text="f", category="failure_pattern", source="s", confidence=0.3),
            DistilledMemory(text="r", category="capability_reliability", source="s", confidence=0.9),
            DistilledMemory(text="l", category="latency_fact", source="s", confidence=0.3),
        ]
        assert mgr.register(items) == 3
        rep = mgr.report()
        assert rep["by_tier"][TIER_NORMAL] == 2     # failure + latency
        assert rep["by_tier"][TIER_IMPORTANT] == 1  # reliability


def test_register_idempotent():
    with tempfile.TemporaryDirectory() as d:
        mgr = _mgr(d)
        it = DistilledMemory(text="x", category="fact", source="s", confidence=0.5)
        assert mgr.register([it]) == 1
        assert mgr.register([it]) == 0  # 同 id 跳过，幂等


def test_preference_eternal():
    with tempfile.TemporaryDirectory() as d:
        mgr = _mgr(d)
        it = DistilledMemory(text="p", category="fact", source="s", confidence=0.5,
                             metadata={"kind": "preference"})
        mgr.register([it])
        assert mgr.mark_preference(it.id) is True
        assert mgr.report()["by_tier"][TIER_ETERNAL] == 1


def test_recall_heats_and_ranks():
    with tempfile.TemporaryDirectory() as d:
        mgr = _mgr(d)
        a = DistilledMemory(text="a", category="fact", source="s", confidence=0.9)
        b = DistilledMemory(text="b", category="fact", source="s", confidence=0.3)
        mgr.register([a, b])
        # a 召回两次升温，置信也高 -> 始终排在 b 前
        mgr.recall([a.to_record(), b.to_record()])
        mgr.recall([a.to_record(), b.to_record()])
        r = mgr.recall([a.to_record(), b.to_record()])
        assert r[0]["text"] == "a"


def test_prune_ttl_demote_and_archive():
    with tempfile.TemporaryDirectory() as d:
        now = [1000.0]
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"),
                                     now_provider=lambda: now[0])
        normal = DistilledMemory(text="n", category="latency_fact", source="s", confidence=0.3)
        imp = DistilledMemory(text="i", category="capability_reliability", source="s", confidence=0.9)
        mgr.register([normal, imp])
        now[0] = 1000.0 + 100 * 86400  # 100 天后未访问
        rep = mgr.prune()
        assert rep.archived == 1   # normal -> archived
        assert rep.demoted == 1    # important -> normal
        rep2 = mgr.prune()
        assert rep2.archived == 1  # 已降为 normal 的 important 现归档
        final = mgr.report()
        assert final["by_tier"][TIER_ARCHIVED] == 2
        assert final["total"] == 2  # 归档不物理删


def test_high_heat_delays_expiry():
    with tempfile.TemporaryDirectory() as d:
        now = [1000.0]
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"),
                                     now_provider=lambda: now[0])
        it = DistilledMemory(text="h", category="latency_fact", source="s", confidence=0.3)
        mgr.register([it])
        rec = it.to_record()
        for _ in range(10):
            mgr.recall([rec])  # 高热度
        now[0] = 1000.0 + 15 * 86400  # 15天 < effective_ttl(21天)，高热度延缓生效
        rep = mgr.prune()
        assert rep.expired == 0  # 高热度延缓降级
        assert mgr.report()["by_tier"][TIER_NORMAL] == 1
        # 高热度非永久：远超 effective_ttl 仍降级（延缓有上限）
        now[0] = 1000.0 + 100 * 86400
        rep2 = mgr.prune()
        assert rep2.archived == 1
        assert mgr.report()["by_tier"][TIER_ARCHIVED] == 1


def test_eternal_never_pruned():
    with tempfile.TemporaryDirectory() as d:
        now = [1000.0]
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"),
                                     now_provider=lambda: now[0])
        it = DistilledMemory(text="e", category="fact", source="s", confidence=0.9)
        mgr.register([it])
        mgr.mark_preference(it.id)
        now[0] = 1000.0 + 1000 * 86400
        rep = mgr.prune()
        assert rep.expired == 0
        assert mgr.report()["by_tier"][TIER_ETERNAL] == 1


def test_distiller_lifecycle_integration():
    tmp = tempfile.mkdtemp()
    sidecar = os.path.join(tmp, "distilled_lifecycle.json")
    dist = MemoryDistiller(trace_dirs=[tmp], interval_seconds=300,
                           lifecycle_path=sidecar)
    trace = {
        "input": {"task": "t1"},
        "steps": [
            {"capability": "media.video", "ok": False, "error": "render fail"},
            {"capability": "media.video", "ok": True},
        ],
        "metrics": {"latency_ms": 1234},
    }
    with open(os.path.join(tmp, "trace_test.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f)
    rep = dist.scan_once()
    assert rep.new_items >= 1
    assert os.path.exists(sidecar)
    with open(sidecar, encoding="utf-8") as f:
        meta = json.load(f)
    assert len(meta) == rep.new_items  # 每条提炼都登记生命周期
    assert isinstance(dist.recall_memories(limit=10), list)
    prep = dist._lifecycle.prune()
    assert prep.scanned == rep.new_items


def test_distiller_no_lifecycle_compat():
    tmp = tempfile.mkdtemp()
    dist = MemoryDistiller(trace_dirs=[tmp])  # 不传 lifecycle_path
    assert dist._lifecycle is None
    assert dist.recall_memories() == []
    trace = {
        "input": {"task": "t2"},
        "steps": [{"capability": "x", "ok": True}],
        "metrics": {},
    }
    with open(os.path.join(tmp, "trace_nolc.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f)
    rep = dist.scan_once()
    assert rep.new_items >= 1
    assert not os.path.exists(os.path.join(tmp, "distilled_lifecycle.json"))
