"""BYOK 模型供应商管理测试。

覆盖：
- provider_presets.yaml 加载与真实性（已知供应商存在）
- 密钥 Fernet 加密落库、解密往返、明文绝不落盘、列表掩码
- test_provider / chat 端点逻辑（mock 真实 LLM 调用，不联网）
"""
from __future__ import annotations

import os
import sqlite3

import pytest
from cryptography.fernet import Fernet

# 测试用 BYOK 主密钥（确定性，避免落盘 .secrets）
_TEST_MASTER = Fernet.generate_key().decode()
os.environ.setdefault("AOS_BYOK_MASTER_KEY", _TEST_MASTER)
os.environ.setdefault("AOS_ENV", "test")


class _FakeResult:
    def __init__(self, ok=True, content="pong", error=None):
        self.ok = ok
        self.data = {"content": content}
        self.error = error


class _FakeAdapter:
    def __init__(self, *a, **k):
        self.calls = []

    def invoke(self, req):
        self.calls.append(req)
        model = (req.payload or {}).get("model")
        # 模拟供应商对错误 key 的拒绝
        if (req.payload or {}).get("api_key") == "bad-key":
            return _FakeResult(ok=False, error="401 auth failed")
        return _FakeResult(ok=True, content=f"reply-from-{model}")


@pytest.fixture
def store(tmp_path, monkeypatch):
    # 用临时库，避免污染真实 tenants.db
    db = str(tmp_path / "tenants.db")
    from kernel.danchuang.tenant import byok as _byok_mod

    monkeypatch.setattr(_byok_mod, "LiteLLMAdapter", _FakeAdapter)
    from kernel.danchuang.tenant.byok import ByokStore

    return ByokStore(db_path=db)


def test_presets_loaded(store):
    presets = store.list_presets()
    assert len(presets) >= 10
    ids = {p["id"] for p in presets}
    for must in ("deepseek", "zhipu", "qwen", "moonshot", "baidu_qianfan",
                 "xfyun_spark", "minimax", "baichuan", "hunyuan", "stepfun",
                 "doubao", "lingyi", "siliconflow"):
        assert must in ids, f"预设缺失: {must}"
    # 每个供应商都有 base_url 与至少一个模型
    for p in presets:
        assert p["base_url"].startswith("https://")
        assert p["models"]


def test_save_encrypts_and_isolates(store):
    tenant_a = "tnt_A"
    tenant_b = "tnt_B"
    ok = store.save(tenant_a, "deepseek", "sk-tenantA-realkey", is_default=True)
    assert ok["ok"]
    assert ok["model"] == "deepseek-v4-flash"  # 默认取预设首个

    ok2 = store.save(tenant_b, "zhipu", "sk-tenantB-realkey")
    assert ok2["ok"]

    # 直查库：明文绝不能落盘
    conn = sqlite3.connect(store.tm.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT tenant_id, provider, key_cipher, key_hash FROM tenant_provider_keys"
    ).fetchall()
    conn.close()
    by_provider = {(r["tenant_id"], r["provider"]): r for r in rows}
    assert (tenant_a, "deepseek") in by_provider
    assert (tenant_b, "zhipu") in by_provider
    cipher_a = by_provider[(tenant_a, "deepseek")]["key_cipher"]
    cipher_b = by_provider[(tenant_b, "zhipu")]["key_cipher"]
    assert cipher_a != "sk-tenantA-realkey"           # 非明文
    assert "sk-tenantA-realkey" not in cipher_a        # 不含明文片段
    assert cipher_a != cipher_b                        # 同明文不同密文（随机 IV）

    # 解密往返一致
    from utils.keystore import decrypt_secret
    assert decrypt_secret(cipher_a) == "sk-tenantA-realkey"
    assert decrypt_secret(cipher_b) == "sk-tenantB-realkey"

    # 列表掩码：不含明文/密文
    listed = store.list_keys(tenant_a)
    assert len(listed) == 1
    assert "key_cipher" not in listed[0]
    assert listed[0]["key_masked"].startswith("****")
    assert listed[0]["is_default"] is True


def test_default_and_delete(store):
    store.save("t1", "deepseek", "sk-d")
    store.save("t1", "zhipu", "sk-z")
    # 首个 deepseek 应为默认
    assert store.tm.get_default_provider_key("t1")["provider"] == "deepseek"
    # 切换默认
    assert store.set_default("t1", "zhipu") is True
    assert store.tm.get_default_provider_key("t1")["provider"] == "zhipu"
    # 删除
    assert store.delete("t1", "deepseek") is True
    assert store.tm.get_provider_key("t1", "deepseek") is None
    # 删除后默认回落到 zhipu
    assert store.tm.get_default_provider_key("t1")["provider"] == "zhipu"


def test_test_provider_ok_and_fail(store):
    # 好 key
    r = store.test_provider("deepseek", "sk-good")
    assert r["ok"] is True
    assert r["model"] == "deepseek-v4-flash"
    # 坏 key（被 mock 拒绝）
    r2 = store.test_provider("deepseek", "bad-key")
    assert r2["ok"] is False
    assert "401" in (r2["error"] or "")
    # 未知供应商
    assert store.test_provider("nope", "x")["ok"] is False


def test_chat_uses_default_provider(store):
    store.save("t1", "deepseek", "sk-good", model="deepseek-v4-pro", is_default=True)
    r = store.chat("t1", "你好")
    assert r["ok"] is True
    assert r["content"] == "reply-from-deepseek-v4-pro"
    assert r["model"] == "deepseek-v4-pro"

    # 未配置时给出明确错误
    empty = store.chat("no-such-tenant", "hi")
    assert empty["ok"] is False
    assert "默认" in (empty["error"] or "")


def test_chat_with_explicit_provider(store):
    store.save("t1", "zhipu", "sk-z", model="glm-4-flash")
    r = store.chat("t1", "hi", provider="zhipu")
    assert r["ok"] is True
    assert r["model"] == "glm-4-flash"
    # 指定未保存的供应商
    assert store.chat("t1", "hi", provider="deepseek")["ok"] is False


def test_llm_override_merges_into_adapter():
    """请求级 BYOK 覆盖应并入 LiteLLMAdapter 的调用负载。

    不联网：monkeypatch litellm.completion，断言 override 的 key/base/model/
    custom_llm_provider 进入 kwargs；且 payload 已带 key 时不被覆盖（零回归）。
    """
    import sys
    from utils.llm_override import llm_override, clear_llm_override
    from core.fabric.adapters import litellm_adapter as _la

    captured = {}

    class _FakeLiteLLM:
        def completion(self, **kwargs):
            captured.update(kwargs)
            class _R:
                choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]
            return _R()

    monkeypatch_litellm = None
    orig = _la._import_litellm
    _la._import_litellm = lambda: _FakeLiteLLM()
    try:
        from core.fabric.adapters.litellm_adapter import LiteLLMAdapter, InvokeRequest
        from core.fabric.capability import Capability

        # 场景1：payload 无 key → 合并 override
        payload = {"model": "zhipu/glm-4-flash", "messages": [{"role": "user", "content": "hi"}]}
        with llm_override({
            "model": "glm-4-flash",
            "api_base": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": "sk-tenant-byok",
            "opts": {"custom_llm_provider": "openai"},
        }):
            res = LiteLLMAdapter().invoke(InvokeRequest(Capability.LLM_GATEWAY, payload=payload))
        assert res.ok is True
        assert captured["api_key"] == "sk-tenant-byok"
        assert captured["api_base"] == "https://open.bigmodel.cn/api/paas/v4"
        assert captured["custom_llm_provider"] == "openai"
        assert captured["model"] == "glm-4-flash"

        # 场景2：payload 已带 key → 不被 override 覆盖（BYOK 直调优先级）
        captured.clear()
        payload2 = {"model": "glm-4-flash", "api_key": "sk-direct",
                    "api_base": "https://x", "messages": [{"role": "user", "content": "hi"}]}
        with llm_override({"model": "glm-4-flash", "api_key": "sk-tenant-byok",
                           "api_base": "https://open.bigmodel.cn/api/paas/v4",
                           "opts": {"custom_llm_provider": "openai"}}):
            LiteLLMAdapter().invoke(InvokeRequest(Capability.LLM_GATEWAY, payload=payload2))
        assert captured["api_key"] == "sk-direct"
    finally:
        _la._import_litellm = orig
        clear_llm_override()
