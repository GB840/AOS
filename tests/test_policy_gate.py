"""验证策略引擎网关（双轨债 ③）：PolicyEngine 真正接入派发边界，且有约束力。

- 可信 system 体（autopilot / workflow_runner 派发）允许执行命令（r010）
- 不可信体执行 system:shell 被 r003 拒绝
- 默认审计模式只记录不阻断（避免误伤自主体合法 code_exec）
- AOS_POLICY_ENFORCE=1 时命中 deny 规则即真阻断
"""
import pytest

from kernel.compliance import (
    get_policy_engine,
    check_capability,
    check_action,
)


def test_system_actor_code_exec_allowed():
    v = check_capability("action.code_exec", actor="system")
    assert v["allowed"] is True


def test_untrusted_actor_code_exec_denied():
    v = check_capability("action.code_exec", actor="some_agent")
    assert v["allowed"] is False
    assert v["matched_rule"] == "r003"


def test_web_search_allowed():
    assert check_capability("web.search", actor="system")["allowed"] is True


def test_get_policy_engine_singleton():
    assert get_policy_engine() is get_policy_engine()


def test_enforce_blocks_untrusted():
    v = check_action("system:shell", actor="some_agent", enforce=True)
    assert v["allowed"] is False


def test_autopilot_route_respects_policy(monkeypatch):
    try:
        from kernel import autopilot
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"autopilot 不可导入: {e}")

    # 强制硬阻断模式 + 让策略网关返回拒绝，验证 _route 在派发前短返
    monkeypatch.setattr(autopilot, "policy_enforce_enabled", lambda: True)
    monkeypatch.setattr(
        autopilot, "check_capability",
        lambda cap, actor="system", resource="", enforce=None: {
            "allowed": False, "matched_rule": "r003",
            "reason": "deny", "rate_limited": False,
        },
    )
    res = autopilot._route("action.code_exec", {"instruction": "echo hi"})
    assert res.ok is False
    assert "策略拒绝" in res.error
