"""MediaGenAdapter 分派 + 返回契约离线测试（零网络/零 key）。

覆盖：
- invoke 按 req.capability 分派（修复 route(media.video) 落到本适配器时
  因缺 payload.mode 被默认当文生图的隐患，与 fabric 路由范式一致）；
- payload.mode 兼容降级；
- 文生图/文生视频成功路径的返回形状（url 字段可被 scroll_world 提取）；
- 缺 key 优雅降级（不谎报 live/ok）。
"""
import os
import sys
from unittest.mock import patch

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters import media_gen_adapter as mg


def _fake_adapter() -> mg.MediaGenAdapter:
    a = mg.MediaGenAdapter()
    a._api_key = "test-key"
    a._available = True
    return a


def _video_side_effect(method, url, key, body=None, timeout=60):
    if url.endswith("/videos/generations"):
        return ({"id": "task_1"}, 200)
    if "/async-result/" in url:
        return ({"task_status": "SUCCESS",
                 "video_result": [{"url": "http://example/v.mp4"}]}, 200)
    return ({}, 200)


def test_invoke_video_by_capability_without_mode():
    """route(media.video) 落到 media-gen 时（不带 mode）必须正确出视频。"""
    a = _fake_adapter()
    with patch.object(mg, "_http_json", side_effect=_video_side_effect):
        res = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO,
                                     payload={"prompt": "a cat"}))
    assert res.ok, res.error
    assert res.data["url"] == "http://example/v.mp4"


def test_invoke_image_by_capability():
    a = _fake_adapter()
    with patch.object(mg, "_http_json", return_value=(
            {"data": [{"url": "http://example/i.png"}]}, 200)):
        res = a.invoke(InvokeRequest(capability=Capability.MEDIA_IMAGE,
                                     payload={"prompt": "a cat"}))
    assert res.ok, res.error
    assert res.data["url"] == "http://example/i.png"


def test_invoke_mode_fallback_video():
    """即使 capability 与 media 语义一致，mode=video 也应走视频（兼容降级）。"""
    a = _fake_adapter()
    with patch.object(mg, "_http_json", side_effect=_video_side_effect):
        res = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO,
                                     payload={"mode": "video", "prompt": "x"}))
    assert res.ok, res.error
    assert res.data["url"].endswith(".mp4")


def test_invoke_missing_key_errors():
    a = mg.MediaGenAdapter()
    a._api_key = None
    a._available = False
    res = a.invoke(InvokeRequest(capability=Capability.MEDIA_IMAGE,
                                 payload={"prompt": "x"}))
    assert not res.ok
    assert "ZHIPU_API_KEY" in (res.error or "")
