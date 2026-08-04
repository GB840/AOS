"""债 #17 端到端追踪链测试：任务 → FabricHub.route（含降级）→ ResilienceBus 记账
→ TaskTraceStore 落 trace_*.json → MemoryDistiller.scan_once 蒸馏出
failure_pattern / capability_reliability / latency_fact。

这是把「白盒才可进化（理念8）」从生产者（trace_store.py）到消费者
（memory_distiller.py）完整串起来的端到端实证。此前两者各自存在、各自有单测，
但从没被一条真实链路验证过「trace 落盘后真能被蒸馏出可用事实」。本文件补这个缺口。

诚实分级：**② 级**（offline 单测，真 FabricHub.route + 真 ResilienceBus + 真蒸馏器，
无真 LLM 调用）。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import InvokeResult  # noqa: E402
from core.fabric.trace_store import TaskTraceStore, TracedRoute  # noqa: E402
from kernel.memory_distiller import MemoryDistiller  # noqa: E402
from kernel.plugins.fabric_hub import FabricHub, reset_fabric_hub  # noqa: E402


class _FakeAdapter:
    """可控假引擎：按自身声明的 capability 决定成功/失败，按需抛异常。"""

    def __init__(self, eid, caps, ok=True, error=None, raises=False):
        self._eid = eid
        self._caps = list(caps)
        self._ok = ok
        self._error = error
        self._raises = raises
        self.calls = 0

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return self._caps

    def health(self):
        return True

    def invoke(self, req):
        self.calls += 1
        if self._raises:
            raise RuntimeError(f"{self._eid} 崩了")
        # 只对自己声明的 capability 成功，其余视作错配失败（模拟真实引擎能力边界）
        if req.capability not in self._caps:
            return InvokeResult(ok=False, error=f"{self._eid} 不提供 {req.capability}")
        if self._ok:
            return InvokeResult(ok=True, data={"engine": self._eid, "count": 1})
        return InvokeResult(ok=False, error=self._error or "fail")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("AOS_DISTILLER_OFF", "1")  # 不引入蒸馏器噪声
    reset_fabric_hub()
    yield
    reset_fabric_hub()


def _make_hub(providers_by_cap):
    """按 capability → 适配器列表 构造隔离 hub：真 route / 真 ResilienceBus。"""
    hub = FabricHub(adapters=())
    for ad in [a for lst in providers_by_cap.values() for a in lst]:
        hub._registry._adapters[ad.engine_id] = ad
    hub._registry.providers_for = lambda cap, tier=None: list(providers_by_cap.get(cap, []))
    hub._registry.maybe_retrain = lambda *a, **k: None
    hub._registry.record_outcome = lambda *a, **k: None
    return hub


def _read_distilled(tmp_path):
    """读 MemoryDistiller 落盘的 distilled_memory.jsonl → 解析成 dict 列表。"""
    out = os.path.join(str(tmp_path), "distilled_memory.jsonl")
    items = []
    if os.path.exists(out):
        with open(out, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    return items


# ── 主链路：成功+失败混合 → trace 落盘 → 蒸馏出三类事实 ───────────────

def test_e2e_trace_chain_records_and_distills(tmp_path):
    # 两个能力：web.search 由可靠引擎承担；web.process 仅由会失败的引擎承担
    good = _FakeAdapter("good-search", ["web.search"], ok=True)
    bad = _FakeAdapter("bad-process", ["web.process"], ok=False,
                       error="HTTP 500 upstream boom")
    hub = _make_hub({"web.search": [good], "web.process": [bad]})

    store = TaskTraceStore(traces_dir=str(tmp_path))
    task_id = "task-e2e-1"
    store.begin(task_id, "搜索并加工资料")
    traced = TracedRoute(hub.route, store, task_id)

    # 步1：成功
    r1 = traced("web.search", {"query": "AOS 架构"})
    assert r1.ok is True and r1.engine_id == "good-search"
    # 步2：失败（该能力只有坏引擎 → route 整体 ok=False → 失败模式会被蒸馏）
    r2 = traced("web.process", {"text": "原始资料..."})
    assert r2.ok is False

    # flush 成 trace_<task_id>.json
    trace_path = store.finish(task_id, ok=False)
    assert trace_path is not None
    assert os.path.basename(trace_path) == f"trace_{task_id}.json", "trace_id 必须贯穿文件名"

    with open(trace_path, "r", encoding="utf-8") as f:
        trace = json.load(f)
    # trace_id 贯穿 + engine 为真实执行引擎（理念6 诚实）
    assert trace["task_id"] == task_id
    assert len(trace["steps"]) == 2
    assert trace["steps"][0]["engine"] == "good-search"
    assert trace["steps"][0]["ok"] is True
    assert trace["steps"][1]["engine"] == "bad-process"
    assert trace["steps"][1]["ok"] is False
    assert "HTTP 500" in (trace["steps"][1].get("error") or "")
    assert trace["metrics"]["latency_ms"] > 0, "延迟事实必须被累加"

    # 消费者：MemoryDistiller 蒸馏
    assert hub._res_bus is not None, "ResilienceBus 必须存在（链路一环）"
    distiller = MemoryDistiller(trace_dirs=[str(tmp_path)], interval_seconds=1)
    report = distiller.scan_once()

    assert report.scanned_files >= 1
    assert report.new_items >= 3, f"至少应蒸馏出 失败模式+能力可靠性×2+延迟事实，实得 {report.new_items}"
    assert report.by_category.get("failure_pattern", 0) >= 1
    assert report.by_category.get("capability_reliability", 0) >= 2  # 两个能力各一条
    assert report.by_category.get("latency_fact", 0) >= 1

    # 落到盘上的内容可被召回（验证蒸馏文本诚实呈现真实引擎/能力/错误）
    items = _read_distilled(tmp_path)
    texts = "\n".join(it["text"] for it in items)
    assert "失败模式" in texts and "bad-process" in texts and "HTTP 500" in texts
    # 能力可靠性按 capability 聚合（非引擎），文本呈现的是能力名
    assert "能力可靠性" in texts and "web.search" in texts and "100%" in texts
    assert "延迟事实" in texts and ("搜索并加工资料" in texts or "task-e2e-1" in texts)


# ── 链路一环：内部失败仍喂给 ResilienceBus，连续失败触发熔断 ───────────
# 注意：当坏引擎排在前面、但后面有兜底好引擎时，整体 route 仍 ok=True
# （任务成功），但坏引擎的内部失败已被 ResilienceBus 记账 → 熔断器独立动作。

def test_e2e_trace_chain_feeds_circuit_breaker(tmp_path):
    bad = _FakeAdapter("bad-k", ["web.search"], ok=False, error="boom")
    good = _FakeAdapter("good-k", ["web.search"], ok=True)
    hub = _make_hub({"web.search": [bad, good]})

    store = TaskTraceStore(traces_dir=str(tmp_path))
    task_id = "task-cb-1"
    store.begin(task_id, "连续撞坏引擎但兜底成功")
    traced = TracedRoute(hub.route, store, task_id)

    # 连续 3 次：每次先撞 bad（失败被记账），降级到 good 兜底成功
    for i in range(3):
        res = traced("web.search", {"query": f"q{i}"})
        assert res.ok is True and res.engine_id == "good-k"
    store.finish(task_id, ok=True)

    # ResilienceBus 已为内部失败记账 → 坏引擎被熔断（链路被真正驱动）
    assert bad.calls == 3, "坏引擎每次都被尝试"
    assert hub._res_bus.should_skip("bad-k") is True, "连续失败必须触发熔断"

    # 熔断后再次路由：直接跳过坏引擎（calls 不再增长），trace 记的也是好引擎
    res = traced("web.search", {"query": "q-final"})
    assert res.ok and res.engine_id == "good-k"
    assert bad.calls == 3, "熔断后不应再打到坏引擎"
    # 任务层面始终成功（韧性闭环），但底层记账与熔断独立成立
    assert good.calls == 4

    # 即便任务成功，蒸馏器仍能从 trace 提炼「能力可靠性 = 100%（全靠 good-k 兜底）」
    distiller = MemoryDistiller(trace_dirs=[str(tmp_path)], interval_seconds=1)
    distiller.scan_once()
    items = _read_distilled(tmp_path)
    assert any(it["category"] == "capability_reliability" for it in items)


# ── 链路健壮性：崩溃引擎被隔离，trace 仍落盘、蒸馏不丢 ───────────────

def test_e2e_trace_chain_crash_isolated_still_traced(tmp_path):
    """芯粒崩溃不传染（理念：chiplet 故障隔离），且 trace 不丢、蒸馏照常。"""
    boom = _FakeAdapter("boom-k", ["web.search"], raises=True)
    good = _FakeAdapter("good-k2", ["web.search"], ok=True)
    hub = _make_hub({"web.search": [boom, good]})

    store = TaskTraceStore(traces_dir=str(tmp_path))
    task_id = "task-crash-1"
    store.begin(task_id, "崩溃引擎隔离验证")
    traced = TracedRoute(hub.route, store, task_id)

    # boom 抛异常被 route 捕获隔离，降级到 good 成功（调用方无感）
    res = traced("web.search", {"query": "x"})
    assert res.ok is True and res.engine_id == "good-k2"
    assert boom.calls == 1

    store.finish(task_id, ok=True)
    trace_path = os.path.join(str(tmp_path), f"trace_{task_id}.json")
    assert os.path.exists(trace_path), "崩溃隔离后 trace 仍须落盘"

    distiller = MemoryDistiller(trace_dirs=[str(tmp_path)], interval_seconds=1)
    rep = distiller.scan_once()
    assert rep.scanned_files >= 1
    # 全部成功 → 只产出 capability_reliability，不应有 failure_pattern
    items = _read_distilled(tmp_path)
    assert any(it["category"] == "capability_reliability" for it in items)
    assert not any(it["category"] == "failure_pattern" for it in items)
