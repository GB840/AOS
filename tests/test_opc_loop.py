"""OPC 商业飞轮常驻环原型测试（mock 模式，无真实 LLM，快速全绿）。

覆盖：阶段按序执行 / 副作用确认门控 / 回流教训写入+注入 / 阶段注册表扩展 / 安全不变量。
"""

import pytest

from kernel.opc_loop import (
    OPCBusinessLoop, OPCLoopConfig, Stage, build_default_stages, register_stage,
)


class FakeExecutor:
    """记录调用，并可指定某阶段失败（模拟 autopilot.run 返回结构）。"""

    def __init__(self, fail_stage: str = None):
        self.calls = []           # (stage_id, task_text, cycle)
        self.fail_stage = fail_stage

    def __call__(self, stage, task_text, context):
        self.calls.append((stage.id, task_text, context["cycle"]))
        ok = stage.id != self.fail_stage
        return {
            "reflection": {"exhausted": not ok, "attempts": 1, "log": []},
            "ok": ok,
            "stage": stage.id,
        }


class FakeStore:
    """内存版 Meta-Trace，可模拟跨轮可见。"""

    def __init__(self):
        self.saved = []
        self.to_return = []

    def save(self, task, failed_cap, error, lesson):
        self.saved.append(
            {"task": task, "cap": failed_cap, "error": error, "lesson": lesson}
        )

    def load(self, task, limit=3):
        return self.to_return[:limit]


def test_stage_order_and_all_run():
    ex = FakeExecutor()
    cfg = OPCLoopConfig(business="自媒体一人公司", executor=ex, max_cycles=1)
    out = OPCBusinessLoop(cfg).run()
    ids = [c[0] for c in ex.calls]
    assert ids == ["analyze", "promote", "acquire", "deliver", "maintain"]


def test_side_effect_requires_confirm():
    ex = FakeExecutor()
    confirmed = []

    def confirm(stage, text):
        confirmed.append(stage.id)
        return stage.id != "acquire"  # 拒绝「获客」阶段

    cfg = OPCLoopConfig(
        business="X", executor=ex, confirm_fn=confirm, max_cycles=1
    )
    out = OPCBusinessLoop(cfg).run()

    # 获客被拒 → skipped
    acquire = [s for c in out["cycles_detail"] for s in c["stages"] if s["stage"] == "acquire"][0]
    assert acquire["skipped"] is True
    # 其余阶段仍执行
    assert ex.calls
    # 确认函数仅在副作用阶段被调用（acquire / deliver）
    assert set(confirmed) == {"acquire", "deliver"}


def test_reflection_saved_and_injected():
    ex = FakeExecutor(fail_stage="analyze")  # 首轮分析失败
    store = FakeStore()
    store.to_return = []  # 冷启动无教训

    OPCBusinessLoop(
        OPCLoopConfig(business="B", executor=ex, lesson_store=store, max_cycles=2)
    ).run()

    # 首轮分析失败 → 写入一条教训
    assert len(store.saved) >= 1
    saved = store.saved[0]
    assert saved["cap"] == "web.search"  # 分析阶段能力标签
    assert "历史教训" not in saved["lesson"]  # 教训本体不含注入标记

    # 模拟 Meta-Trace 跨轮可见：把存的教训设为可读
    store.to_return = store.saved

    ex2 = FakeExecutor()
    OPCBusinessLoop(
        OPCLoopConfig(business="B", executor=ex2, lesson_store=store, max_cycles=1)
    ).run()

    analyze_calls = [t for (sid, t, _c) in ex2.calls if sid == "analyze"]
    assert analyze_calls, "分析阶段应被执行"
    assert "历史教训" in analyze_calls[0]
    assert saved["lesson"] in analyze_calls[0]


def test_custom_stage_registry_extensible():
    register_stage(Stage(
        id="seo", name="SEO", capability="web.search",
        side_effect=False, parallel_safe=True, confirm=False,
        prompt="做SEO优化：{business}",
    ))
    ex = FakeExecutor()
    cfg = OPCLoopConfig(
        business="Y", executor=ex, enabled_stage_ids=["seo"], max_cycles=1
    )
    OPCBusinessLoop(cfg).run()
    assert [c[0] for c in ex.calls] == ["seo"]


def test_side_effect_stages_serial_and_confirmed_invariant():
    by_id = {s.id: s for s in build_default_stages()}
    # 副作用阶段：必须串行（parallel_safe=False）+ 确认（confirm=True）
    assert by_id["acquire"].side_effect is True
    assert by_id["acquire"].parallel_safe is False
    assert by_id["acquire"].confirm is True
    assert by_id["deliver"].side_effect is True
    assert by_id["deliver"].parallel_safe is False
    # 只读安全阶段：可并行 + 无需确认
    assert by_id["analyze"].side_effect is False
    assert by_id["analyze"].parallel_safe is True
    assert by_id["analyze"].confirm is False


def test_cycle_end_hook_fires():
    ex = FakeExecutor()
    fired = []
    cfg = OPCLoopConfig(
        business="Z", executor=ex, max_cycles=2,
        on_cycle_end=lambda detail, cycle: fired.append(cycle),
    )
    OPCBusinessLoop(cfg).run()
    assert fired == [0, 1]
