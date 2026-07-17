"""FabricHub chat/skill_discover 单元测试——mock route 不依赖真实 API key。

FabricHub(adapters=()) 空适配器构造轻量，所有测试秒级完成。
"""

from unittest.mock import MagicMock, patch

from kernel.plugins.fabric_hub import FabricHub
from core.fabric.adapter import InvokeResult


def _make_hub():
    """构造空适配器 FabricHub（无真实引擎注册），秒级完成。"""
    return FabricHub(adapters=())


def test_chat_with_mocked_llm_success():
    """chat() 在 route 返回成功 InvokeResult 时返回文本。"""
    hub = _make_hub()
    mock_result = InvokeResult(
        ok=True,
        engine_id="litellm",
        data={"content": "你好，我是 AOS"},
    )
    hub.route = MagicMock(return_value=mock_result)

    res = hub.chat("你好")
    assert res["ok"] is True
    assert res["response"] == "你好，我是 AOS"
    assert res["engine"] == "litellm"
    assert res["session_id"] == "default"


def test_chat_with_text_field():
    """chat() 兼容 data 中含 text 字段（非 content）的输出形状。"""
    hub = _make_hub()
    mock_result = InvokeResult(
        ok=True,
        engine_id="agns",
        data={"text": "来自 agnes 的回复"},
    )
    hub.route = MagicMock(return_value=mock_result)

    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "来自 agnes 的回复"


def test_chat_with_choices_format():
    """chat() 兼容 OpenAI choices 格式输出。"""
    hub = _make_hub()
    mock_result = InvokeResult(
        ok=True,
        engine_id="openai",
        data={"choices": [{"message": {"content": "OpenAI 回复"}}]},
    )
    hub.route = MagicMock(return_value=mock_result)

    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "OpenAI 回复"


def test_chat_failure_returns_error():
    """route 失败时 chat() 诚实返回错误，不伪造输出。"""
    hub = _make_hub()
    mock_result = InvokeResult(ok=False, error="LLM key missing", engine_id="litellm")
    hub.route = MagicMock(return_value=mock_result)

    res = hub.chat("hi")
    assert res["ok"] is False
    assert "FabricHub chat failed" in res["response"]
    assert res["engine"] == "litellm"


def test_chat_exception_graceful():
    """route 抛异常时 chat() 不崩，返回错误。"""
    hub = _make_hub()
    hub.route = MagicMock(side_effect=RuntimeError("网络超时"))

    res = hub.chat("hi")
    assert res["ok"] is False
    assert "chat error" in res["response"].lower()


def test_chat_with_system_prompt():
    """带有 system_prompt 的 chat 调用仍正常工作。"""
    hub = _make_hub()
    mock_result = InvokeResult(ok=True, engine_id="litellm", data={"content": "ok"})
    hub.route = MagicMock(return_value=mock_result)

    res = hub.chat("问个问题", system_prompt="你是一个助手")
    assert res["ok"] is True
    # 验证 route 被调用且 messages 包含 system prompt
    call_args = hub.route.call_args
    payload = call_args[0][1]  # 第二个参数是 payload dict
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"] == "你是一个助手"


def test_chat_non_invoke_result_raw_string():
    """route 返回非 InvokeResult（如原始字符串）时 chat() 仍工作。"""
    hub = _make_hub()
    hub.route = MagicMock(return_value="原始字符串回复")

    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "原始字符串回复"


def test_chat_empty_response_placeholder():
    """LLM 返回空内容时给占位符不忘空返回。"""
    hub = _make_hub()
    mock_result = InvokeResult(ok=True, engine_id="x", data={"content": ""})
    hub.route = MagicMock(return_value=mock_result)

    res = hub.chat("hi")
    assert res["ok"] is True
    assert res["response"] == "[no response]"


def test_skill_discover_with_capability():
    """skill_discover 按能力查询返回正确技能列表。"""
    hub = _make_hub()
    res = hub.skill_discover("web.search")
    assert res["total"] >= 1
    names = [s["name"] for s in res["skills"]]
    assert "DuckDuckGo Search" in names


def test_skill_discover_no_capability_returns_all():
    """不传 capability 时 skill_discover 返回全部 31 技能。"""
    hub = _make_hub()
    res = hub.skill_discover()
    assert res["total"] >= 25
    assert len(res["skills"]) >= 25


def test_skill_discover_nonexistent():
    """不存在的 capability 返回空。"""
    hub = _make_hub()
    res = hub.skill_discover("nope.nothing.here")
    assert res["total"] == 0
    assert res["skills"] == []


def test_health_report_with_empty_adapters():
    """空适配器时 health_report 不崩，返回概览。"""
    hub = _make_hub()
    report = hub.health_report()
    assert isinstance(report, dict)
    assert "adapters" in report
    assert report["total"] == 0
