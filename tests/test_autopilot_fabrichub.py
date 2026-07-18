"""autopilot ↔ FabricHub 融合测试（双轨债⑤）。

验证：
- 默认（AOS_AUTOPILOT_USE_FABRICHUB 未设）_get_hub() 返回 None，走本地适配器；
- 启用后 _route 的真实适配器调用改经 FabricHub.route() 统一派发
  （web.search / action.code_exec / inference.llm 三类）；
- cognition.* 在 hub 路径归并到 inference.llm；
- hub 不可用时 _dispatch 本地兜底仍调用对应惰性适配器。

两种路径返回 InvokeResult(.data 同构)，autopilot 真实闸门/指标逻辑不受影响。
"""
from unittest import mock

from core.fabric.adapter import InvokeResult

from kernel import autopilot as ap


def test_get_hub_returns_none_when_disabled():
    ap._AUTOPILOT_USE_HUB = False
    ap._HUB = None
    assert ap._get_hub() is None


def test_route_web_search_delegates_to_fabrichub(monkeypatch):
    fake_hub = mock.MagicMock()
    fake_hub.route.return_value = InvokeResult(
        ok=True,
        data={"results": [{"url": "http://example.com", "title": "t", "snippet": "s"}]},
    )
    monkeypatch.setattr(ap, "_get_hub", lambda: fake_hub)

    res = ap._route("web.search", {"query": "ffmpeg"})

    assert res.ok is True
    fake_hub.route.assert_called_once()
    called_cap, called_payload = fake_hub.route.call_args[0]
    assert called_cap == "web.search"
    assert called_payload["query"] == "ffmpeg"
    assert called_payload["count"] == 5


def test_route_code_exec_delegates_to_fabrichub(monkeypatch):
    fake_hub = mock.MagicMock()
    fake_hub.route.return_value = InvokeResult(ok=True, data={"output": "hello world"})
    monkeypatch.setattr(ap, "_get_hub", lambda: fake_hub)

    res = ap._route("action.code_exec", {"code": "echo hello"})

    assert res.ok is True
    called_cap, called_payload = fake_hub.route.call_args[0]
    assert called_cap == "action.code_exec"
    assert called_payload["code"] == "echo hello"


def test_route_inference_delegates_to_fabrichub(monkeypatch):
    fake_hub = mock.MagicMock()
    fake_hub.route.return_value = InvokeResult(
        ok=True,
        data={"content": "这是一段足够长的真实推理产出文字用于通过真实闸门校验避免被判为敷衍空转"},
    )
    monkeypatch.setattr(ap, "_get_hub", lambda: fake_hub)

    res = ap._route("inference.llm", {"task": "写报告", "content": "材料"})

    assert res.ok is True
    called_cap, _ = fake_hub.route.call_args[0]
    assert called_cap == "inference.llm"


def test_route_cognition_reasoning_merges_to_inference_llm(monkeypatch):
    fake_hub = mock.MagicMock()
    fake_hub.route.return_value = InvokeResult(
        ok=True,
        data={"content": "足够长的推理产出文字用于通过真实闸门校验避免被判为敷衍空转失败"},
    )
    monkeypatch.setattr(ap, "_get_hub", lambda: fake_hub)

    res = ap._route("cognition.reasoning", {"task": "x", "content": "材料"})

    assert res.ok is True
    called_cap, _ = fake_hub.route.call_args[0]
    assert called_cap == "inference.llm"


def test_dispatch_local_fallback_uses_search_adapter(monkeypatch):
    fake_adapter = mock.MagicMock()
    fake_adapter.invoke.return_value = InvokeResult(ok=True, data={"results": [{"url": "u"}]})
    monkeypatch.setattr(ap, "_get_hub", lambda: None)
    monkeypatch.setattr(ap, "_get_search", lambda: fake_adapter)

    res = ap._dispatch("web.search", {"type": "search", "query": "x", "count": 5})

    assert res.ok is True
    fake_adapter.invoke.assert_called_once()
    # 本地兜底路径仍用 InvokeRequest 包装
    req = fake_adapter.invoke.call_args[0][0]
    assert req.capability == "web.search"
    assert req.payload["query"] == "x"
