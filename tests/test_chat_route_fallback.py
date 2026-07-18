"""`/api/chat` 后端链兜底集成测试（单基座第一性 + brain.py 退场）。

不启动完整 app（避免 ~2min brain 构造），直接调用 chat 异步处理器，
用 mock 替换 _get_fabric_hub / app.state.bridge / brain 三大后端，
验证：默认 fabric→kernel 链、brain.py opt-in 兜底、全部失败诚实 503、
以及 brain 路径打废弃标记（理念6/9 不伪造）。
"""
import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.main import chat, ChatRequest
import src.api.main as main_mod
from api.chat_routing import BRAIN_DEPRECATION_MSG


class _InvokeResult:
    def __init__(self, data, ok=True):
        self.data = data
        self.ok = ok


class _MockHub:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
    def chat(self, message, session_id=""):
        if self.exc is not None:
            raise self.exc
        return self.result


class _MockBridge:
    def __init__(self, content=None, exc=None):
        self._content = content
        self.exc = exc
        self.routes = []
        self.requests = 0
    def record_chat_request(self):
        self.requests += 1
    def record_chat_route(self, route):
        self.routes.append(route)
    def chat(self, prompt, session_id=""):
        if self.exc is not None:
            raise self.exc
        return _InvokeResult({"content": self._content}, ok=True)


class _Meta:
    def route_intent(self, intent, user_id, trace_id):
        return {"layer": "L1", "complexity": "low", "workflow_id": None, "priority": 1}


class _MockBrain:
    def __init__(self, result=None, exc=None):
        self._result = result
        self.exc = exc
        self.meta_orchestrator = _Meta()
        class _Tracer:
            enabled = False
        self.langfuse_tracer = _Tracer()
    def chat(self, message, session_id=None, meta_decision=None):
        if self.exc is not None:
            raise self.exc
        return self._result


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("AOS_CHAT_BACKEND", "AOS_BRAIN_FALLBACK"):
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture
def wired(monkeypatch):
    """把三大后端替换成可控 mock，并返回它们供断言。"""
    hub = _MockHub()
    bridge = _MockBridge()
    brain = _MockBrain()
    main_mod.app.state.bridge = bridge

    async def _fake_get_hub():
        return hub

    monkeypatch.setattr(main_mod, "_get_fabric_hub", _fake_get_hub)
    monkeypatch.setattr(main_mod, "brain", brain)
    yield {"hub": hub, "bridge": bridge, "brain": brain}


def _run(req: ChatRequest):
    return asyncio.run(chat(req))


def test_fabric_success_default(wired):
    wired["hub"].result = {"response": "fabric-ans", "engine": "litellm", "ok": True}
    res = _run(ChatRequest(message="hi"))
    assert res["response"] == "fabric-ans"
    assert res["route"].startswith("fabric/")
    assert wired["bridge"].routes == ["fabric"]


def test_fabric_fail_kernel_success(wired):
    wired["hub"].exc = RuntimeError("fabric down")
    wired["bridge"]._content = "kernel-ans"
    res = _run(ChatRequest(message="hi"))
    assert res["response"] == "kernel-ans"
    assert res["route"] == "kernel/v1"
    assert wired["bridge"].routes == ["fabric", "kernel"]


def test_fabric_kernel_fail_brain_success(wired, monkeypatch, caplog):
    monkeypatch.setenv("AOS_BRAIN_FALLBACK", "1")
    wired["hub"].exc = RuntimeError("fabric down")
    wired["bridge"].exc = RuntimeError("kernel down")
    wired["brain"]._result = {"response": "brain-ans", "session_id": "s", "ok": True}
    with caplog.at_level(logging.WARNING, logger="src.api.main"):
        res = _run(ChatRequest(message="hi"))
    assert res["response"] == "brain-ans"
    # legacy 路径给结果加了 meta 分层字段
    assert res["meta"]["layer"] == "L1"
    assert wired["bridge"].routes == ["fabric", "kernel", "brain"]
    assert BRAIN_DEPRECATION_MSG in caplog.text


def test_all_fail_no_brain_returns_503(wired, caplog):
    wired["hub"].exc = RuntimeError("fabric down")
    wired["bridge"].exc = RuntimeError("kernel down")
    with caplog.at_level(logging.ERROR, logger="src.api.main"):
        with pytest.raises(HTTPException) as exc:
            _run(ChatRequest(message="hi"))
    assert exc.value.status_code == 503
    assert "all backends failed" in exc.value.detail
    # brain 不在默认链中，不得被调用
    assert wired["bridge"].routes == ["fabric", "kernel"]


def test_explicit_brain_backend_is_deprecated(wired, monkeypatch, caplog):
    monkeypatch.setenv("AOS_CHAT_BACKEND", "brain")
    wired["brain"]._result = {"response": "legacy-ans", "session_id": "s", "ok": True}
    with caplog.at_level(logging.WARNING, logger="src.api.main"):
        res = _run(ChatRequest(message="hi"))
    assert res["response"] == "legacy-ans"
    assert wired["bridge"].routes == ["brain"]
    assert BRAIN_DEPRECATION_MSG in caplog.text


def test_explicit_kernel_backend(wired, monkeypatch):
    monkeypatch.setenv("AOS_CHAT_BACKEND", "kernel")
    wired["bridge"]._content = "kernel-only"
    res = _run(ChatRequest(message="hi"))
    assert res["response"] == "kernel-only"
    assert res["route"] == "kernel/v1"
    assert wired["bridge"].routes == ["kernel"]


def test_brain_fallback_never_called_by_default(wired):
    # 默认链 [fabric, kernel]；fabric 成功时不触发 kernel/brain
    wired["hub"].result = {"response": "fabric-ans", "engine": "litellm", "ok": True}
    _run(ChatRequest(message="hi"))
    assert wired["bridge"].routes == ["fabric"]
    assert wired["bridge"]._content is None  # kernel.chat 未被调用
