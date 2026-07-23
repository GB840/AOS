"""LLM 提供者模块。

为单创OS提供统一的大语言模型调用接口，支持：
- MockLLM：模拟 LLM，用于无网络/无 key 测试
- LocalLLM：本地模型（预留接口，可接 llama.cpp / transformers / ollama）
- RemoteLLM：远程 API（OpenAI / 阿里云 / DeepSeek 等）
"""
from .langchain_adapter import LangChainLLMAdapter
from .provider import LLMProvider, LLMResponse, get_default_provider

__all__ = ["LLMProvider", "LLMResponse", "get_default_provider", "LangChainLLMAdapter"]
