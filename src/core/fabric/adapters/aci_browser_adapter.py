"""Real browser-use adapter for the AOS open fabric - the ACTION / ACI PLANE.

browser-use (browser-use, MIT - github.com/browser-use/browser-use) lets an
agent drive a real web browser through natural language: click, fill,
scroll, read, submit. This is the "Agent Computer Interface" (ACI) plane -
the agents need actual HANDS on the machine/web, not just text mouths/ears.
OpenClaw gives AOS the chat channels; browser-use gives AOS the hands.

Thin adapter: translates AOS `action.aci` into a real `browser_use.Agent`
run. AOS does NOT build its own browser automation - it delegates to the
real OSS.
"""
from __future__ import annotations

from typing import Any

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability


def _import_browser_use():
    """Lazy import so the adapter is valid code even before `pip install`."""
    from browser_use import Agent  # type: ignore
    return Agent


def _safe_async_run(coro):
    """安全地在同步上下文中运行协程：如果已有事件循环在运行则创建新循环在线程中执行。"""
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 已在事件循环中（如 asyncio.to_thread），在新线程中创建独立循环
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class BrowserUseAdapter(BaseAgentAdapter):
    """Thin wrapper over the real browser-use agent (the "hands" plane)."""

    def __init__(self, llm: Any = None) -> None:
        # The underlying agent needs an LLM to plan actions. In production
        # this is wired to the LiteLLM inference plane (engine_id "litellm").
        self._llm = llm

    @property
    def engine_id(self) -> str:
        return "browser-use"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.ACI, Capability.TOOL_USE]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        try:
            import asyncio

            Agent = _import_browser_use()
            task = req.payload.get("task", "")
            agent = Agent(task=task, llm=self._llm)
            # 使用 _safe_async_run 避免在已有事件循环中调用 asyncio.run() 导致 RuntimeError
            result = _safe_async_run(agent.run())
            return InvokeResult(ok=True, data={"result": str(result)})
        except Exception as e:  # no LLM / no browser binary installed
            logger.warning("browser-use invoke failed: %s", e)
            return InvokeResult(ok=False, error=str(e))

    def health(self) -> bool:
        try:
            _import_browser_use()
            return True
        except Exception as e:
            logger.debug("browser-use health check failed: %s", e)
            return False

    def supported_protocols(self) -> list[str]:
        return ["OpenAI"]
