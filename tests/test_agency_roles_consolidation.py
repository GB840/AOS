"""Layer 2: agency_roles 收口薄壳的单元测试。

关键约束（来自沙箱安全分析）：
- 绝不调用 legacy 路径的 ``get_brain()``（会 import cognee → 批量删除守卫）。
- 只验证：flag 解析、runtime 选择器、kernel 路径经 ``get_bridge().call_skill/chat`` 正确透传。
"""

import pytest

from skills.agency_roles import (
    get_agency_runtime,
    is_kernel_consolidation_enabled,
    _KernelRuntime,
    _LegacyRuntime,
)


@pytest.fixture(autouse=True)
def _clear_flag():
    import os
    os.environ.pop("AOS_USE_KERNEL_FOR_ROLES", None)
    yield
    os.environ.pop("AOS_USE_KERNEL_FOR_ROLES", None)


def test_flag_default_off():
    assert is_kernel_consolidation_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_flag_truthy(monkeypatch, val):
    monkeypatch.setenv("AOS_USE_KERNEL_FOR_ROLES", val)
    assert is_kernel_consolidation_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "", "2", "disabled"])
def test_flag_falsy(monkeypatch, val):
    monkeypatch.setenv("AOS_USE_KERNEL_FOR_ROLES", val)
    assert is_kernel_consolidation_enabled() is False


def test_selector_default_legacy():
    rt = get_agency_runtime("前端开发者")
    assert isinstance(rt, _LegacyRuntime)
    assert rt.backend == "legacy_brain"
    assert rt.agent_id == "agency:前端开发者"


def test_selector_kernel_on(monkeypatch):
    monkeypatch.setenv("AOS_USE_KERNEL_FOR_ROLES", "1")
    rt = get_agency_runtime("前端开发者")
    assert isinstance(rt, _KernelRuntime)
    assert rt.backend == "kernel"


def test_kernel_runtime_routes_call_skill(monkeypatch):
    monkeypatch.setenv("AOS_USE_KERNEL_FOR_ROLES", "1")
    captured = {}

    class StubBridge:
        def call_skill(self, skill_id, params, caller="api"):
            captured["skill_id"] = skill_id
            captured["params"] = params
            captured["caller"] = caller
            return {"ok": True, "data": "stub"}

        def chat(self, prompt, session_id="", engine="litellm", caller="api"):
            captured["chat_prompt"] = prompt
            captured["chat_caller"] = caller
            return {"ok": True, "data": "chat-stub"}

    import kernel.v5_bridge as vb
    monkeypatch.setattr(vb, "get_bridge", lambda: StubBridge())

    rt = get_agency_runtime("前端开发者")
    res = rt.call_skill("some_skill", {"x": 1})
    assert res == {"ok": True, "data": "stub"}
    assert captured["skill_id"] == "some_skill"
    assert captured["caller"] == "agency:前端开发者"

    rt.chat("hello")
    assert captured["chat_prompt"] == "hello"
    assert captured["chat_caller"] == "agency:前端开发者"
