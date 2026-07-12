"""LiteLLMAdapter 单测：聚焦 #37 修复——

1) 上游串味：当 context（上一步整个输出字典）带着图像/视频模型名
   (如 agnes-image-2.1-flash) 流进 inference.llm 步时，不能拿它当文本模型，
   否则 litellm 报 "LLM Provider NOT provided"。必须退回文本默认模型。
2) content 当 prompt：编排把上一步输出的 content 透传，但 litellm 认的是
   prompt/messages，需把 content 转成 user message，否则拿到空消息。
"""
from __future__ import annotations

from core.fabric.adapters import litellm_adapter as m
from core.fabric.adapter import InvokeRequest


def _kw(payload):
    return m._build_kwargs(InvokeRequest(capability="inference.llm", payload=payload))


def test_poisoned_image_model_falls_back_to_text():
    # 模拟 media.image 步输出透传进 inference.llm 步
    kw = _kw({"model": "agnes-image-2.1-flash", "content": "晴 26度", "images": []})
    # 图像模型名绝不能被拿来做文本补全（否则 litellm 报 Provider NOT provided）
    assert "image" not in kw["model"] and "video" not in kw["model"]
    # 退回文本默认模型（zhipu/ 前缀在 zhipu 分支被剥为裸模型名）
    assert kw["model"] == "glm-4-flash"
    assert kw["messages"] == [{"role": "user", "content": "晴 26度"}]


def test_content_used_as_prompt_when_no_prompt_key():
    kw = _kw({"content": "上一步的搜索结果摘要"})
    assert kw["messages"] == [{"role": "user", "content": "上一步的搜索结果摘要"}]


def test_explicit_prompt_preserved():
    kw = _kw({"prompt": "直接提问", "model": "zhipu/glm-4-flash"})
    # zhipu/ 前缀在 zhipu 分支被剥为裸模型名
    assert kw["model"] == "glm-4-flash"
    assert kw["messages"] == [{"role": "user", "content": "直接提问"}]


def test_explicit_messages_preserved():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    kw = _kw({"messages": msgs})
    assert kw["messages"] == msgs
