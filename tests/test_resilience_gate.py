"""抗复合失败：诚实闸门单元测试（任务271 / 白皮书 3.2）。

核心命题：复合失败的根源是『假成功累积』——朴素串联只看步骤布尔 ok，
把空转 / 伪造的成功当真，错误逐层累积导致雪崩。AOS 的每步真实闸门
（real_metrics.is_real）拦截假成功；失败明确判未完成，绝不谎报完成。
"""
from kernel import autopilot as ap


def test_fake_success_is_not_judged_complete():
    # 所有步 ok=True 但 real_metrics.is_real=False（空转 / 敷衍 / 伪造）
    # 朴素串联会把这当"全成功"继续 → 错误累积雪崩；AOS 闸门必须拦截。
    data = {"failed_steps": 0}
    trace = [
        {"capability": "web.search", "ok": True, "real_metrics": {"is_real": False}},
        {"capability": "action.code_exec", "ok": True, "real_metrics": {"is_real": False}},
    ]
    verdict = ap._verdict("生成一份市场分析报告", data, trace, {})
    assert "未完成" in verdict["status"], "假成功必须被判未完成，否则会雪崩"
    assert verdict["status"] != "完成 ✅"


def test_real_failure_requires_reflection():
    r = {"verdict": {"status": "未完成 ❌"}}
    assert ap._needs_reflection(r) is True


def test_genuine_completion_stops_reflection():
    r = {"verdict": {"status": "完成 ✅"}}
    assert ap._needs_reflection(r) is False


def test_partial_with_real_deliverable_stops_reflection():
    # 部分步骤失败但产物已真实落盘 → 视为达成，停止反思（不空转）
    r = {"verdict": {"status": "部分完成 ⚠️（有步骤失败，但产物已真实落盘）"}}
    assert ap._needs_reflection(r) is False
