"""FabricHub chat/skill_discover 单元测试——mock route 不依赖真实 API key。

FabricHub(adapters=()) 空适配器构造轻量，所有测试秒级完成。
"""

from unittest.mock import MagicMock, patch

import pytest

from kernel.plugins.fabric_hub import FabricHub
from core.fabric.adapter import InvokeResult


@pytest.fixture(autouse=True)
def _isolate_real_llm():
    """chat() 真实逻辑优先走真实 LLM 直连(zhipu/ollama)，本测试只验证 chat
    对 FabricHub.route 返回的处理，必须隔离真实网络调用，强制落到 mock 的
    self.route。否则真实 LLM 回复(沙箱偶发可用)会绕过 mock、断言失真。
    """
    with patch("kernel.plugins.fabric_hub.zhipu_chat", return_value=None), \
         patch("kernel.plugins.fabric_hub.ollama_chat", return_value=None), \
         patch("kernel.plugins.fabric_hub.ollama_available", return_value=False):
        yield


@pytest.fixture(scope="module")
def hub():
    """模块级 fixture：所有测试复用一个空适配器 FabricHub。"""
    return FabricHub(adapters=())


def test_chat_with_mocked_llm_success(hub):
    """chat() 在 route 返回成功 InvokeResult 时返回文本。"""
    hub.route = MagicMock(return_value=InvokeResult(
        ok=True, engine_id="litellm", data={"content": "你好，我是 AOS"},
    ))
    res = hub.chat("你好")
    assert res["ok"] is True
    assert res["response"] == "你好，我是 AOS"
    assert res["engine"] == "litellm"
    assert res["session_id"] == "default"


def test_chat_with_text_field(hub):
    """chat() 兼容 data 中含 text 字段（非 content）的输出形状。"""
    hub.route = MagicMock(return_value=InvokeResult(
        ok=True, engine_id="agns", data={"text": "来自 agnes 的回复"},
    ))
    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "来自 agnes 的回复"


def test_chat_with_choices_format(hub):
    """chat() 兼容 OpenAI choices 格式输出。"""
    hub.route = MagicMock(return_value=InvokeResult(
        ok=True, engine_id="openai",
        data={"choices": [{"message": {"content": "OpenAI 回复"}}]},
    ))
    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "OpenAI 回复"


def test_chat_failure_returns_error(hub):
    """route 失败时 chat() 诚实返回错误，不伪造输出。"""
    hub.route = MagicMock(return_value=InvokeResult(
        ok=False, error="LLM key missing", engine_id="litellm",
    ))
    res = hub.chat("hi")
    assert res["ok"] is False
    assert "FabricHub chat failed" in res["response"]
    assert res["engine"] == "litellm"


def test_chat_exception_graceful(hub):
    """route 抛异常时 chat() 不崩，返回错误。"""
    hub.route = MagicMock(side_effect=RuntimeError("网络超时"))
    res = hub.chat("hi")
    assert res["ok"] is False
    assert "chat error" in res["response"].lower()


def test_chat_with_system_prompt(hub):
    """带有 system_prompt 的 chat 调用仍正常工作。"""
    hub.route = MagicMock(return_value=InvokeResult(
        ok=True, engine_id="litellm", data={"content": "ok"},
    ))
    res = hub.chat("问个问题", system_prompt="你是一个助手")
    assert res["ok"] is True
    call_args = hub.route.call_args
    payload = call_args[0][1]
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"] == "你是一个助手"


def test_chat_non_invoke_result_raw_string(hub):
    """route 返回非 InvokeResult（如原始字符串）时 chat() 仍工作。"""
    hub.route = MagicMock(return_value="原始字符串回复")
    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "原始字符串回复"


def test_chat_empty_response_placeholder(hub):
    """LLM 返回空内容时给占位符不忘空返回。"""
    hub.route = MagicMock(return_value=InvokeResult(
        ok=True, engine_id="x", data={"content": ""},
    ))
    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "[no response]"


def test_skill_discover_with_capability(hub):
    """skill_discover 按能力查询返回正确技能列表。"""
    res = hub.skill_discover("web.search")
    assert res["total"] >= 1
    names = [s["name"] for s in res["skills"]]
    assert "DuckDuckGo Search" in names


def test_skill_discover_no_capability_returns_all(hub):
    """不传 capability 时 skill_discover 返回全部 31 技能。"""
    res = hub.skill_discover()
    assert res["total"] >= 25
    assert len(res["skills"]) >= 25


def test_skill_discover_nonexistent(hub):
    """不存在的 capability 返回空。"""
    res = hub.skill_discover("nope.nothing.here")
    assert res["total"] == 0
    assert res["skills"] == []
