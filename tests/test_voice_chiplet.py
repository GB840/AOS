"""VoicePipeline 单例化回归：验证 _get_hub 走 get_fabric_hub() 单例，而非裸 FabricHub()。

直接针对「单基座」第一性原则破口（voice_chiplet.py:252 曾裸造 FabricHub()）。
纯 monkeypatch，无重型 import、无真实网络。
"""
import pytest

from core.fabric.voice_chiplet import VoicePipeline


@pytest.fixture(autouse=True)
def _reset_hub_cache():
    VoicePipeline._HUB = None
    yield
    VoicePipeline._HUB = None


def test_get_hub_uses_singleton_getter(monkeypatch):
    """_get_hub 必须返回 get_fabric_hub() 的单例，不得再裸造 FabricHub()。"""
    fake_hub = object()
    called = {}

    def _fake_get():
        called["n"] = called.get("n", 0) + 1
        return fake_hub

    monkeypatch.setattr("kernel.plugins.fabric_hub.get_fabric_hub", _fake_get)
    # 确保不会回退到裸 FabricHub()：把源模块 FabricHub 换成会爆炸的桩
    monkeypatch.setattr(
        "kernel.plugins.fabric_hub.FabricHub",
        lambda: next(_ for _ in ()),  # 迭代空生成器 -> StopIteration(即不应被调用)
    )

    result = VoicePipeline._get_hub()
    assert result is fake_hub, "应返回单例 getter 的产物"
    assert called.get("n") == 1, "应恰好调用一次 get_fabric_hub"


def test_get_hub_graceful_when_singleton_unavailable(monkeypatch):
    """单例 getter 抛异常时，应优雅降级为 None（不崩溃、不裸造）。"""
    def _boom():
        raise RuntimeError("装配失败")

    monkeypatch.setattr("kernel.plugins.fabric_hub.get_fabric_hub", _boom)
    monkeypatch.setattr(
        "kernel.plugins.fabric_hub.FabricHub",
        lambda: next(_ for _ in ()),
    )

    assert VoicePipeline._get_hub() is None
