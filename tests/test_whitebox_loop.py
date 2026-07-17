"""白盒进化闭环·回读验证（理念8「白盒才可进化」的端到端闭环测试）。

覆盖 P0 任务的四个验收点：
  ① 编排器 / 内容导演真实产出 trace_<id>.json，且 schema 严格对齐
     MemoryDistiller._distill_trace_file 的期望（蒸馏器可真吃、不乱填）。
  ② 蒸馏循环能把 trace_*.json / route_outcomes.jsonl 提炼成
     distilled_memory.jsonl（含 capability_reliability / failure_pattern /
     latency_fact，带量化置信）。
  ③ 路由回读真实生效：失败率超阈值的 (能力,引擎) 被沉底（软偏好，不硬阻断），
     置信不足（样本 < min_samples）不误杀——诚实门控。
  ④ 蒸馏记忆文件缺失 / 为空 / 含损坏行时零影响、不抛、绝不编造。

所有外部依赖均用 fake（route_fn / 合成 trace 文件），但业务逻辑全真：
trace → distill → registry 回读 三段都是真实代码路径，不是 mock。
"""
import enum
import json
from pathlib import Path

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import TIER_HIGH, TIER_MEDIUM
from core.fabric.registry import FabricRegistry
from core.fabric.trace_store import TaskTraceStore, TracedRoute, _traces_dir


# ── 测试用最小能力枚举（仅 .value 参与匹配，避免引入重型依赖）──
class _Cap(str, enum.Enum):
    DEMO = "demo.cap"
    DEMO_BAD = "demo.bad"


# ── 最小 fake 适配器（实现 BaseAgentAdapter 契约即可）──
class FakeAdapter(BaseAgentAdapter):
    def __init__(self, eid, caps, tier=TIER_HIGH):
        self._eid = eid
        self._caps = caps
        self._tier = tier

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return self._caps

    def health(self):
        return True

    def invoke(self, req):
        return InvokeResult(ok=True, engine_id=self._eid)

    def tier(self):
        return self._tier


# ══════════════════════════════════════════════════════════════
# ① 生产者：TaskTraceStore 直接产出正确 schema
# ══════════════════════════════════════════════════════════════
def test_task_trace_store_schema(tmp_path):
    store = TaskTraceStore(traces_dir=str(tmp_path))
    store.begin("t1", "demo task")
    store.add_step("t1", "demo.cap", "good", True, None, 12.5)
    store.add_step("t1", "demo.bad", "bad", False, "boom", 30.0)
    path = store.finish("t1", ok=False)
    assert path and Path(path).exists()

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["task_id"] == "t1"
    assert data["input"]["task"] == "demo task"
    assert len(data["steps"]) == 2
    # 步骤 schema 严格对齐蒸馏器期望
    s0 = data["steps"][0]
    assert s0["capability"] == "demo.cap" and s0["engine"] == "good" and s0["ok"] is True
    s1 = data["steps"][1]
    assert s1["capability"] == "demo.bad" and s1["ok"] is False and s1["error"] == "boom"
    # 延迟事实聚合
    assert data["metrics"]["latency_ms"] == 42.5
    assert data["ok"] is False
    assert "ts" in data


def test_traced_route_records_success_and_propagates_exception():
    store = TaskTraceStore(traces_dir=str(Path("/tmp").joinpath("aos_wb_none")))
    calls = []

    def ok_fn(cap, payload):
        calls.append((cap, payload))
        return InvokeResult(ok=True, data={"x": 1}, engine_id="good")

    # TracedRoute 需先 begin（真实用法里 content_director/orchestration 都先 begin）
    store.begin("rt1", "goal")
    traced = TracedRoute(ok_fn, store, "rt1")
    res = traced("demo.cap", {"k": "v"})
    assert res.ok is True
    # 成功步被埋点
    rec = store._buf["rt1"]["steps"][0]
    assert rec["capability"] == "demo.cap" and rec["engine"] == "good" and rec["ok"] is True

    def boom_fn(cap, payload):
        raise RuntimeError("kaboom")

    store.begin("rt2", "goal")
    traced2 = TracedRoute(boom_fn, store, "rt2")
    try:
        traced2("demo.bad", {})
    except RuntimeError:
        pass
    else:
        raise AssertionError("异常未被透传")
    # 异常步也埋点（失败不丢），并带 engine=None
    rec2 = store._buf["rt2"]["steps"][0]
    assert rec2["capability"] == "demo.bad" and rec2["ok"] is False and rec2["engine"] is None


# ══════════════════════════════════════════════════════════════
# ① 生产者：OrchestrationChiplet 真实跑出 trace_<id>.json
# ══════════════════════════════════════════════════════════════
def test_orchestration_chiplet_produces_trace():
    from core.fabric.capability import Capability
    from kernel.plugins.orchestration_chiplet import OrchestrationChiplet

    def fake_route(cap, payload):
        if cap == "demo.cap":
            return InvokeResult(ok=True, data={"x": 1}, engine_id="good")
        if cap == "demo.bad":
            return InvokeResult(ok=False, error="step failed", engine_id="bad")
        return InvokeResult(ok=False, error="unknown", engine_id="?")

    chip = OrchestrationChiplet(route_fn=fake_route)
    req = InvokeRequest(
        capability=Capability.WORKFLOW_EXECUTE,
        payload={
            "task_id": "wb_orch_01",
            "initial": {"task": "编排白盒测试"},
            "steps": [
                {"capability": "demo.cap", "in": {}},
                {"capability": "demo.bad", "in": {}},
            ],
        },
    )
    res = chip.invoke(req)
    # 一步成功一步失败 → 编排本身完成（ok=True），失败步在 data.trace 体现
    assert res.ok is True
    assert res.data["ok_steps"] == 1 and res.data["failed_steps"] == 1

    trace_path = _traces_dir() / "trace_wb_orch_01.json"
    assert trace_path.exists(), "编排芯粒未落盘 trace_<id>.json"
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    assert data["input"]["task"] == "编排白盒测试"
    assert len(data["steps"]) == 2
    ok_step = next(s for s in data["steps"] if s["capability"] == "demo.cap")
    bad_step = next(s for s in data["steps"] if s["capability"] == "demo.bad")
    assert ok_step["ok"] is True and ok_step["engine"] == "good"
    assert bad_step["ok"] is False and bad_step["error"] == "step failed"


# ══════════════════════════════════════════════════════════════
# ① 生产者：ContentDirector.produce 真实埋点出 trace_<id>.json
# ══════════════════════════════════════════════════════════════
def test_content_director_produces_trace(tmp_path):
    from kernel.plugins.content_director import ContentDirector

    def fake_route(cap, payload):
        if cap == "web.search":
            return {"ok": True, "data": {"results": [{"title": "A", "url": "http://a"}]}}
        if cap in ("media.image", "media.video"):
            return {"ok": True, "data": {"output_path": f"/fake/{cap}.png"}}
        # 知识库/视觉/LLM 不可达 → 诚实降级（不影响 trace 埋点）
        return {"ok": False, "data": {}}

    d = ContentDirector(route_fn=fake_route, work_root=str(tmp_path))
    res = d.produce("白盒进化测试短片")
    assert res.task_id

    trace_path = _traces_dir() / f"trace_{res.task_id}.json"
    assert trace_path.exists(), "内容导演未落盘 trace_<id>.json"
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    assert data["input"]["task"] == "白盒进化测试短片"
    assert len(data["steps"]) >= 1
    # 每步都带 capability（蒸馏器聚合键）
    assert all("capability" in s for s in data["steps"])


# ══════════════════════════════════════════════════════════════
# ② 蒸馏循环：把 trace_*.json 提炼成 distilled_memory.jsonl
# ══════════════════════════════════════════════════════════════
def test_distiller_turn_trace_file_into_distilled_memory(tmp_path):
    from kernel.memory_distiller import MemoryDistiller

    # 合成一个符合 trace_store schema 的任务 trace（含一步失败 + 延迟）
    trace = {
        "task_id": "t1",
        "input": {"task": "demo task"},
        "steps": [
            {"capability": "demo.cap", "engine": "good", "ok": True, "latency_ms": 10.0},
            {"capability": "demo.bad", "engine": "bad", "ok": False, "error": "boom"},
        ],
        "metrics": {"latency_ms": 10.0},
        "ts": "2026-07-17T00:00:00",
        "ok": False,
    }
    (tmp_path / "trace_t1.json").write_text(
        json.dumps(trace, ensure_ascii=False), encoding="utf-8")

    out = tmp_path / "distilled_memory.jsonl"
    dist = MemoryDistiller(
        trace_dirs=[str(tmp_path)],
        out_path=str(out),
        state_path=str(tmp_path / ".distill_state.json"),
    )
    rep = dist.scan_once()
    assert rep.scanned_files == 1
    assert rep.new_items >= 3   # 失败模式 + 能力可靠性 + 延迟事实

    records = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    cats = {r["category"] for r in records}
    assert "failure_pattern" in cats
    assert "capability_reliability" in cats
    assert "latency_fact" in cats
    # 失败模式来源正确
    fp = next(r for r in records if r["category"] == "failure_pattern")
    assert "demo.bad" in fp["text"] and "boom" in fp["text"]
    # 量化置信（样本1 → 低 0.3）
    assert fp["confidence"] == 0.3


# ══════════════════════════════════════════════════════════════
# ② 蒸馏循环：把 route_outcomes.jsonl 提炼成 distilled_memory.jsonl
# ══════════════════════════════════════════════════════════════
def test_distiller_turn_route_outcomes_into_distilled_memory(tmp_path):
    from kernel.memory_distiller import MemoryDistiller

    # 10 次路由：demo.cap 经 bad 引擎全失败 → 提炼出「不可靠」可靠性记录
    rows = [
        {"capability": "demo.cap", "engine": "bad", "ok": False,
         "tier": "high", "latency_ms": 5.0, "error": "x"}
        for _ in range(10)
    ]
    (tmp_path / "route_outcomes.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")

    out = tmp_path / "distilled_memory.jsonl"
    dist = MemoryDistiller(
        trace_dirs=[str(tmp_path)],
        out_path=str(out),
        state_path=str(tmp_path / ".distill_state.json"),
    )
    dist.scan_once()

    records = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    rel = [r for r in records if r["category"] == "capability_reliability"]
    assert rel, "未提炼出能力可靠性记录"
    rec = rel[0]
    # route 源 metadata 带 key=能力/引擎，且样本 10 达高置信
    assert rec["metadata"]["key"] == "demo.cap/bad"
    assert rec["metadata"]["ok"] == 0 and rec["metadata"]["total"] == 10
    assert rec["confidence"] == 0.9   # 样本 >=5 → 高


# ══════════════════════════════════════════════════════════════
# ③ 路由回读真实生效：失败引擎被沉底（软偏好，仍作兜底）
# ══════════════════════════════════════════════════════════════
def _write_distilled(path: Path, cap: str, engine: str, ok: int, total: int):
    """写一条 route 源的能力可靠性记录（key=能力/引擎）。"""
    rec = {
        "category": "capability_reliability",
        "text": f"路由可靠性：{cap}/{engine} 成功率 {ok}/{total}",
        "source": "route_outcomes.jsonl",
        "confidence": 0.9 if total >= 5 else 0.3,
        "metadata": {"key": f"{cap}/{engine}", "ok": ok, "total": total},
    }
    path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")


def test_registry_penalizes_unreliable_engine_and_orders_down():
    distilled = Path("/tmp/aos_wb_distilled_pen.json")
    _write_distilled(distilled, "demo.cap", "bad", ok=0, total=10)  # 成功率 0 < 0.5

    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert reg.distilled_diagnostics()["penalty_count"] == 1
    assert "demo.cap|bad" in reg._distilled_penalties

    # 注册顺序：bad 在前，good 在后；无惩罚时稳定排序保持 [bad, good]
    reg.register(FakeAdapter("bad", [_Cap.DEMO]))
    reg.register(FakeAdapter("good", [_Cap.DEMO]))
    order = [a.engine_id for a in reg.providers_for(_Cap.DEMO)]
    # 惩罚把 bad 沉底 → [good, bad]，且 bad 仍在列表（软偏好，不硬阻断）
    assert order == ["good", "bad"], f"惩罚未生效：{order}"
    assert "bad" in order


def test_registry_insufficient_samples_no_mis_kill():
    """置信门控：样本 < min_samples 不施加惩罚（不误杀可用引擎）。"""
    distilled = Path("/tmp/aos_wb_distilled_insuff.json")
    _write_distilled(distilled, "demo.cap", "bad", ok=0, total=3)  # 3 < 5

    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert reg.distilled_diagnostics()["penalty_count"] == 0, "样本不足却施加了惩罚"

    reg.register(FakeAdapter("bad", [_Cap.DEMO]))
    reg.register(FakeAdapter("good", [_Cap.DEMO]))
    order = [a.engine_id for a in reg.providers_for(_Cap.DEMO)]
    # 无惩罚 → 稳定排序保持注册顺序 [bad, good]（bad 未被误杀沉底）
    assert order == ["bad", "good"], f"样本不足却沉底了 bad：{order}"


def test_registry_reliable_engine_not_penalized():
    """成功率高（>= 阈值）的引擎不惩罚，哪怕样本充足。"""
    distilled = Path("/tmp/aos_wb_distilled_reliable.json")
    _write_distilled(distilled, "demo.cap", "bad", ok=9, total=10)  # 90% > 50%

    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert reg.distilled_diagnostics()["penalty_count"] == 0
    reg.register(FakeAdapter("bad", [_Cap.DEMO]))
    reg.register(FakeAdapter("good", [_Cap.DEMO]))
    order = [a.engine_id for a in reg.providers_for(_Cap.DEMO)]
    assert order == ["bad", "good"]


def test_registry_incremental_reload_on_mtime_change():
    """蒸馏器常驻持续写，路由软偏好应按文件 mtime 增量重加载，闭环活起来。"""
    distilled = Path("/tmp/aos_wb_distilled_reload.json")
    _write_distilled(distilled, "demo.cap", "bad", ok=0, total=10)
    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert "demo.cap|bad" in reg._distilled_penalties

    # 蒸馏器追加一条新不可靠记录（demo.cap/bad2 全失败）
    with distilled.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "category": "capability_reliability",
            "text": "x",
            "source": "r",
            "confidence": 0.9,
            "metadata": {"key": "demo.cap/bad2", "ok": 0, "total": 10},
        }, ensure_ascii=False) + "\n")
    # 强制 mtime 前进，确保 _maybe_reload_distilled 判定变更
    import os
    st = os.stat(distilled)
    os.utime(distilled, (st.st_atime, st.st_mtime + 1.0))

    reg._maybe_reload_distilled()
    assert "demo.cap|bad2" in reg._distilled_penalties, "mtime 变更后未增量重加载"
    assert reg.distilled_diagnostics()["penalty_count"] == 2


# ══════════════════════════════════════════════════════════════
# ④ 文件缺失 / 为空 / 损坏行：零影响、不抛、不编造
# ══════════════════════════════════════════════════════════════
def test_registry_distilled_missing_file_zero_impact():
    reg = FabricRegistry(
        distilled_memory_path="/tmp/aos_wb_distilled_does_not_exist.json",
        distilled_min_samples=5)
    diag = reg.distilled_diagnostics()
    assert diag["enabled"] is True
    assert diag["loaded"] is False
    assert diag["penalty_count"] == 0
    # 路由照常工作，不抛
    reg.register(FakeAdapter("bad", [_Cap.DEMO]))
    reg.register(FakeAdapter("good", [_Cap.DEMO]))
    assert [a.engine_id for a in reg.providers_for(_Cap.DEMO)] == ["bad", "good"]


def test_registry_distilled_empty_file_zero_impact():
    distilled = Path("/tmp/aos_wb_distilled_empty.json")
    distilled.write_text("", encoding="utf-8")
    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert reg.distilled_diagnostics()["penalty_count"] == 0
    # 无惩罚、不抛，正常返回已注册适配器（稳定排序保持注册顺序）
    reg.register(FakeAdapter("bad", [_Cap.DEMO]))
    reg.register(FakeAdapter("good", [_Cap.DEMO]))
    assert [a.engine_id for a in reg.providers_for(_Cap.DEMO)] == ["bad", "good"]


def test_registry_distilled_malformed_lines_ignored():
    """损坏行被跳过，合法行仍解析，不抛。"""
    distilled = Path("/tmp/aos_wb_distilled_malformed.json")
    distilled.write_text(
        "{这不是合法json\n"                              # 损坏行
        + json.dumps({                                   # 合法不可靠记录
            "category": "capability_reliability",
            "text": "x", "source": "r", "confidence": 0.9,
            "metadata": {"key": "demo.cap/bad", "ok": 0, "total": 10},
        }, ensure_ascii=False) + "\n",
        encoding="utf-8")
    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert "demo.cap|bad" in reg._distilled_penalties, "合法行未被解析"


# ══════════════════════════════════════════════════════════════
# 集成：distill → registry 回读 端到端闭环
# ══════════════════════════════════════════════════════════════
def test_end_to_end_distill_then_registry_readback(tmp_path):
    from kernel.memory_distiller import MemoryDistiller

    # 1) 合成 route_outcomes：demo.cap 经 bad 全失败（10 次）
    rows = [{"capability": "demo.cap", "engine": "bad", "ok": False,
             "tier": "high", "latency_ms": 5.0, "error": "x"} for _ in range(10)]
    (tmp_path / "route_outcomes.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    # 2) 蒸馏器提炼 → distilled_memory.jsonl
    distilled = tmp_path / "distilled_memory.jsonl"
    dist = MemoryDistiller(
        trace_dirs=[str(tmp_path)], out_path=str(distilled),
        state_path=str(tmp_path / ".distill_state.json"))
    dist.scan_once()
    assert distilled.exists()

    # 3) 注册表回读 → bad 引擎被沉底
    reg = FabricRegistry(distilled_memory_path=str(distilled), distilled_min_samples=5)
    assert "demo.cap|bad" in reg._distilled_penalties
    reg.register(FakeAdapter("bad", [_Cap.DEMO]))
    reg.register(FakeAdapter("good", [_Cap.DEMO]))
    order = [a.engine_id for a in reg.providers_for(_Cap.DEMO)]
    assert order == ["good", "bad"], f"端到端闭环未生效：{order}"
