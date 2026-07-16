"""VLMAdapter 单元测试（无网，纯 glue + 档位逻辑验证）。

真实 HTTP 发送集中在 _describe_cloud / _describe_local，本测试通过
monkeypatch 注入假 transport 验证：
- 能力声明、诚实 health（无后端返 False）
- 云端请求体构造（image_url data URI + model）
- 档位选择（auto 优先云端、本地兜底、payload 覆盖）
- 结果投影、未知 action、缺图报错
"""
from __future__ import annotations

import base64

import pytest

from core.fabric.adapters.vlm_adapter import (
    TIER_CLOUD,
    TIER_LOCAL,
    VLMAdapter,
)
from core.fabric.adapter import InvokeRequest, InvokeResult
from core.fabric.capability import Capability


@pytest.fixture
def fake_b64():
    return base64.b64encode(b"\x89PNG fake image bytes").decode("ascii")


def test_advertises_vision_capability():
    a = VLMAdapter()
    caps = a.advertise_capabilities()
    assert caps == [Capability.VISION_UNDERSTAND]
    assert a.engine_id == "vlm"


def test_health_false_when_no_backend(monkeypatch):
    # 无 key + 本地无视觉模型 → 诚实 False
    monkeypatch.setenv("VLM_API_KEY", "")
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", staticmethod(lambda: False))
    a = VLMAdapter()
    assert a.health() is False
    assert a._resolve_tier() is None
    det = a.health_detail()
    assert det["ready"] is False
    assert "无可用" in det["note"]


def test_cloud_request_body_shape(fake_b64):
    a = VLMAdapter()
    body = a._build_cloud_body(fake_b64, "描述这张图")
    assert body["model"] == "gpt-4o-mini"
    assert body["stream"] is False
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "描述这张图"}
    img = content[1]
    assert img["type"] == "image_url"
    assert img["image_url"]["url"].startswith("data:image/png;base64,")
    assert fake_b64 in img["image_url"]["url"]


def test_describe_cloud_success(monkeypatch, fake_b64):
    monkeypatch.setenv("VLM_API_KEY", "sk-test")
    captured = {}

    def fake_cloud(self, image_b64, prompt):
        captured["image_b64"] = image_b64
        captured["prompt"] = prompt
        return "这是一张截图，显示了登录按钮。"

    monkeypatch.setattr(VLMAdapter, "_describe_cloud", fake_cloud)
    a = VLMAdapter()
    assert a._resolve_tier() == TIER_CLOUD
    res = a.invoke(InvokeRequest(
        capability="vision.understand",
        payload={"image_base64": fake_b64, "prompt": "描述这张图"},
    ))
    assert isinstance(res, InvokeResult)
    assert res.ok is True
    assert res.data["text"] == "这是一张截图，显示了登录按钮。"
    assert res.data["tier"] == TIER_CLOUD
    assert captured["image_b64"] == fake_b64


def test_describe_local_fallback(monkeypatch, fake_b64):
    monkeypatch.setenv("VLM_API_KEY", "")  # 无 key
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", staticmethod(lambda: True))

    def fake_local(self, image_b64, prompt):
        return "本地 ollama 识别：界面顶部有标题栏。"

    monkeypatch.setattr(VLMAdapter, "_describe_local", fake_local)
    a = VLMAdapter()
    assert a._resolve_tier() == TIER_LOCAL  # auto 落到本地
    res = a.invoke(InvokeRequest(
        capability="vision.understand",
        payload={"image_base64": fake_b64},
    ))
    assert res.ok is True
    assert res.data["tier"] == TIER_LOCAL


def test_payload_tier_override(monkeypatch, fake_b64):
    monkeypatch.setenv("VLM_API_KEY", "sk-test")
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", staticmethod(lambda: True))
    monkeypatch.setattr(VLMAdapter, "_describe_local",
                        lambda self, b, p: "local-out")
    a = VLMAdapter()
    # 显式指定 local 档，即使云端可用也应走本地
    res = a.invoke(InvokeRequest(
        capability="vision.understand",
        payload={"image_base64": fake_b64, "tier": TIER_LOCAL},
    ))
    assert res.ok is True
    assert res.data["tier"] == TIER_LOCAL


def test_unknown_action_rejected():
    a = VLMAdapter()
    res = a.invoke(InvokeRequest(
        capability="vision.understand",
        payload={"action": "translate", "image_base64": "x"},
    ))
    assert res.ok is False
    assert "未知 action" in res.error


def test_missing_image_rejected(monkeypatch):
    # 先提供可用后端，才能走到「缺图」这一层校验
    monkeypatch.setenv("VLM_API_KEY", "sk-test")
    monkeypatch.setattr(VLMAdapter, "_describe_cloud",
                        lambda self, b, p: "x")
    a = VLMAdapter()
    res = a.invoke(InvokeRequest(
        capability="vision.understand", payload={},
    ))
    assert res.ok is False
    assert "image_path 或 image_base64" in res.error
