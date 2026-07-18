"""VLM 多模态适配器单元测试（Task 7: Multi-modal Agent）。

覆盖：
- 档位解析：auto / cloud / local，无 key 无 ollama 时的降级路径
- health / health_detail：诚实判定，无后端时 health=False
- advertise_capabilities / engine_id / tier 契约
- invoke 错误路径：未知 action、无 image、读文件失败、无后端、空结果
- _build_cloud_body：纯函数请求体构造（不触网）
- _describe_cloud / _describe_local：注入假 transport 验证 glue（请求 URL/headers/响应解析）
- tier 选择优先级：auto 时 cloud 优先于 local
- _probe_ollama：探活 + 模型缺失识别

设计：所有测试都通过 monkeypatch 控制环境变量与传输层，零联网、零外部依赖。
"""
from __future__ import annotations

import base64
import json
from typing import Any

import pytest

# 预禁用 tiktoken（避免网络下载）
import kernel.pulse.cost_tracker as _ct  # noqa: E402
_ct._TIKTOKEN_ENC = False

from core.fabric.adapters.vlm_adapter import (  # noqa: E402
    TIER_AUTO, TIER_CLOUD, TIER_LOCAL, VLMAdapter,
)
from core.fabric.adapter import InvokeRequest  # noqa: E402
from core.fabric.capability import Capability  # noqa: E402


# ── 公共 fixture ──

@pytest.fixture
def clean_vlm_env(monkeypatch):
    """清空 VLM 相关环境变量，每个测试从零开始。"""
    for k in ("VLM_API_KEY", "VLM_TIER", "VLM_MODEL",
              "VLM_CLOUD_BASE", "VLM_OLLAMA_URL", "VLM_OLLAMA_MODEL"):
        monkeypatch.delenv(k, raising=False)
    # 默认无 key、无 ollama
    return monkeypatch


@pytest.fixture
def cloud_env(clean_vlm_env):
    """配置云端可用（有 key）。"""
    clean_vlm_env.setenv("VLM_API_KEY", "sk-test-fake-key")
    clean_vlm_env.setenv("VLM_MODEL", "gpt-4o-mini")
    clean_vlm_env.setenv("VLM_CLOUD_BASE", "https://fake.api/v1")
    return clean_vlm_env


# ── 1. 档位解析 ──

def test_resolve_tier_auto_no_backend_returns_none(clean_vlm_env):
    """auto 档位无 key 无 ollama → None（诚实，不谎报）。"""
    adapter = VLMAdapter()
    assert adapter._resolve_tier() is None
    assert adapter.health() is False


def test_resolve_tier_auto_picks_cloud_when_key_present(cloud_env):
    """auto 档位有 key 时优先选 cloud。"""
    adapter = VLMAdapter()
    assert adapter._resolve_tier() == TIER_CLOUD
    assert adapter.health() is True


def test_resolve_tier_explicit_cloud_unhealthy_without_key(clean_vlm_env):
    """显式 cloud 档位无 key → None。"""
    adapter = VLMAdapter(tier=TIER_CLOUD)
    assert adapter._resolve_tier() is None
    assert adapter.health() is False


def test_resolve_tier_explicit_local_unhealthy_without_ollama(clean_vlm_env, monkeypatch):
    """显式 local 档位但 ollama 不可达 → None。"""
    adapter = VLMAdapter(tier=TIER_LOCAL)
    # _probe_ollama 默认会真连 127.0.0.1:11434，强制返回 False
    monkeypatch.setattr(adapter, "_probe_ollama", lambda: False)
    assert adapter._resolve_tier() is None
    assert adapter.health() is False


def test_resolve_tier_local_available_when_ollama_has_model(clean_vlm_env, monkeypatch):
    """local 档位且 ollama 有视觉模型 → TIER_LOCAL。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: True)
    adapter = VLMAdapter(tier=TIER_LOCAL)
    assert adapter._resolve_tier() == TIER_LOCAL
    assert adapter.health() is True


def test_available_tiers_empty_when_no_backend(clean_vlm_env, monkeypatch):
    """无任何后端时 available_tiers 应为空。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: False)
    adapter = VLMAdapter()
    assert adapter.available_tiers() == []


def test_available_tiers_includes_cloud_when_key_present(cloud_env):
    """有 key 时 available_tiers 应含 cloud。"""
    adapter = VLMAdapter()
    assert TIER_CLOUD in adapter.available_tiers()


def test_tier_priority_cloud_first(cloud_env, monkeypatch):
    """auto 时 cloud 应优先于 local（即使 local 也可用）。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: True)
    adapter = VLMAdapter()
    # cloud 和 local 都可用，但 cloud 应优先
    assert adapter._resolve_tier() == TIER_CLOUD


# ── 2. health_detail ──

def test_health_detail_no_backend(clean_vlm_env, monkeypatch):
    """无后端时 health_detail 应含「无可用」提示。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: False)
    adapter = VLMAdapter()
    d = adapter.health_detail()
    assert d["engine"] == "vlm"
    assert d["ready"] is False
    assert d["resolved_tier"] is None
    assert "无可用" in d["note"]


def test_health_detail_cloud_mode(cloud_env):
    """cloud 可用时 health_detail 应展示云端信息。"""
    adapter = VLMAdapter()
    d = adapter.health_detail()
    assert d["mode"] == "cloud"
    assert d["ready"] is True
    assert d["resolved_tier"] == TIER_CLOUD
    assert d["model"] == "gpt-4o-mini"
    assert "VLM_API_KEY" in d["note"]


def test_health_detail_local_mode(clean_vlm_env, monkeypatch):
    """local 可用时 health_detail 应展示本地 ollama 信息。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: True)
    adapter = VLMAdapter(tier=TIER_LOCAL)
    d = adapter.health_detail()
    assert d["mode"] == "local"
    assert d["ready"] is True
    assert d["resolved_tier"] == TIER_LOCAL
    assert "ollama" in d["note"]


# ── 3. 契约 ──

def test_engine_id():
    """engine_id 应为 'vlm'。"""
    assert VLMAdapter().engine_id == "vlm"


def test_advertise_capabilities():
    """应只声明 VISION_UNDERSTAND。"""
    caps = VLMAdapter().advertise_capabilities()
    assert caps == [Capability.VISION_UNDERSTAND]


def test_tier_property_returns_resolved(cloud_env):
    """tier() 应返回解析后的实际档位。"""
    adapter = VLMAdapter()
    assert adapter.tier() == TIER_CLOUD


# ── 4. invoke 错误路径 ──

def test_invoke_unknown_action_returns_error(cloud_env):
    """未知 action 应返回 ok=False。"""
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"action": "unknown"})
    result = adapter.invoke(req)
    assert result.ok is False
    assert "未知 action" in result.error


def test_invoke_no_backend_returns_error(clean_vlm_env, monkeypatch):
    """无可用后端时 invoke 应返回 ok=False。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: False)
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake", "prompt": "describe"})
    result = adapter.invoke(req)
    assert result.ok is False
    assert "无可用" in result.error


def test_invoke_no_image_returns_error(cloud_env):
    """无 image_path/image_base64 应返回 ok=False。"""
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"prompt": "describe"})
    result = adapter.invoke(req)
    assert result.ok is False
    assert "image_path" in result.error or "image_base64" in result.error


def test_invoke_image_path_not_found_returns_error(cloud_env, tmp_path):
    """image_path 不存在应返回读取失败错误。"""
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_path": str(tmp_path / "nonexistent.png")})
    result = adapter.invoke(req)
    assert result.ok is False
    assert "image_path" in result.error or "读取" in result.error


def test_invoke_image_path_reads_file(cloud_env, tmp_path, monkeypatch):
    """image_path 存在时应读文件并调用 _describe_cloud。"""
    # 准备一个假图片
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-data")
    expected_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-png-data").decode("ascii")

    called = {"image_b64": None, "prompt": None}

    def fake_describe_cloud(self, image_b64, prompt):
        called["image_b64"] = image_b64
        called["prompt"] = prompt
        return "fake description"

    monkeypatch.setattr(VLMAdapter, "_describe_cloud", fake_describe_cloud)
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_path": str(img_path), "prompt": "what is this"})
    result = adapter.invoke(req)
    assert result.ok is True
    assert result.data["text"] == "fake description"
    assert result.data["tier"] == TIER_CLOUD
    assert called["image_b64"] == expected_b64
    assert called["prompt"] == "what is this"


def test_invoke_empty_response_returns_error(cloud_env, monkeypatch):
    """VLM 返回空字符串应返回 ok=False。"""
    monkeypatch.setattr(VLMAdapter, "_describe_cloud",
                        lambda self, b64, p: "")
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake", "prompt": "describe"})
    result = adapter.invoke(req)
    assert result.ok is False
    assert "空结果" in result.error


def test_invoke_call_exception_returns_error(cloud_env, monkeypatch):
    """_describe_cloud 抛异常时 invoke 应捕获并返回 ok=False。"""
    monkeypatch.setattr(VLMAdapter, "_describe_cloud",
                        lambda self, b64, p: (_ for _ in ()).throw(RuntimeError("连接超时")))
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake"})
    result = adapter.invoke(req)
    assert result.ok is False
    assert "VLM(cloud)" in result.error
    assert "连接超时" in result.error


def test_invoke_uses_default_prompt_when_missing(cloud_env, monkeypatch):
    """未传 prompt 时应使用默认 prompt。"""
    captured = {"prompt": None}
    def fake_describe_cloud(self, image_b64, prompt):
        captured["prompt"] = prompt
        return "desc"
    monkeypatch.setattr(VLMAdapter, "_describe_cloud", fake_describe_cloud)
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake"})
    result = adapter.invoke(req)
    assert result.ok is True
    assert "描述" in captured["prompt"]  # 默认 prompt 含「描述」


# ── 5. _build_cloud_body 纯函数 ──

def test_build_cloud_body_structure(cloud_env):
    """_build_cloud_body 应构造合法的 OpenAI 兼容请求体。"""
    adapter = VLMAdapter()
    body = adapter._build_cloud_body("abc123", "describe this image")
    assert body["model"] == "gpt-4o-mini"
    assert body["stream"] is False
    assert len(body["messages"]) == 1
    msg = body["messages"][0]
    assert msg["role"] == "user"
    # content 应含 text 和 image_url 两段
    types = {c["type"] for c in msg["content"]}
    assert "text" in types
    assert "image_url" in types
    # image_url 应是 data URL
    image_url = next(c["image_url"]["url"] for c in msg["content"]
                     if c["type"] == "image_url")
    assert image_url.startswith("data:image/png;base64,abc123")


def test_build_cloud_body_prompt_in_text(cloud_env):
    """prompt 应出现在 text 段。"""
    adapter = VLMAdapter()
    body = adapter._build_cloud_body("xxx", "hello world")
    text_seg = next(c for c in body["messages"][0]["content"] if c["type"] == "text")
    assert text_seg["text"] == "hello world"


# ── 6. _describe_cloud 真实传输（注入假 requests） ──

class _FakeResponse:
    """模拟 requests.Response。"""
    def __init__(self, status_code: int, json_data: Any = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def test_describe_cloud_success(cloud_env, monkeypatch):
    """_describe_cloud 应正确解析 200 响应的 content。"""
    captured = {"url": None, "headers": None, "body": None}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "这是一只猫"}}]
        })

    # 注入 fake requests 模块到 sys.modules
    import sys
    fake_mod = type(sys)("requests")
    fake_mod.post = fake_post
    monkeypatch.setitem(sys.modules, "requests", fake_mod)

    # VLM_CLOUD_BASE 是模块级常量（import 时固定），需直接 patch 模块属性
    import core.fabric.adapters.vlm_adapter as vlm_mod
    monkeypatch.setattr(vlm_mod, "VLM_CLOUD_BASE", "https://fake.api/v1")

    adapter = VLMAdapter()
    text = adapter._describe_cloud("img_b64_data", "描述图片")
    assert text == "这是一只猫"
    assert captured["url"] == "https://fake.api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test-fake-key"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["body"]["model"] == "gpt-4o-mini"


def test_describe_cloud_non_200_raises(cloud_env, monkeypatch):
    """非 200 响应应抛 RuntimeError 含状态码。"""
    import sys
    fake_mod = type(sys)("requests")
    fake_mod.post = lambda *a, **kw: _FakeResponse(401, text="unauthorized")
    monkeypatch.setitem(sys.modules, "requests", fake_mod)

    adapter = VLMAdapter()
    with pytest.raises(RuntimeError) as exc:
        adapter._describe_cloud("img", "prompt")
    assert "401" in str(exc.value)


def test_describe_cloud_uses_api_key(cloud_env, monkeypatch):
    """_describe_cloud 应读取 VLM_API_KEY 环境变量。"""
    cloud_env.setenv("VLM_API_KEY", "sk-dynamic-key-123")
    captured = {"auth": None}
    def fake_post(url, json=None, headers=None, timeout=None):
        captured["auth"] = headers["Authorization"]
        return _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})
    import sys
    fake_mod = type(sys)("requests")
    fake_mod.post = fake_post
    monkeypatch.setitem(sys.modules, "requests", fake_mod)

    adapter = VLMAdapter()
    adapter._describe_cloud("img", "p")
    assert captured["auth"] == "Bearer sk-dynamic-key-123"


# ── 7. _describe_local 真实传输（注入假 urllib） ──

class _FakeUrlopenResponse:
    def __init__(self, status: int, data: Any):
        self.status = status
        self._data = data

    def read(self):
        return json.dumps(self._data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_describe_local_success(clean_vlm_env, monkeypatch):
    """_describe_local 应正确解析 ollama /api/chat 响应。"""
    captured = {"url": None, "body": None}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url if hasattr(req, "full_url") else req
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeUrlopenResponse(200, {"message": {"content": "本地视觉结果"}})

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    adapter = VLMAdapter(tier=TIER_LOCAL)
    text = adapter._describe_local("img_b64", "描述")
    assert text == "本地视觉结果"
    assert "/api/chat" in captured["url"]
    assert captured["body"]["model"] == "minicpm-v:2b"
    assert captured["body"]["messages"][0]["images"] == ["img_b64"]


def test_describe_local_missing_content_returns_empty(clean_vlm_env, monkeypatch):
    """ollama 响应缺 message.content 时应返回空字符串（上层判失败）。"""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeUrlopenResponse(200, {}))
    adapter = VLMAdapter(tier=TIER_LOCAL)
    text = adapter._describe_local("img", "p")
    assert text == ""


# ── 8. _probe_ollama ──

def test_probe_ollama_returns_true_when_model_present(clean_vlm_env, monkeypatch):
    """ollama /api/tags 含目标模型时探活成功。"""
    def fake_urlopen(req, timeout=None):
        return _FakeUrlopenResponse(200, {
            "models": [{"name": "minicpm-v:2b"}, {"name": "qwen2.5:7b"}]
        })
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    adapter = VLMAdapter()
    assert adapter._probe_ollama() is True


def test_probe_ollama_returns_false_when_model_missing(clean_vlm_env, monkeypatch):
    """ollama /api/tags 不含目标模型时探活失败（避免「health=True 但 invoke 失败」表里不一）。"""
    def fake_urlopen(req, timeout=None):
        return _FakeUrlopenResponse(200, {
            "models": [{"name": "qwen2.5:7b"}, {"name": "minicpm-mem:1b"}]
        })
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    adapter = VLMAdapter()
    assert adapter._probe_ollama() is False


def test_probe_ollama_returns_false_on_connection_error(clean_vlm_env, monkeypatch):
    """ollama 不可达时探活失败（不抛异常）。"""
    def fake_urlopen(req, timeout=None):
        raise ConnectionRefusedError("no ollama")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    adapter = VLMAdapter()
    assert adapter._probe_ollama() is False


def test_probe_ollama_returns_false_on_non_200(clean_vlm_env, monkeypatch):
    """ollama 返回非 200 时探活失败。"""
    def fake_urlopen(req, timeout=None):
        return _FakeUrlopenResponse(500, {})
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    adapter = VLMAdapter()
    assert adapter._probe_ollama() is False


# ── 9. 端到端：invoke + local tier ──

def test_invoke_local_tier_success(clean_vlm_env, monkeypatch):
    """端到端：local tier + 假 ollama → invoke 返回 ok=True。"""
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: True)

    def fake_urlopen(req, timeout=None):
        return _FakeUrlopenResponse(200, {"message": {"content": "local desc"}})
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    adapter = VLMAdapter(tier=TIER_LOCAL)
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake", "prompt": "describe"})
    result = adapter.invoke(req)
    assert result.ok is True
    assert result.data["text"] == "local desc"
    assert result.data["tier"] == TIER_LOCAL
    assert result.data["engine"] == "vlm"


def test_invoke_with_explicit_tier_override(clean_vlm_env, monkeypatch):
    """payload 中带 tier 时应覆盖适配器默认档位。"""
    # 默认 cloud 可用，但 payload 指定 local
    cloud_env = clean_vlm_env
    cloud_env.setenv("VLM_API_KEY", "sk-test")
    monkeypatch.setattr(VLMAdapter, "_probe_ollama", lambda self: True)

    def fake_urlopen(req, timeout=None):
        return _FakeUrlopenResponse(200, {"message": {"content": "via local"}})
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    adapter = VLMAdapter()  # 默认 auto → 解析为 cloud
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake", "tier": TIER_LOCAL})
    result = adapter.invoke(req)
    assert result.ok is True
    assert result.data["tier"] == TIER_LOCAL


# ── 10. 边界 ──

def test_default_tier_is_auto(clean_vlm_env):
    """不传 tier 时默认为 auto。"""
    adapter = VLMAdapter()
    assert adapter._tier == TIER_AUTO


def test_invoke_result_data_has_prompt(cloud_env, monkeypatch):
    """成功 invoke 的 data 应含原始 prompt（便于回溯）。"""
    monkeypatch.setattr(VLMAdapter, "_describe_cloud",
                        lambda self, b64, p: "desc")
    adapter = VLMAdapter()
    req = InvokeRequest(capability=Capability.VISION_UNDERSTAND,
                        payload={"image_base64": "fake", "prompt": "custom prompt"})
    result = adapter.invoke(req)
    assert result.ok is True
    assert result.data["prompt"] == "custom prompt"
