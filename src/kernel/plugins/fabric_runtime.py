"""插件：把现有 fabric.BaseAgentAdapter（四个真实 OSS 引擎）登记为 AgentRuntime。

这是 v1.0「物种思维」的接线层：内核只认 AgentRuntime(ABC)，本文件把已有的
BaseAgentAdapter 实例薄封装成 AgentRuntime，从而四个真实 OSS（OpenClaw /
Hermes / DeerFlow / AG2）无需改写即可作为内核插件挂入。内核零依赖，本文件
才允许 import 具体实现（core.fabric）。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ..interfaces import AgentRuntime
from ..types import AgentInstance, AgentSpec, Response

# 延迟导入具体实现，避免内核包被具体依赖污染
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest
from core.fabric.capability import Capability


class FabricAgentRuntime(AgentRuntime):
    """薄封装：一个 BaseAgentAdapter 实例 = 一个 AgentRuntime 插件。

    v1.0 用 create_agent/run_agent 词汇；BaseAgentAdapter 用
    engine_id/advertise_capabilities/invoke/health。本类把 invoke 映射为
    run_agent，把 advertise 映射为能力声明 —— 不改动四个 OSS 适配器的代码。
    """

    def __init__(self, adapter: BaseAgentAdapter) -> None:
        self._adapter = adapter

    # ---- AgentRuntime 接口 ----
    def create_agent(self, spec: AgentSpec) -> AgentInstance:
        # 引擎插件是无状态的调用翻译器；create_agent 仅声明一个实例。
        return AgentInstance(agent_id=spec.agent_id, spec=spec)

    def run_agent(self, instance: AgentInstance, task: Any) -> Response:
        cap = _first_cap(self._adapter)
        payload = {"prompt": _extract_prompt(task)}
        model = _extract_model(task)
        if model:  # 空字符串时省略，让网关回退到默认模型
            payload["model"] = model
        req = InvokeRequest(capability=cap, payload=payload)
        res = self._adapter.invoke(req)
        if res.ok:
            return Response(ok=True, data=res.data or {})
        return Response(ok=False, error=res.error or "invoke failed")

    def stream_run(self, instance: AgentInstance, task: Any) -> AsyncIterator[Any]:
        # 现有适配器未实现流式；yield 单次完整结果（薄缝，未来可接协议原生流）。
        yield self.run_agent(instance, task)

    def get_status(self, instance_id: str) -> str:
        return "healthy" if self._adapter.health() else "unhealthy"

    # ---- 兼容 BaseAgentAdapter 底层契约（供接线层读取） ----
    @property
    def engine_id(self) -> str:
        return self._adapter.engine_id

    def advertise_capabilities(self) -> list:
        return self._adapter.advertise_capabilities()


def _first_cap(adapter: BaseAgentAdapter):
    caps = adapter.advertise_capabilities()
    return caps[0] if caps else Capability.LLM_GATEWAY


def _extract_prompt(task: Any) -> str:
    if isinstance(task, dict):
        return task.get("prompt") or task.get("message") or task.get("content") or ""
    return str(task)


def _extract_model(task: Any) -> str:
    if isinstance(task, dict):
        return task.get("model", "")
    return ""
