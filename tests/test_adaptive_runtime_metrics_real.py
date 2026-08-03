"""内核自适应中枢「真实运行时体征」真跑测试（补缺口①）。

对齐（每条断言都能回溯到全局，不是零散补丁）：
- 白皮书 L2E 体感稳态系统：体征是**内在真实状态向量**，不能是同一个失败率的
  五种线性变形 —— 否则稳态其实只看得见一个数，「体感」是假的；
- 九大理念 8「白盒才可进化」：每个体征的来源必须可解释、可断言（vital_sources）；
- 九大理念 2.5「反思闭环」：稳态说的「降并发」必须真作用于真实并发旋钮，
  而不是错配到 evolution_interval（那是进化频率，压它反而把进化关掉了）。

诚实分级：②级（代码 + 单测实证，全部离线真跑，无 mock 体征、不连外网）。
不宣称③级（③需真 LLM + 主机环境）。
"""

import os

import pytest

from kernel.adaptive import AdaptiveCore


def _core(tmp_path, **kw) -> AdaptiveCore:
    return AdaptiveCore(memory_path=str(tmp_path / "failure_memory.json"), **kw)


# ── 1) 体征来源：真实运行时优先，而非成败折算 ────────────────────────────

def test_vitals_come_from_real_runtime_not_derived(tmp_path):
    core = _core(tmp_path)
    # 注入真实运行时指标（真实延迟 / 真实 token / 真实预算）
    for i in range(5):
        core.observe(
            success=True, task=f"t{i}", capability="chat",
            runtime_metrics={"latency_ms": 800.0 + i * 5,
                             "tokens": 300.0, "token_budget": 10000.0},
        )
    src = core.vital_sources()
    # 关键：五个体征各有独立真实来源，没有一个还在走 derived 折算
    assert src["error_rate"] == "runtime_window"
    assert src["latency_ms"] == "runtime"
    assert src["energy"] == "runtime_budget"      # 真实预算余量，不是 0.5-0.3*err
    assert src["focus"] == "runtime_jitter"       # 真实延迟抖动，不是 success?0.5:0.25
    assert src["mood"] == "runtime_window"
    assert src["debt"] == "runtime_memory"        # 真实未解决模式数，不是 failed*0.5
    # 真实指标原样留存可审计
    assert core.last_runtime_metrics()["tokens"] == 300.0


def test_energy_tracks_real_budget_burn_not_failure_rate(tmp_path):
    """全成功但预算烧光 → energy 必须跌破设定点并触发 rest_cycle。

    这正是旧版折算做不到的：旧版 energy = 0.5 - 0.3*err_rate，全成功时恒为 0.5，
    永远看不到「钱烧完了」。
    """
    core = _core(tmp_path)
    for i in range(8):
        core.observe(success=True, task=f"t{i}", capability="chat",
                     runtime_metrics={"latency_ms": 500.0, "tokens": 900.0,
                                      "token_budget": 5000.0})
    reading = core._readings[-1]
    assert reading["energy"] < 0.45, f"预算烧掉大半，energy 应真跌，实际 {reading['energy']}"
    assert core.tasks_failed == 0, "本用例零失败，energy 下跌只能来自真实预算消耗"
    actions = [getattr(c, "action", "") for c in core.corrections()]
    assert "rest_cycle" in actions, f"能量耗尽应触发休眠纠偏，实际 {actions}"


def test_focus_tracks_real_latency_jitter(tmp_path):
    """延迟剧烈抖动（同为成功）→ focus 真跌 → 触发 reset_focus。"""
    stable = _core(tmp_path / "a")
    jittery = _core(tmp_path / "b")
    os.makedirs(str(tmp_path / "a"), exist_ok=True)
    os.makedirs(str(tmp_path / "b"), exist_ok=True)

    for lat in (500.0, 505.0, 498.0, 502.0, 501.0):
        stable.observe(success=True, capability="chat",
                       runtime_metrics={"latency_ms": lat})
    for lat in (30.0, 2400.0, 60.0, 1900.0, 45.0):
        jittery.observe(success=True, capability="chat",
                        runtime_metrics={"latency_ms": lat})

    f_stable = stable._readings[-1]["focus"]
    f_jitter = jittery._readings[-1]["focus"]
    assert f_stable > 0.9, f"延迟平稳应高度专注，实际 {f_stable}"
    assert f_jitter < 0.5, f"延迟剧烈抖动应判涣散，实际 {f_jitter}"
    actions = [getattr(c, "action", "") for c in jittery.corrections()]
    assert "reset_focus" in actions, f"抖动应触发 reset_focus，实际 {actions}"


def test_latency_vital_is_registered_and_fires(tmp_path):
    """latency_ms 体征此前在 with_defaults() 里漏注册 → 真实延迟被稳态静默丢弃。

    现已在 AdaptiveCore 补注册，本用例守住这条真实断线不再复发。
    """
    core = _core(tmp_path)
    assert "latency_ms" in core.homeostasis._vitals, "latency_ms 体征必须被注册"
    for _ in range(4):
        core.observe(success=True, capability="chat",
                     runtime_metrics={"latency_ms": 1900.0})  # 逼近 2s 上界
    actions = [getattr(c, "action", "") for c in core.corrections()]
    assert "switch_engine_tier:light" in actions, \
        f"真实高延迟应触发切轻量档，实际 {actions}"


def test_debt_equals_real_unresolved_failure_patterns(tmp_path):
    """debt 体征 = 记忆库真实未解决模式数（真技术债），不是「失败次数×0.5」。"""
    core = _core(tmp_path)
    core.observe(success=False, task="装 ffmpeg", error="command not found: ffmpeg",
                 capability="action.code_exec")
    core.observe(success=False, task="拉取网页", error="ConnectionError: timeout",
                 capability="web.search")
    unresolved = core.memory_stats["unresolved"]
    assert unresolved >= 2
    assert core._readings[-1]["debt"] == float(min(5.0, unresolved)), \
        "debt 必须直接等于真实未解决模式存量"


def test_failure_enters_its_own_reading_no_off_by_one(tmp_path):
    """首次失败必须立刻反映进本次体征（旧版先算体征后记账，慢一拍）。"""
    core = _core(tmp_path)
    core.observe(success=False, task="x", error="boom", capability="action.code_exec")
    assert core._readings[-1]["error_rate"] == 1.0, \
        f"第一次就失败，本次 error_rate 应为 1.0，实际 {core._readings[-1]['error_rate']}"
    assert core._readings[-1]["debt"] >= 1.0, "本次失败应已计入债务"


# ── 2) 真实并发旋钮：降得下去，也回得来 ─────────────────────────────────

def test_reduce_concurrency_hits_real_dial_and_recovers(tmp_path):
    core = _core(tmp_path, concurrency_base=4, concurrency_floor=1)
    assert core.concurrency_limit() is None, "未干预时不应占用调用方默认值"
    assert core.effective_concurrency(4) == 4

    core.reduce_concurrency(effort=1.0)
    assert core.concurrency_limit() == 2, "力度 1.0 应砍半"
    assert core.effective_concurrency(4) == 2, "调用方默认与自适应上限取小"

    core.reduce_concurrency(effort=1.0)
    assert core.concurrency_limit() == 1
    core.reduce_concurrency(effort=1.0)
    assert core.concurrency_limit() == 1, "不得低于 concurrency_floor"

    core.restore_concurrency()
    assert core.concurrency_limit() == 2, "稳定后应逐步回升（动态，不是单向阀）"
    core.restore_concurrency(step=5)
    assert core.concurrency_limit() is None, "回到基线即撤销干预，还权调用方"


def test_apply_corrections_no_longer_mismaps_to_evolution_interval(tmp_path):
    """reduce_concurrency 只动并发；rest_cycle 才动 evolution_interval。"""
    class _FakeEngine:
        _evolution_interval = 5
        _max_concurrency = 4
        _max_population = 10
        _min_population = 2

    core = _core(tmp_path, concurrency_base=4)
    eng = _FakeEngine()

    class _C:
        def __init__(self, action, effort=1.0):
            self.action = action
            self.effort = effort

    applied = core.apply_corrections(eng, [_C("reduce_concurrency")])
    assert eng._evolution_interval == 5, "降并发绝不能顺手把进化频率也改了"
    assert eng._max_concurrency == 2, f"引擎并发应真降，实际 {eng._max_concurrency}"
    assert any("concurrency->" in a for a in applied)

    core.apply_corrections(eng, [_C("rest_cycle", 1.0)])
    assert eng._evolution_interval == 10, "休眠才拉长进化间隔（语义正确）"


def test_apply_corrections_works_without_engine(tmp_path):
    """autopilot 侧没有 live 引擎，也必须能真降自身并发旋钮。"""
    core = _core(tmp_path, concurrency_base=3)

    class _C:
        action = "reduce_concurrency"
        effort = 1.0

    applied = core.apply_corrections(None, [_C()])
    assert core.concurrency_limit() == 1, "base=3 全力砍半 → 1"
    assert any("concurrency->1" in a for a in applied)


def test_autopilot_max_parallel_respects_adaptive_dial(tmp_path, monkeypatch):
    """稳态压低并发后，autopilot 规划的并行宽度真的跟着变窄（不是记日志）。"""
    import kernel.autopilot as ap
    from kernel.adaptive import set_adaptive_core

    monkeypatch.setenv("AOS_MAX_PARALLEL", "4")
    core = _core(tmp_path, concurrency_base=4)
    set_adaptive_core(core)
    try:
        assert ap._max_parallel() == 4, "未失稳时按 env 基线"
        core.reduce_concurrency(effort=1.0)      # → 2
        assert ap._max_parallel() == 2, "稳态压低后并行宽度必须真变窄"
        groups = ap._cap_parallel_groups([[0, 1, 2, 3]], ap._max_parallel())
        assert all(len(g) <= 2 for g in groups), f"并行组应被真实切窄，实际 {groups}"
    finally:
        set_adaptive_core(None)


# ── 3) 快照可观测：真实指标进得了运维面 ──────────────────────────────────

def test_snapshot_exposes_real_runtime_surface(tmp_path):
    core = _core(tmp_path)
    core.observe(success=True, capability="chat",
                 runtime_metrics={"latency_ms": 700.0, "tokens": 120.0})
    snap = core.snapshot()
    for key in ("vital_sources", "last_runtime_metrics", "last_readings",
                "concurrency_limit", "concurrency_base", "tokens_total",
                "stage_ticks", "stage_health"):
        assert key in snap, f"运维快照缺少 {key}"
    assert snap["tokens_total"] == 120.0
    assert snap["vital_sources"]["latency_ms"] == "runtime"
