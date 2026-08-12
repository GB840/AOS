"""深度诚实测试：用【生产单例 + 真实磁盘】验证生命体真驱动闭环。

与 test_lifeform_drives_runtime.py 的区别（补此前 mock 自欺缺口）：
  - 不 monkeypatch 替换 get_lifeform_runtime，直接拿 main.py 挂载的那个单例；
  - 不手动 new 实例替换 life_state，用生产默认存储目录真实落盘；
  - 验证「清掉单例缓存后重读磁盘」仍是衰减后的值 → 证明闭环是真持久化，
    不是内存里的假象。

诚实分级：② 级（代码 + 真实磁盘实证），不含真 LLM 端到端。
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

UID = "__prod_probe__"  # 专用探针 uid，不污染 default 用户体征


@pytest.fixture(scope="module", autouse=True)
def _reset_singleton():
    """测试前后清掉单例缓存，确保拿到的是真实装配的单例。"""
    import kernel.lifeform_runtime as lr
    if hasattr(lr.get_lifeform_runtime, "_inst"):
        delattr(lr.get_lifeform_runtime, "_inst")
    yield
    if hasattr(lr.get_lifeform_runtime, "_inst"):
        delattr(lr.get_lifeform_runtime, "_inst")


def test_production_singleton_assembled_for_real():
    """生产单例（非 fixture new）真装配了 31 组件且零失败。"""
    ap = importlib.import_module("kernel.autopilot")  # 触发模块级 import 不破坏单例
    rt = importlib.import_module("kernel.lifeform_runtime").get_lifeform_runtime()
    assert rt.errors == {}, f"生产装配有失败: {rt.errors}"
    assert rt.status()["components_loaded"] >= 31
    assert "life_state" in rt.components and "homeostasis" in rt.components


def test_production_loop_downgrades_and_persists():
    """生产单例 + 真实磁盘闭环：跑得多→energy 降→真降档→清缓存重读仍降档。"""
    lr = importlib.import_module("kernel.lifeform_runtime")
    rt = lr.get_lifeform_runtime()
    heavy, light = "qwen3:8b", "qwen2.5:3b"

    # 重置探针 uid 为初始满能量，避免上轮落盘的残留污染（真实磁盘隔离）。
    # 这本身也在测「save 真写盘」——后续清缓存重读应能感知这次写入。
    from kernel.life_state import LifeState
    rt.components["life_state"].save(UID, LifeState())

    assert rt.pick_model(heavy, light, user_id=UID) == heavy  # 满能量用重模型

    for _ in range(25):
        rt.on_run_finished(cost=0.05, failed=False, user_id=UID)

    # 闭环真生效：能量耗尽后自动切轻模型
    assert rt.pick_model(heavy, light, user_id=UID) == light

    # 真落盘：清掉单例缓存，重新取单例并从磁盘读，仍应为低能量 + 降档
    delattr(lr.get_lifeform_runtime, "_inst")
    rt2 = lr.get_lifeform_runtime()
    st = rt2.components["life_state"].load(UID)
    assert st.energy < 0.3, f"体征未真实持久化到磁盘: energy={st.energy}"
    assert rt2.pick_model(heavy, light, user_id=UID) == light
