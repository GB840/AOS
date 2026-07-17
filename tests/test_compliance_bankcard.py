"""测试银行卡号正则精确匹配（V4修复验证）"""
import pytest
from kernel.compliance import ContentGuard


def test_bank_card_exact_match():
    """测试银行卡号精确匹配，前后不应有其他数字"""
    engine = ContentGuard()

    # 应该匹配的有效银行卡号
    valid_cases = [
        "1234567890123456",      # 16位
        "12345678901234567",     # 17位
        "123456789012345678",    # 18位
        "1234567890123456789",   # 19位
        "6222021234567890123",   # 真实银行卡号格式
    ]

    for case in valid_cases:
        result = engine.check(case)
        assert result["redacted"] is not None, f"应该匹配银行卡号: {case}"
        assert "****" in result["redacted"]

    # 不应该匹配的无效案例（前后有其他数字）
    invalid_cases = [
        "abc1234567890123456def",    # 前后有字母
        "123-456-789-012-345-6",     # 包含连字符
    ]

    for case in invalid_cases:
        result = engine.check(case)
        assert result["redacted"] is None, f"不应该匹配: {case}"


def test_bank_card_in_text():
    """测试银行卡号在文本中的匹配"""
    engine = ContentGuard()

    # 应该匹配：银行卡号前后是空格或标点
    text1 = "我的银行卡号是 6222021234567890123 请保密"
    result1 = engine.check(text1)
    assert result1["redacted"] is not None
    assert "****" in result1["redacted"]
    assert "6222021234567890123" not in result1["redacted"]

    # 不应该匹配：银行卡号前后是其他数字
    # 注意：20位数字会被id_card正则匹配，所以这里测试bank_card正则不会匹配
    text2 = "订单号12345678901234567890包含20位数字"
    result2 = engine.check(text2)
    # 验证是id_card匹配的，不是bank_card
    findings = result2.get("findings", [])
    bank_card_found = any(f.get("rule") == "bank_card" for f in findings)
    assert not bank_card_found, "bank_card正则不应该匹配20位数字"