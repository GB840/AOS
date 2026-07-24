"""Regression tests for the v1.0 kernel security fixes (2026-07-12).

Locks in three real fixes that were verified against the running system:
  1. Permission defaults to DENY (zero-trust); previously defaulted to grant=True.
  2. MCP skill bus now seeds its whitelist from the protocol's real default
     tools, so the kernel exposes usable skills instead of 0 (the old
     whitelist named tools that don't exist -> silent deny-all).
  3. grant_permission() allows runtime, additive authorization so the
     production chat path (v5_bridge.chat) can opt a session agent into
     "receive" without flipping the global default back to permissive.

These tests import only kernel modules (no cognee), so they gate cleanly.
"""

from __future__ import annotations

from kernel.types import AgentSpec, Message
from kernel.wiring import build_default_kernel


class TestPermissionDefaultDeny:
    def test_build_default_kernel_is_deny_by_default(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        assert k.check_permission("anyone", "receive") is False
        assert k.check_permission("anyone", "anything") is False

    def test_explicit_grant_overrides_default_deny(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        k.grant_permission("agent-x", "receive", True)
        assert k.check_permission("agent-x", "receive") is True
        # unrelated action still denied
        assert k.check_permission("agent-x", "send") is False

    def test_grant_permission_is_additive(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        k.grant_permission("a1", "receive", True)
        k.grant_permission("a2", "receive", True)
        assert k.check_permission("a1", "receive") is True
        assert k.check_permission("a2", "receive") is True


class TestSkillBusSeeding:
    def test_kernel_exposes_real_protocol_tools(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        ids = sorted(s.skill_id for s in k._skill_bus.discover_skills())
        # Protocol registers these 6 default tools; the security gateway must
        # now surface them instead of 0.
        assert "chat" in ids
        assert "get_status" in ids
        assert "search_memory" in ids
        assert len(ids) >= 6

    def test_whitelisted_tool_is_callable(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        r = k._skill_bus.call_skill("get_status", {})
        assert r.ok is True

    def test_non_whitelisted_tool_is_blocked(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        r = k._skill_bus.call_skill("definitely_not_registered", {})
        assert r.ok is False
        assert "白名单" in r.error


class TestGrantEnablesSendMessage:
    def test_send_message_requires_receive_grant(self):
        k = build_default_kernel(isolate_heavy=False, inject_brain=False)
        k.register_agent(AgentSpec(agent_id="t1", name="T", engine="litellm"))

        # No grant -> denied
        denied = k.send_message(Message(sender="u", recipient="t1",
                                        payload={"prompt": "hi"}))
        assert denied.ok is False
        assert "permission denied" in denied.error

        # Grant -> allowed (kernel passes the permission gate; routing to a
        # runtime is a separate concern we don't assert here).
        k.grant_permission("t1", "receive", True)
        allowed = k.send_message(Message(sender="u", recipient="t1",
                                         payload={"prompt": "hi"}))
        assert allowed.error is None or "permission denied" not in allowed.error
