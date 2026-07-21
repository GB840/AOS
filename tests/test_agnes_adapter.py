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
from core.fabric.capability import Capability, ENGINE_CAPABILITY_MAP


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


def test_generate_image_rejected_after_media_exit():
    """收圆后 agnes 已退出 media 供给，便捷方法应诚实拒绝而非连不可达云端。"""
    a = AgnesAdapter(api_key="sk-test")
    r = a.generate_image("一只猫", model="agnes-image-2.0-flash")
    assert r.ok is False
    assert "已退出 media" in (r.error or "")


def test_generate_video_rejected_after_media_exit():
    a = AgnesAdapter(api_key="sk-test")
    r = a.generate_video("海上日出")
    assert r.ok is False
    assert "已退出 media" in (r.error or "")


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


def test_advertises_only_llm_gateway():
    """收圆后 agnes 只声明 LLM Gateway，不再声明 media.image / media.video。"""
    a = AgnesAdapter(api_key="sk-test")
    caps = {c.value if hasattr(c, "value") else str(c) for c in a.advertise_capabilities()}
    assert caps == {"inference.llm"}


def test_invoke_media_rejected():
    """invoke 直打 media 能力应诚实拒绝（而非连不可达 agnes 云端 503 假活）。"""
    a = AgnesAdapter(api_key="sk-test")
    r = a.invoke(InvokeRequest(capability=Capability.MEDIA_IMAGE, payload={"prompt": "x"}))
    assert r.ok is False
    assert "已退出 media" in (r.error or "")
    r2 = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO, payload={"prompt": "x"}))
    assert r2.ok is False
    assert "已退出 media" in (r2.error or "")


def test_registered_in_fabric_hub_no_media():
    """agnes 在能力枢纽里只登记 LLM Gateway，不登记 media（收圆结论）。

    用静态 ENGINE_CAPABILITY_MAP 校验——它正是 fabric_hub 路由的依据，
    无需拉起完整 FabricHub（其重型 import 会让单测跑 ~2 分钟，见 cognee/
    litellm/google.genai 等依赖加载）。test_media_routing 也守同一结论，
    此处从 agnes 适配器视角再断言一次，避免误把 media 能力加回。
    """
    caps = ENGINE_CAPABILITY_MAP["agnes"]
    assert Capability.LLM_GATEWAY in caps
    # 收圆后 agnes 不再声明 media 能力
    assert Capability.MEDIA_IMAGE not in caps
    assert Capability.MEDIA_VIDEO not in caps


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


def test_no_dead_media_methods():
    """agnes 收圆后应彻底清除 _image/_video/_poll_video 等死代码方法。

    这些方法是「agnes 退出 media 供给」前的连云端实现，收圆后 invoke 与
    generate_* 均已诚实拒绝、不再调用。残留会成为误导性的不可达代码。
    """
    a = AgnesAdapter(api_key="sk-test")
    for name in ("_image", "_video", "_poll_video", "_extract_video_id",
                 "_extract_video_url", "_extract_status", "_derive_result_url"):
        assert not hasattr(a, name), f"agnes 仍残留死代码方法 {name}"
