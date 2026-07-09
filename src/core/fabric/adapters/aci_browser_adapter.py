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

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability


def _import_browser_use():
    """Lazy import so the adapter is valid code even before `pip install`."""
    from browser_use import Agent  # type: ignore
    return Agent


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
            result = asyncio.run(agent.run())
            return InvokeResult(ok=True, data={"result": str(result)})
        except Exception as e:  # no LLM / no browser binary installed
            return InvokeResult(ok=False, error=str(e))

    def health(self) -> bool:
        try:
            _import_browser_use()
            return True
        except Exception:
            return False

    def supported_protocols(self) -> list[str]:
        return ["OpenAI"]
