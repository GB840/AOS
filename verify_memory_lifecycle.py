"""概念2 农耕层循环记忆——秒级真跑验证（纯标准库，绕过重型冷导入）。

直接调用 kernel.memory_lifecycle / kernel.memory_distiller，验证：
TTL 过期降级、热度延缓、偏好永生、分层降级、量化报告、distiller 端到端接入。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("src"))

from kernel.memory_lifecycle import (
    MemoryLifecycleManager,
    TIER_ETERNAL, TIER_IMPORTANT, TIER_NORMAL, TIER_ARCHIVED,
)
from kernel.memory_distiller import DistilledMemory, MemoryDistiller

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}")


def test_register_mapping():
    with tempfile.TemporaryDirectory() as d:
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: 1000.0)
        items = [
            DistilledMemory(text="f", category="failure_pattern", source="s", confidence=0.3),
            DistilledMemory(text="r", category="capability_reliability", source="s", confidence=0.9),
            DistilledMemory(text="l", category="latency_fact", source="s", confidence=0.3),
        ]
        check("register 返回3条", mgr.register(items) == 3)
        rep = mgr.report()
        check("failure+latency→normal(2)", rep["by_tier"][TIER_NORMAL] == 2)
        check("reliability→important(1)", rep["by_tier"][TIER_IMPORTANT] == 1)


def test_idempotent():
    with tempfile.TemporaryDirectory() as d:
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: 1000.0)
        it = DistilledMemory(text="x", category="fact", source="s", confidence=0.5)
        check("首次登记=1", mgr.register([it]) == 1)
        check("重复登记=0(幂等)", mgr.register([it]) == 0)


def test_preference_eternal():
    with tempfile.TemporaryDirectory() as d:
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: 1000.0)
        it = DistilledMemory(text="p", category="fact", source="s", confidence=0.5,
                             metadata={"kind": "preference"})
        mgr.register([it])
        check("mark_preference→True", mgr.mark_preference(it.id) is True)
        check("偏好记忆→永生层", mgr.report()["by_tier"][TIER_ETERNAL] == 1)


def test_recall_heat():
    with tempfile.TemporaryDirectory() as d:
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: 1000.0)
        a = DistilledMemory(text="a", category="fact", source="s", confidence=0.9)
        b = DistilledMemory(text="b", category="fact", source="s", confidence=0.3)
        mgr.register([a, b])
        mgr.recall([a.to_record(), b.to_record()])
        mgr.recall([a.to_record(), b.to_record()])
        r = mgr.recall([a.to_record(), b.to_record()])
        check("召回按热度*置信排序(a在前)", r[0]["text"] == "a")


def test_prune_demote_archive():
    with tempfile.TemporaryDirectory() as d:
        now = [1000.0]
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: now[0])
        normal = DistilledMemory(text="n", category="latency_fact", source="s", confidence=0.3)
        imp = DistilledMemory(text="i", category="capability_reliability", source="s", confidence=0.9)
        mgr.register([normal, imp])
        now[0] = 1000.0 + 100 * 86400
        rep = mgr.prune()
        check("normal→归档(1)", rep.archived == 1)
        check("important→降级(1)", rep.demoted == 1)
        rep2 = mgr.prune()
        check("二次prune important已归档(1)", rep2.archived == 1)
        final = mgr.report()
        check("归档共2条", final["by_tier"][TIER_ARCHIVED] == 2)
        check("归档不物理删(total=2)", final["total"] == 2)


def test_high_heat_delays():
    with tempfile.TemporaryDirectory() as d:
        now = [1000.0]
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: now[0])
        it = DistilledMemory(text="h", category="latency_fact", source="s", confidence=0.3)
        mgr.register([it])
        rec = it.to_record()
        for _ in range(10):
            mgr.recall([rec])
        now[0] = 1000.0 + 15 * 86400
        rep = mgr.prune()
        check("高热度延缓降级(15天不过期)", rep.expired == 0)
        check("仍留在normal层", mgr.report()["by_tier"][TIER_NORMAL] == 1)
        now[0] = 1000.0 + 100 * 86400
        rep2 = mgr.prune()
        check("高热度非永久(100天归档)", rep2.archived == 1)
        check("最终降至归档层", mgr.report()["by_tier"][TIER_ARCHIVED] == 1)


def test_eternal_never():
    with tempfile.TemporaryDirectory() as d:
        now = [1000.0]
        mgr = MemoryLifecycleManager(os.path.join(d, "lc.json"), now_provider=lambda: now[0])
        it = DistilledMemory(text="e", category="fact", source="s", confidence=0.9)
        mgr.register([it])
        mgr.mark_preference(it.id)
        now[0] = 1000.0 + 1000 * 86400
        rep = mgr.prune()
        check("永生不降级(expired=0)", rep.expired == 0)
        check("永生层计数=1", mgr.report()["by_tier"][TIER_ETERNAL] == 1)


def test_distiller_integration():
    tmp = tempfile.mkdtemp()
    sidecar = os.path.join(tmp, "distilled_lifecycle.json")
    dist = MemoryDistiller(trace_dirs=[tmp], interval_seconds=300, lifecycle_path=sidecar)
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
    check("distiller提炼≥1条", rep.new_items >= 1)
    check("生命周期侧车已生成", os.path.exists(sidecar))
    with open(sidecar, encoding="utf-8") as f:
        meta = json.load(f)
    check("每条提炼都登记生命周期", len(meta) == rep.new_items)
    check("recall_memories返回list", isinstance(dist.recall_memories(limit=10), list))
    prep = dist._lifecycle.prune()
    check("prune扫描数=登记数", prep.scanned == rep.new_items)


def test_distiller_compat():
    tmp = tempfile.mkdtemp()
    dist = MemoryDistiller(trace_dirs=[tmp])
    check("无lifecycle_path→None(向后兼容)", dist._lifecycle is None)
    check("无lifecycle→recall返回[]", dist.recall_memories() == [])
    trace = {"input": {"task": "t2"}, "steps": [{"capability": "x", "ok": True}], "metrics": {}}
    with open(os.path.join(tmp, "trace_nolc.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f)
    rep = dist.scan_once()
    check("无lifecycle也能提炼", rep.new_items >= 1)
    check("无侧车文件生成", not os.path.exists(os.path.join(tmp, "distilled_lifecycle.json")))


def test_public_api_methods():
    tmp = tempfile.mkdtemp()
    sidecar = os.path.join(tmp, "distilled_lifecycle.json")
    dist = MemoryDistiller(trace_dirs=[tmp], lifecycle_path=sidecar)
    rep = dist.lifecycle_report()
    check("lifecycle_report 返回含 by_tier 的字典", rep is not None and "by_tier" in rep)
    p = dist.lifecycle_prune()
    check("lifecycle_prune 返回含 scanned 的字典", isinstance(p, dict) and "scanned" in p)
    # 无 lifecycle 时公开方法返回 None（API 端点据此返回 disabled）
    dist2 = MemoryDistiller(trace_dirs=[tempfile.mkdtemp()])
    check("无lifecycle时 report 返回 None", dist2.lifecycle_report() is None)
    check("无lifecycle时 prune 返回 None", dist2.lifecycle_prune() is None)


if __name__ == "__main__":
    print("=== 概念2 农耕层循环记忆 verify ===")
    test_register_mapping()
    test_idempotent()
    test_preference_eternal()
    test_recall_heat()
    test_prune_demote_archive()
    test_high_heat_delays()
    test_eternal_never()
    test_distiller_integration()
    test_distiller_compat()
    test_public_api_methods()
    print(f"\n=== 结果: {_passed} passed, {_failed} failed ===")
    sys.exit(1 if _failed else 0)
