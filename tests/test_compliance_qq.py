"""测试合规层 QQ 号检测（直接测真实 ContentGuard，不重复内联正则）。

QQ 号正则语义：5–11 位、首位非 0、前后不紧贴其他数字的独立数字串。
注意：这是宽松启发式，10 位订单号 / 11 位手机号也会命中——属正常重叠，
测试不对此断言"不命中"，只验证：真实 QQ 能检出、非法边界正确拒绝。
"""
import re

from src.kernel.compliance import ContentGuard


def test_qq_regex_valid_range():
    """5–11 位合法 QQ 应被匹配。"""
    pat = ContentGuard.SENSITIVE_PATTERNS["qq_number"]
    assert pat.findall("12345") == ["12345"]                      # 5 位
    assert pat.findall("123456789") == ["123456789"]              # 9 位
    assert pat.findall("12345678901") == ["12345678901"]          # 11 位（上限）


def test_qq_regex_invalid_bounds():
    """非法 QQ 应被正确拒绝。"""
    pat = ContentGuard.SENSITIVE_PATTERNS["qq_number"]
    assert pat.findall("0123456789") == []    # 首位为 0
    assert pat.findall("1234") == []          # 不足 5 位
    # 12 位及以上整串都是数字：尾部总有数字跟随，(?![0-9]) 永不满足
    assert pat.findall("123456789012") == []
    assert pat.findall("1234567890123") == []


def test_qq_regex_no_adjacent_digits():
    """数字段前后紧贴其他数字时不匹配（避免从长串里误切）。"""
    pat = ContentGuard.SENSITIVE_PATTERNS["qq_number"]
    # UUID 由 16 进制段组成，含字母、且数字段均 >11 位或 <5 位
    assert pat.findall("UUID：550e8400-e29b-41d4-a716-446655440000") == []
    # 独立 5–11 位数字仍应匹配
    assert pat.findall("QQ：123456789") == ["123456789"]
    # 年份 + QQ 相邻：只切出独立那段
    assert pat.findall("2023年123456789年") == ["123456789"]


def test_compliance_layer_flags_qq():
    """真实合规层 check() 能检出 QQ 号并标注 rule=qq_number。"""
    guard = ContentGuard(mode="audit")
    res = guard.check("加我QQ：123456789 详聊")
    rules = {f["rule"] for f in res["findings"]}
    assert "qq_number" in rules


def test_compliance_layer_detection_triggers_redaction_pipeline():
    """含 QQ 的内容会触发脱敏管线（redacted 非空）。

    注：当前 _redact 替换表只覆盖 phone/id_card/bank_card/email/api_key，
    QQ 号虽被"检测"但未单独遮罩——这是现有实现的不一致点（已反馈待修），
    本测试只验证"检测到敏感信息 → redacted 字段被填充"的管线连通性。
    """
    guard = ContentGuard(mode="audit")
    res = guard.check("联系方式 QQ 123456789")
    assert res["redacted"] is not None          # 检测到敏感信息，脱敏管线已触发
    rules = {f["rule"] for f in res["findings"]}
    assert "qq_number" in rules


def test_compliance_layer_redacts_phone():
    """脱敏管线对 phone_cn 这类已配置类型真实生效（验证 _redact 通路）。"""
    guard = ContentGuard(mode="audit")
    res = guard.check("联系我手机号13800138000")
    assert res["redacted"] is not None
    assert "13800138000" not in res["redacted"]  # 手机号已被遮盖
