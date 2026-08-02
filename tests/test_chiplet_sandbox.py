"""chiplet_sandbox 原型单测（② 级：纯函数 + 状态序列化，无需 LLM/容器）。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.fabric.chiplet_sandbox import (  # noqa: E402
    ChipletSandbox,
    ChipletState,
    ChipletCrashed,
)


def _inc(state: ChipletState) -> ChipletState:
    state.data["acc"] = state.data.get("acc", 0) + 1
    return state


def test_snapshot_and_resume():
    sb = ChipletSandbox()
    st = ChipletState(chiplet_id="c1", step=2, data={"acc": 5})
    sid = sb.snapshot(st)
    restored = sb.resume(sid)
    assert restored.step == 2 and restored.data["acc"] == 5
    assert restored.snapshot_id == sid


def test_run_fresh_completes():
    sb = ChipletSandbox()
    st = sb.run(_inc, init=ChipletState(chiplet_id="c2", data={"max_steps": 3}), crash_at_step=None)
    assert st.step == 3
    assert st.data["acc"] == 3


def test_run_crash_then_resume():
    sb = ChipletSandbox()
    # 第一轮在 step=1 崩溃
    try:
        sb.run(_inc, init=ChipletState(chiplet_id="c3", data={"max_steps": 3}), crash_at_step=1)
        assert False, "应当抛出 ChipletCrashed"
    except ChipletCrashed as e:
        sid = e.snapshot_id
    # 从快照续跑，应完成剩余 step
    st = sb.run(_inc, snapshot_id=sid, crash_at_step=None)
    assert st.step == 3
    assert st.data["acc"] == 3
