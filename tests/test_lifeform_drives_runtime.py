"""乙线实证：生命体层「真驱动」运行时决策，而非仅被挂载。

诚实分级：本文件是 ② 级（代码 + 单测实证），不含真 LLM 端到端。
证明目标：
  1. 31 个原孤儿模块在运行时真被实例化（一套系统，非一堆零件）；
  2. life_state.energy 会真实改变 autopilot 的模型选择（决策锚定落地）；
  3. 跑得多 → energy 衰减 → 自动降档，形成闭环（不是静态开关）；
  4. homeostasis 真输出纠偏动作（修复此前裸构造导致 tick() 恒空的缺陷）。
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture()
def rt(tmp_path, monkeypatch):
    """隔离实例：life_state 落到 tmp_path，绝不污染真实体征文件。"""
    from kernel.life_state import LifeStateStore
    from kernel.lifeform_runtime import LifeformRuntime

    r = LifeformRuntime()
    r.components["life_state"] = LifeStateStore(base_dir=tmp_path)
    return r


def test_all_lifeform_modules_assembled(rt):
    """甲线实证：生命体层模块被真实例化，且零构造失败。"""
    assert rt.errors == {}, f"有模块构造失败: {rt.errors}"
    assert len(rt.components) >= 31, f"仅装载 {len(rt.components)} 个"
    # 抽查跨域覆盖：状态/灵魂/精神/分形/肉体/安全闸门 都在
    for key in ("life_state", "homeostasis", "tree_ring", "datong",
                "fractal_spawner", "hal", "action_arbiter", "emergency_brake",
                "memory_ladder", "mirror_lab", "perception_gateway"):
        assert key in rt.components, f"缺组件: {key}"


def test_homeostasis_has_registered_vitals(rt):
    """修复实证：homeostasis 必须带默认体征，否则 tick() 恒空 = 白挂。"""
    homeo = rt.components["homeostasis"]
    corrections = homeo.tick({"energy": 0.01, "focus": 0.01,
                              "mood": 0.0, "debt": 4.9, "error_rate": 1.0})
    assert corrections, "tick() 返回空 —— 体征未注册（白挂）"
    assert any(c.vital == "energy" for c in corrections)


def test_high_energy_keeps_heavy_model(rt):
    """满能量 → 用重模型。"""
    st = rt.components["life_state"].load("u1")
    assert st.energy >= 0.9
    assert rt.pick_model("qwen3:8b", "qwen2.5:3b", user_id="u1") == "qwen3:8b"


def test_low_energy_downgrades_model(rt):
    """低能量 → 真的换成轻模型（决策被体征改变）。"""
    store = rt.components["life_state"]
    st = store.load("u2")
    st.energy = 0.1
    store.save("u2", st)
    assert rt.pick_model("qwen3:8b", "qwen2.5:3b", user_id="u2") == "qwen2.5:3b"


def test_repeated_runs_close_the_loop(rt):
    """闭环实证：连续跑 → energy 衰减 → 自动从重模型切到轻模型。"""
    uid = "loop"
    heavy, light = "qwen3:8b", "qwen2.5:3b"
    assert rt.pick_model(heavy, light, user_id=uid) == heavy

    switched_at = None
    for i in range(1, 40):
        rt.on_run_finished(cost=0.05, failed=False, user_id=uid)
        if rt.pick_model(heavy, light, user_id=uid) == light:
            switched_at = i
            break
    assert switched_at is not None, "跑到能量耗尽也没降档 —— 闭环没接上"
    # 1.0 起步、每次 -0.05、阈值 0.3 → 约第 15 次附近切换
    assert 10 <= switched_at <= 20, f"降档时机异常: 第 {switched_at} 次"


def test_failure_raises_debt(rt):
    """失败会真抬高 debt（体征记账，不是空跑）。"""
    uid = "dbt"
    before = rt.components["life_state"].load(uid).debt
    out = rt.on_run_finished(failed=True, user_id=uid)
    after = rt.components["life_state"].load(uid).debt
    assert out["applied"] is True
    assert after > before


def test_autopilot_uses_lifeform_picker(monkeypatch):
    """接线实证：autopilot 的模型选择确实走生命体层，而不是只读 env。"""
    ap = importlib.import_module("kernel.autopilot")
    assert hasattr(ap, "_lifeform_pick_model")
    seen = {}

    class _FakeRT:
        def pick_model(self, heavy, light=None, user_id="default"):
            seen["heavy"] = heavy
            return "LIGHT-PICKED"

    import kernel.lifeform_runtime as lr
    monkeypatch.setattr(lr, "get_lifeform_runtime", lambda: _FakeRT())
    assert ap._lifeform_pick_model("qwen3:8b") == "LIGHT-PICKED"
    assert seen["heavy"] == "qwen3:8b"


def test_picker_never_blocks_on_error(monkeypatch):
    """best-effort 铁律：生命体层炸了也必须退回默认模型，不能阻断主链路。"""
    ap = importlib.import_module("kernel.autopilot")
    import kernel.lifeform_runtime as lr

    def _boom():
        raise RuntimeError("lifeform down")

    monkeypatch.setattr(lr, "get_lifeform_runtime", _boom)
    assert ap._lifeform_pick_model("qwen3:8b") == "qwen3:8b"
