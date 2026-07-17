"""常驻记忆提炼 Agent 验证（借鉴 Jcode 的常驻记忆提炼思路）。

覆盖：trace 提炼出三类事实、route_outcomes 提炼、防重复提炼、单例、置信度三级。
mem0 增强通道在测试里显式禁用（mem0_store=None），只验证「扫描+提炼+jsonl 落盘」
核心逻辑（理念9 白盒进化根基），不依赖 mem0 在线。
"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.memory_distiller import (  # noqa: E402
    MemoryDistiller,
    get_distiller,
    _confidence_for,
)


def _write_trace(d, name, steps, latency=100, task="测试任务"):
    data = {
        "input": {"task": task},
        "steps": steps,
        "output": {
            "ok_steps": [s for s in steps if s.get("ok")],
            "failed_steps": [s for s in steps if not s.get("ok")],
        },
        "metrics": {"latency_ms": latency},
    }
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _write_routes(d, rows):
    with open(os.path.join(d, "route_outcomes.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_out(dist):
    with open(dist.out_path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_distill_trace_three_categories():
    tmp = tempfile.mkdtemp()
    _write_trace(tmp, "trace_1.json", [
        {"capability": "web-search", "ok": True},
        {"capability": "code-exec", "ok": False, "error": "timeout"},
    ], latency=250, task="搜索并跑代码")
    dist = MemoryDistiller(trace_dirs=[tmp], mem0_store=None)
    rep = dist.scan_once()
    assert rep.new_items > 0, rep.to_dict()
    recs = _read_out(dist)
    cats = {x["category"] for x in recs}
    assert "failure_pattern" in cats
    assert "capability_reliability" in cats
    assert "latency_fact" in cats
    # 防重复：第二次扫描应无新条目
    rep2 = dist.scan_once()
    assert rep2.new_items == 0, rep2.to_dict()


def test_distill_route_outcomes():
    tmp = tempfile.mkdtemp()
    _write_routes(tmp, [
        {"capability": "web-search", "engine": "agnes", "ok": True, "latency_ms": 80},
        {"capability": "web-search", "engine": "agnes", "ok": True, "latency_ms": 90},
        {"capability": "web-search", "engine": "agnes", "ok": False,
         "error": "403", "latency_ms": 30},
    ])
    dist = MemoryDistiller(trace_dirs=[tmp], mem0_store=None)
    rep = dist.scan_once()
    assert rep.new_items >= 2, rep.to_dict()
    recs = _read_out(dist)
    assert any(r["category"] == "capability_reliability" for r in recs)
    assert any(r["category"] == "failure_pattern" for r in recs)
    # reliability 聚合 2/3
    rel = [r for r in recs if r["category"] == "capability_reliability"][0]
    assert rel["metadata"]["ok"] == 2 and rel["metadata"]["total"] == 3


def test_confidence_three_levels():
    assert _confidence_for(1) == 0.3
    assert _confidence_for(3) == 0.6
    assert _confidence_for(7) == 0.9


def test_get_distiller_singleton():
    d1 = get_distiller(mem0_store=None)
    d2 = get_distiller(mem0_store=None)
    assert d1 is d2
