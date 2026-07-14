"""mem0 双域记忆测试：默认关、隔离不崩、本地 JSON 铁底、子进程隔离机制。

诚实边界：mem0 在本沙箱真执行会硬崩子进程（ollama 抽取段错），因此双域记忆
的铁底是本地 JSON，mem0 是可选语义增强层（AOS_MEM0_BRIDGE=1 才启用，且跑在
隔离子进程里）。本测试验证：默认安全、不崩、本地双域永远可用。
"""
import os

import pytest

import core.fabric.companion as C


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("AOS_COMPANION_DIR", str(tmp_path))
    monkeypatch.delenv("AOS_MEM0_BRIDGE", raising=False)
    C._Mem0Bridge._DISABLED = False
    C._Mem0Bridge._CONSEC_FAIL = 0
    yield tmp_path


def test_bridge_disabled_by_default(iso):
    assert C._Mem0Bridge.enabled() is False


def test_store_recall_safe_when_disabled(iso):
    # 未启用：store 返回 False，recall 返回 None —— 不崩、不联网
    assert C._Mem0Bridge.store("user", "facts", "u") is False
    assert C._Mem0Bridge.recall("user", "u") is None


def test_local_json_dual_domain_always_works(iso):
    comp = C.Companion.load("u")
    comp.remember_user("用户喜欢蓝色")
    comp.note_experience("3d", "做了星河")
    # user 域
    assert "用户喜欢蓝色" in comp.user_domain["facts"]
    # agent 域
    assert comp.agent_domain["experiences"][-1]["detail"] == "做了星河"
    # 召回（bridge 关 → 退回本地 JSON 扫描）
    rec = comp.recall_user_memories("颜色")
    assert any("蓝色" in r for r in rec)
    ag = comp.recall_agent_memories("做过什么")
    assert any("星河" in r for r in ag)


def test_subprocess_isolation_mechanism(iso):
    # 直接验证 _run 的子进程隔离：返回 dict 或 None（绝不抛、绝不带崩主进程）
    out = C._Mem0Bridge._run({"action": "health"})
    assert out is None or isinstance(out, dict)


def test_companion_view_mem0_status(iso):
    view = C.get_companion_view("u")
    assert "mem0_bridge" in view["memory"]
    assert view["memory"]["mem0_bridge"] is False  # 默认关
