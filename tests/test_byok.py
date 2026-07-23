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
