"""将单创OS的 LLMProvider 适配为 CrewAI BaseLLM。

用于与 CrewAI / LangChain 生态集成，
使自研或本地模型可以无缝接入这些框架。

CrewAI 1.15+ 对 Agent.llm 字段做 Pydantic 校验，要求实例为
``crewai.llms.base_llm.BaseLLM`` 子类并实现 ``call`` 方法。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from crewai.llms.base_llm import BaseLLM as CrewAIBaseLLM
from pydantic import Field

from .provider import LLMProvider


class LangChainLLMAdapter(CrewAIBaseLLM):
    """单创OS LLMProvider → CrewAI BaseLLM 适配器。"""

    # 使用 llm_provider 而不是 provider，避免与 CrewAI BaseLLM 的
    # provider: str = "openai" 字段冲突。
    llm_provider: LLMProvider = Field(..., description="底层 LLM 提供者")
    model: str = Field(default="danchuang-llm")
    provider: str = Field(default="danchuang", description="CrewAI 内部 provider 标识")

    def call(
        self,
        messages: str | List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        callbacks: List[Any] | None = None,
        available_functions: Dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: Any | None = None,
    ) -> str:
        """实现 CrewAI BaseLLM 的调用接口。

        CrewAI 调用时传入的是消息列表（含 system / user / assistant）。
        这里直接转交给底层 LLMProvider，返回文本结果。
        """
        formatted_messages: List[Dict[str, str]]
        if isinstance(messages, str):
            formatted_messages = [{"role": "user", "content": messages}]
        else:
            formatted_messages = [
                {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
                for m in messages
            ]

        response = self.llm_provider.invoke(
            formatted_messages,
            temperature=self.temperature,
            max_tokens=int(self.max_tokens) if self.max_tokens is not None else 2048,
        )
        return response.content

    async def acall(
        self,
        messages: str | List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
        callbacks: List[Any] | None = None,
        available_functions: Dict[str, Any] | None = None,
        from_task: Any | None = None,
        from_agent: Any | None = None,
        response_model: Any | None = None,
    ) -> str:
        """同步包装为异步。"""
        return self.call(
            messages,
            tools=tools,
            callbacks=callbacks,
            available_functions=available_functions,
            from_task=from_task,
            from_agent=from_agent,
            response_model=response_model,
        )
