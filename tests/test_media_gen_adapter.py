"""MediaGenAdapter 测试：能力注册、health 真实探测、缺 key 优雅降级、hub 路由。

照 test_crawl4ai_adapter.py 范式。缺 prompt / 无 key 的逻辑用 monkeypatch 隔离，
不依赖真实智谱 key；真机文生图/文生视频用 skipif 隔离
（依赖 ZHIPU_API_KEY + 联网 + 智谱额度），由 CI/本机在有 key 时真跑。
"""
from __future__ import annotations

import os

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters import media_gen_adapter as m


def _key_ok() -> bool:
    return bool(os.environ.get("ZHIPU_API_KEY") or os.environ.get("ZHIPUAI_API_KEY"))


KEY_OK = _key_ok()


def test_adapter_advertises_media_caps():
    a = m.MediaGenAdapter()
    caps = a.advertise_capabilities()
    assert Capability.MEDIA_IMAGE in caps
    assert Capability.MEDIA_VIDEO in caps
    assert a.engine_id == "media-gen"


def test_adapter_registered_in_package():
    import core.fabric.adapters as ad

    assert "MediaGenAdapter" in ad.__all__
    assert ad.MediaGenAdapter is m.MediaGenAdapter


def test_health_reflects_key():
    # health 必须基于真实 key 可用性，不硬编码 True
    a = m.MediaGenAdapter()
    assert a.health() is KEY_OK


def test_invoke_requires_prompt(monkeypatch):
    # 注入假 key 让适配器进入「有 key」分支，但缺 prompt 应在联网前就报错
    monkeypatch.setenv("ZHIPU_API_KEY", "dummy-for-test")
    a = m.MediaGenAdapter()
    res = a.invoke(
        InvokeRequest(capability="media.image", payload={"mode": "image"})
    )
    assert res.ok is False
    assert "prompt" in (res.error or "").lower()


def test_invoke_graceful_when_no_key(monkeypatch):
    # 无 key 时：health=False 且 invoke 绝不崩溃，明确告知需配置
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    a = m.MediaGenAdapter()
    assert a.health() is False
    res = a.invoke(
        InvokeRequest(capability="media.image", payload={
            "mode": "image", "prompt": "一只猫"})
    )
    assert res.ok is False
    assert "ZHIPU_API_KEY" in res.error


def test_fabric_hub_resolves_media_caps():
    from kernel.plugins.fabric_hub import FabricHub

    hub = FabricHub(adapters=(m.MediaGenAdapter,))
    if KEY_OK:
        assert hub.resolve_engine("media.image") == "media-gen"
        assert hub.resolve_engine("media.video") == "media-gen"
    else:
        # 无 key → health=False → 路由层应忽略（不谎报可达）
        assert hub.resolve_engine("media.image") is None


@pytest.mark.skipif(not KEY_OK, reason="需 ZHIPU_API_KEY 做真机验证")
def test_real_image_generation():
    res = m.MediaGenAdapter().invoke(
        InvokeRequest(capability="media.image", payload={
            "mode": "image",
            "prompt": "一只赛博朋克风格的小猫，霓虹灯光，简洁纯色背景",
            "size": "1024x1024",
        })
    )
    assert res.ok, res.error
    assert res.data.get("url", "").startswith("http")


@pytest.mark.skipif(not KEY_OK, reason="需 ZHIPU_API_KEY 做真机验证")
def test_real_video_generation():
    res = m.MediaGenAdapter().invoke(
        InvokeRequest(capability="media.video", payload={
            "mode": "video",
            "prompt": "A cute cat walking in a sunny garden, cinematic.",
            "size": "1280x720",
            "quality": "speed",
            "duration": 5,
            "with_audio": False,
            "poll_timeout": 180,
        })
    )
    assert res.ok, res.error
    assert res.data.get("url", "").startswith("http")
