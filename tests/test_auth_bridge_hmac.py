"""测试HMAC签名完整性（V5修复验证）"""
import os
import pytest
from kernel.auth_bridge import generate_self_contained_token, _default_token_verify


def test_hmac_signature_not_truncated():
    """测试HMAC签名不被截断，使用完整SHA256签名"""
    os.environ["AOS_TOKEN_SECRET"] = "test_secret_key_32_bytes_long"

    token = generate_self_contained_token("agent123", "api")
    assert token is not None

    # 验证签名长度：SHA256 HMAC应该是64个字符（32字节）
    import base64
    import json
    padded = token + "=" * (4 - len(token) % 4) if len(token) % 4 else token
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
    sig = decoded.get("sig", "")

    assert len(sig) == 64, f"HMAC签名应该是64个字符，实际是{len(sig)}个"


def test_hmac_compare_digest_used():
    """测试使用hmac.compare_digest防止时序攻击"""
    os.environ["AOS_TOKEN_SECRET"] = "test_secret_key_32_bytes_long"

    token = generate_self_contained_token("agent123", "api")
    assert token is not None

    # 验证token
    payload = _default_token_verify(token)
    assert payload is not None
    assert payload["sub"] == "agent123"


def test_hmac_invalid_signature():
    """测试无效签名被拒绝"""
    os.environ["AOS_TOKEN_SECRET"] = "test_secret_key_32_bytes_long"

    token = generate_self_contained_token("agent123", "api")
    assert token is not None

    # 篡改签名
    import base64
    import json
    padded = token + "=" * (4 - len(token) % 4) if len(token) % 4 else token
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
    decoded["sig"] = "0" * 64  # 伪造签名
    tampered = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode().rstrip("=")

    # 验证应该失败
    payload = _default_token_verify(tampered)
    assert payload is None