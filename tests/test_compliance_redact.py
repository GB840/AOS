"""测试合规层 IP / 微信号 真实脱敏。

STATUS.md 第 11 节曾记「QQ 脱敏不一致」——实机核验 qq 早已在 _redact 补齐
（见 tests/test_compliance_qq.py）。真正的「检得出、遮不住」缺口在 `ip_address`
与 `wechat_id`：二者在 SENSITIVE_PATTERNS 被检测、却未进 _redact 的 replacements，
导致 check() 报敏感但 redacted 字段仍是明文（PII 泄露）。

本测试守护该缺口已闭合：check() 报敏感 → redacted 字段必须遮罩、原文不得残留。
"""
from src.kernel.compliance import ContentGuard


def _guard():
    return ContentGuard(mode="audit")


def test_ip_detected_and_redacted():
    """IP 被检出且脱敏，末段遮罩、原文不残留。"""
    res = _guard().check("服务器IP是 192.168.1.23 端口8080")
    rules = {f["rule"] for f in res["findings"]}
    assert "ip_address" in rules
    assert res["redacted"] is not None
    assert "192.168.1.23" not in res["redacted"]      # 原文不残留
    assert "192.168.1.***" in res["redacted"]          # 末段已遮罩


def test_wechat_detected_and_redacted():
    """微信号 wxid_xxx 被检出且脱敏，前缀与末 4 位保留、原文不残留。"""
    res = _guard().check("微信号 wxid_abc123def456 联系我")
    rules = {f["rule"] for f in res["findings"]}
    assert "wechat_id" in rules
    assert res["redacted"] is not None
    assert "wxid_abc123def456" not in res["redacted"]   # 原文不残留
    assert "wxid_" in res["redacted"]                   # 前缀保留可识别


def test_redacted_has_no_sensitive_plaintext():
    """同一段含 IP + 微信号，redacted 不得残留任一原文（覆盖两种缺失规则）。"""
    res = _guard().check("IP 10.0.0.5 微信号 wxid_secret9988 备注")
    assert res["redacted"] is not None
    assert "10.0.0.5" not in res["redacted"]
    assert "wxid_secret9988" not in res["redacted"]
