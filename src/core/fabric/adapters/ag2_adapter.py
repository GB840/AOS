"""Real AG2 (AutoGen community fork) adapter for the AOS open fabric.

AG2 (https://ag2.ai, MIT) is a genuine open-source multi-agent *group chat*
orchestration framework - it provides GroupChat + GroupChatManager, exactly
the "group.orchestration" capability AOS needs. It is pip-installable
(``pip install ag2`` -> the ``autogen`` namespace) and runs as an in-process
library, so it needs no Docker and no external service.

AG2 is the group-orchestration engine AOS runs. It satisfies the hard rule:
real open-source, not self-written. It is an in-process library (pip `ag2`)
with no Docker dependency, so it is reachable in any environment.

This adapter runs a REAL group chat: it spins up specialist AssistantAgents
and a GroupChatManager, feeds the task, and returns the manager's final
aggregated reply. LLM access goes through the same OpenAI-compatible provider
(SiliconFlow / DeepSeek-V3) already wired for OpenClaw, so no new keys.
"""
from __future__ import annotations

import os
from typing import Any

import logging
logger = logging.getLogger(__name__)

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

# autogen(ag2) 的 import 在某些环境下会**卡死**（不是报错，是阻塞），
# 故不能用顶层 `try: import autogen / except` 兜底——except 抓不住「卡死」，
# 整条 `import kernel.wiring` 链会被拖垮。改为惰性 + 超时线程守卫：
# 首次真正要跑 group chat 时才导入，6s 内没返回就判不可用，模块导入瞬时完成。
_AG2_AVAILABLE = False
_AUTOGEN_MODULE = None


def _ensure_autogen(timeout: float = 6.0):
    """惰性导入 autogen；卡死 / 失败都返回 None（绝不阻塞调用方线程）。

    用 daemon 线程跑 import，主线程 join 超时即放弃——这样即便 autogen
    在 import 时卡死，也不会让 API 进程 / 内核构建挂起，只是该能力不可用。
    """
    global _AG2_AVAILABLE, _AUTOGEN_MODULE
    if _AUTOGEN_MODULE is not None:
        return _AUTOGEN_MODULE
    if _AG2_AVAILABLE:
        return _AUTOGEN_MODULE
    import threading
    import importlib

    box: dict = {}
    def _run() -> None:
        try:
            box["m"] = importlib.import_module("autogen")
        except Exception:  # noqa: BLE001 - 任一导入错误都视为不可用
            box["err"] = True
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive() or "err" in box:
        _AG2_AVAILABLE = False
        return None
    _AUTOGEN_MODULE = box["m"]
    _AG2_AVAILABLE = True
    return _AUTOGEN_MODULE


def _llm_config() -> dict[str, Any]:
    """OpenAI-compatible config.

    Defaults to Zhipu (glm-4-flash, free tier) because the repo's
    SiliconFlow key was observed to run out of balance. Override via env:
      AOS_LLM_BASE_URL, SILICONFLOW_API_KEY / ZHIPU_API_KEY / OPENAI_API_KEY,
      AOS_LLM_MODEL.
    """
    base = os.environ.get("AOS_LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    key = (
        os.environ.get("ZHIPU_API_KEY")
        or os.environ.get("SILICONFLOW_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    model = os.environ.get("AOS_LLM_MODEL", "glm-4-flash")
    return {
        "model": model,
        "base_url": base,
        "api_key": key,
        "temperature": 0.3,
        "timeout": 60,
    }


class AG2Adapter(BaseAgentAdapter):
    """Wraps a real AG2 GroupChat as the group.orchestration engine."""

    def __init__(
        self,
        agents: list[str] | None = None,
        max_round: int = 3,
        llm_config: dict[str, Any] | None = None,
    ) -> None:
        self._agents = agents or ["planner", "developer", "tester"]
        self._max_round = max_round
        self._llm_config = llm_config or _llm_config()

    @property
    def engine_id(self) -> str:
        return "ag2"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.GROUP_ORCHESTRATION, Capability.PLANNING]

    def _run_group_chat(self, task: str) -> str:
        autogen = _ensure_autogen()
        if autogen is None:
            raise RuntimeError("ag2 (autogen) is not importable in this environment")
        cfg = self._llm_config

        # A user proxy that never asks for human input and never executes code;
        # it just kicks off the conversation and collects the final reply.
        user = autogen.UserProxyAgent(
            name="user",
            code_execution_config=False,
            human_input_mode="NEVER",
            function_map={},
        )
        specialists = [
            autogen.AssistantAgent(
                name=name,
                llm_config=cfg,
                system_message=(
                    f"You are the {name} in a multi-agent team solving one task. "
                    f"Be concise (<=3 sentences). Build on others' points."
                ),
            )
            for name in self._agents
        ]
        group = autogen.GroupChat(
            agents=[user, *specialists],
            messages=[],
            max_round=self._max_round,
            speaker_selection_method="round_robin",
        )
        manager = autogen.GroupChatManager(group, llm_config=cfg)
        result = user.initiate_chat(manager, message=task, summary_method="last_msg")
        # result.chat_history[-1] holds the manager's final aggregated message.
        return str(result.chat_history[-1].get("content", "")).strip()

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        try:
            if req.capability == Capability.GROUP_ORCHESTRATION:
                task = req.payload.get("text") or req.payload.get("topic") or "demo task"
                reply = self._run_group_chat(task)
                return InvokeResult(
                    ok=True,
                    data={"engine": "ag2", "group_chat": True, "reply": reply},
                )
            if req.capability == Capability.PLANNING:
                topic = req.payload.get("topic", "the task")
                # 让 AG2 产出「工具调用步骤」而非「团队分工叙述」：
                # 每行带 AOS 真实能力标签 [web.search] 等，解析器优先认标签。
                plan_prompt = (
                    "Plan the following task as concrete executable steps for the "
                    "AOS agent system. Available tools (use exactly these names as "
                    "bracketed tags): web.search, action.aci, media.image, media.video, "
                    "inference.llm, memory.semantic, action.code_exec, channel.access.\n"
                    "Output each step on its own line as: N. [tool_name] <what to do>\n"
                    "Do NOT describe a human team; describe tool calls the system will "
                    f"execute.\nTask: {topic}"
                )
                reply = self._run_group_chat(plan_prompt)
                return InvokeResult(ok=True, data={"engine": "ag2", "plan": reply})
            return InvokeResult(
                ok=False, error=f"unsupported capability {req.capability.value}"
            )
        except Exception as e:  # surface real failures instead of faking success
            logger.warning("ag2 group chat invoke failed: %s", e)
            return InvokeResult(ok=False, error=f"ag2 group chat failed: {e}")

    def health(self) -> bool:
        if not _AG2_AVAILABLE:
            return False
        try:
            return bool(self._llm_config.get("api_key"))
        except Exception as e:
            logger.debug("ag2 health check failed: %s", e)
            return False

    def supported_protocols(self) -> list[str]:
        # AG2 is an in-process library; it speaks no external agent protocol here.
        return []
