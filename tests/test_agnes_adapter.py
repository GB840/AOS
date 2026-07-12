"""AgnesAdapter 单元测试（mock HTTP，沙箱可跑，不触网）。

验证：请求 URL / 鉴权头 / 默认模型 / 视频异步轮询逻辑 / 能力声明 / 故障隔离。
真机联调见 scripts/agnes_demo.py（在主机运行）。
"""
from __future__ import annotations

import sys
import pytest
from unittest import mock

sys.path.insert(0, "D:/AOS/src")

import core.fabric.adapters.agnes_adapter as mod
from core.fabric.adapters.agnes_adapter import AgnesAdapter, AGNES_DEFAULTS
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability


def _resp(json_body: dict, status: int = 200):
    r = mock.MagicMock()
    r.status_code = status
    r.json.return_value = json_body
    r.raise_for_status = lambda: None
    return r


def _req_mock():
    """模拟 requests 模块：按 URL 路由返回不同响应。"""
    M = mock.MagicMock()

    def _post(url, **kw):
        if url.endswith("/chat/completions"):
            return _resp({"choices": [{"message": {"content": "Hello from Agnes"}}]})
        if url.endswith("/images/generations"):
            return _resp({"data": [{"url": "https://img/1.png"}]})
        if url.endswith("/videos"):
            return _resp({"video_id": "vid_abc"})
        return _resp({})

    def _get(url, **kw):
        # 视频结果轮询端点
        return _resp({"url": "https://vid/1.mp4", "status": "done"})

    M.post.side_effect = _post
    M.get.side_effect = _get
    return M


def test_chat_builds_correct_request():
    M = _req_mock()
    a = AgnesAdapter(api_key="sk-test", base_url="https://apihub.agnes-ai.com/v1")
    with mock.patch.object(mod, "_requests", return_value=M):
        r = a.chat("你好")
    assert r.ok and r.data["content"] == "Hello from Agnes"
    # URL 必须是 Base URL + /chat/completions
    args, kwargs = M.post.call_args
    assert args[0].endswith("/chat/completions")
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["json"]["model"] == AGNES_DEFAULTS["text_model"]
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "你好"}]


def test_image_returns_items():
    M = _req_mock()
    a = AgnesAdapter(api_key="sk-test")
    with mock.patch.object(mod, "_requests", return_value=M):
        r = a.generate_image("一只猫", model="agnes-image-2.0-flash")
    assert r.ok
    assert r.data["images"] == [{"url": "https://img/1.png"}]
    args, kwargs = M.post.call_args
    assert args[0].endswith("/images/generations")
    assert kwargs["json"]["model"] == "agnes-image-2.0-flash"
    assert kwargs["json"]["prompt"] == "一只猫"


def test_video_async_poll():
    M = _req_mock()
    a = AgnesAdapter(api_key="sk-test")
    with mock.patch.object(mod, "_requests", return_value=M):
        r = a.generate_video("海上日出")
    assert r.ok
    assert r.data["video_id"] == "vid_abc"
    assert r.data["url"] == "https://vid/1.mp4"
    # 先 POST /videos，再 GET 结果端点
    assert M.post.called
    assert M.get.called
    get_args, get_kwargs = M.get.call_args
    assert "video_id" in get_kwargs["params"]
    assert get_kwargs["params"]["video_id"] == "vid_abc"


def test_health_no_key_is_dead(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    a = AgnesAdapter()  # 无 api_key 参数且环境无 key
    assert a.health() is False


def test_health_reachable_is_alive():
    M = mock.MagicMock()
    M.get.return_value = _resp({}, status=200)
    a = AgnesAdapter(api_key="sk-test")
    with mock.patch.object(mod, "_requests", return_value=M):
        assert a.health() is True


def test_health_5xx_is_dead():
    M = mock.MagicMock()
    M.get.return_value = _resp({}, status=500)
    a = AgnesAdapter(api_key="sk-test")
    with mock.patch.object(mod, "_requests", return_value=M):
        assert a.health() is False


def test_unsupported_capability_isolated():
    a = AgnesAdapter(api_key="sk-test")
    r = a.invoke(InvokeRequest(capability="nonsense", payload={}))
    assert r.ok is False


def test_advertises_three_capabilities():
    a = AgnesAdapter(api_key="sk-test")
    caps = {c.value if hasattr(c, "value") else str(c) for c in a.advertise_capabilities()}
    assert caps == {"inference.llm", "media.image", "media.video"}


def test_registered_in_fabric_hub():
    """Agnes 作为能力枢纽引擎被登记，且可按 media.image 路由到它。"""
    with mock.patch.object(AgnesAdapter, "health", return_value=True):
        from kernel.plugins.fabric_hub import FabricHub
        hub = FabricHub(adapters=(AgnesAdapter,))
        advertised = hub.advertised()
        assert "agnes" in advertised
        assert "media.image" in advertised["agnes"]
        assert "media.video" in advertised["agnes"]
        assert hub.resolve_engine("media.image") == "agnes"
        assert hub.resolve_engine("media.video") == "agnes"


def test_agnes_is_default_gateway_when_key_present():
    """wiring 把 Agnes 排到网关链最前：默认（空 model_id）对话落到 Agnes。

    复刻 build_default_kernel 的网关组装（跳过重型 brain 注入），断言
    AgnesModelGateway 在 CompositeModelGateway 中排首。
    """
    import os
    if not os.environ.get("AGNES_API_KEY"):
        pytest.skip("需要 AGNES_API_KEY 才纳入 Agnes 网关")
    from kernel.plugins.agnes_gateway import AgnesModelGateway
    from kernel.plugins.litellm_gateway import LiteLLMModelGateway
    from kernel.plugins.composite_gateway import CompositeModelGateway

    gateways = [AgnesModelGateway(), LiteLLMModelGateway()]
    gw = CompositeModelGateway(gateways)
    assert gw.list_models()[0].model_id.startswith("agnes")
    # 默认空 model_id 经 _ordered 落到链首（Agnes）
    assert gw._ordered("")[0] is gateways[0]
