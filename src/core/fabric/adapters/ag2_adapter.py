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

import difflib
import os
import re
from typing import Any

import logging
logger = logging.getLogger(__name__)


def _text_similarity(a: str, b: str) -> float:
    """0~1 字符级相似度（difflib ratio）；任一为空返回 0。"""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _dedup_text(text: str) -> str:
    """去除 LLM（尤其 glm-4-flash 长 prompt 下）把正文整段重复输出的问题。

    两层防御：
      1) 段落级：相邻近重复段落直接丢弃（防「同一段连发两遍」）；
      2) 整文级：扫描粗粒度候选边界，若某点之后的后缀与正文开头高度相似
         （>=0.9 且重复段占比足够大），则截到该点（防「整篇报告输出两次」）。
    短文本（<120 字）直接跳过，避免误伤短输出（如规划步骤）。
    """
    if not text or len(text) < 120:
        return text
    # 1) 段落级去重
    paras = re.split(r"\n\s*\n", text)
    cleaned: list[str] = []
    for p in paras:
        if p.strip() and cleaned:
            if _text_similarity(cleaned[-1], p) >= 0.9:
                continue
        cleaned.append(p)
    text = "\n\n".join(cleaned).strip()
    if not text or len(text) < 120:
        return text

    # 2) 整文级去重：检测「整篇重复两遍」。
    #    用「尾部 L 字 vs 头部 L 字」做对齐比较（对副本间的换行/分隔符偏移鲁棒），
    #    从 L=n/2 向下扫到 n/4，命中高相似即判定为重复，切点 = n-L（保留第一份）。
    n = len(text)
    for L in range(n // 2, n // 4, -1):
        head = text[:L]
        tail = text[-L:]
        if _text_similarity(head, tail) >= 0.9:
            cut = n - L
            # 仅当切点落在中段（约 1/3~2/3）才采纳，避免误伤正常长文
            if n // 3 <= cut <= 2 * n // 3:
                return text[:cut].strip()
    return text

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

# autogen(ag2) 的 import 在某些环境下会**卡死**（不是报错，是阻塞），
# 故不能用顶层 `try: import autogen / except` 兜底——except 抓不住「卡死」，
# 整条 `import kernel.wiring` 链会被拖垮。改为惰性 + 超时线程守卫：
# 首次真正要跑 group chat 时才导入，6s 内没返回就判不可用，模块导入瞬时完成。
_AG2_AVAILABLE = False
_AUTOGEN_MODULE = None


def _ensure_autogen(timeout: float = 180.0):
    """惰性导入 autogen；卡死 / 失败都返回 None（绝不阻塞调用方线程）。

    用 daemon 线程跑 import，主线程 join 超时即放弃——这样即便 autogen
    在 import 时卡死，也不会让 API 进程 / 内核构建挂起，只是该能力不可用。
    """
    global _AG2_AVAILABLE, _AUTOGEN_MODULE
    if _AUTOGEN_MODULE is not None or _AG2_AVAILABLE:
        return _AUTOGEN_MODULE
    from ..resilience import guarded_import
    mod = guarded_import("autogen", timeout)
    _AUTOGEN_MODULE = mod
    _AG2_AVAILABLE = mod is not None
    return mod


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

    def _run_single_agent(
        self, task: str, system_message: str, temperature: float | None = None
    ) -> str:
        """跑单个 AssistantAgent（用于规划 / 内容生产这类单角色任务）。

        用 generate_reply 直接取回复，不走 UserProxyAgent——后者在 NEVER 模式
        下会在 assistant 回复后发一条空消息，导致 400（"未正常接收到prompt参数"）
        并把整个 invoke 搞挂。generate_reply 干净返回文本，比 group chat 更稳。
        """
        autogen = _ensure_autogen()
        if autogen is None:
            raise RuntimeError("ag2 (autogen) is not importable in this environment")
        cfg = dict(self._llm_config)
        if temperature is not None:
            cfg["temperature"] = temperature
        agent = autogen.AssistantAgent(
            name="planner",
            llm_config=cfg,
            system_message=system_message,
        )
        reply = agent.generate_reply(
            messages=[{"role": "user", "content": task}], sender=None
        )
        if isinstance(reply, dict):
            return str(reply.get("content", "")).strip()
        return str(reply).strip()

    def produce_text(self, prompt: str) -> str:
        """单角色「内容生产」：基于给定材料产出正文（报告/分析/总结等）。

        用单个 writer agent（低温 + 明确「只输出一次」），避免 group chat 跑偏
        成「团队讨论」式元叙述，也避免 glm-4-flash 在长 prompt 下把正文重复输出。
        最后再经 _dedup_text 兜底去重——模型若仍把整段重复两遍，这里截掉重复部分。
        """
        raw = self._run_single_agent(
            prompt,
            system_message=(
                "You are a precise technical writer. Write the requested content "
                "based strictly on the provided material. Output ONLY the content "
                "itself (markdown is fine) — no preamble, no 'Here is the report', "
                "no commentary, no questions. Output the content EXACTLY ONCE; "
                "never repeat the same passage."
            ),
            temperature=0.1,
        )
        return _dedup_text(raw)

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
                # 规划是单角色任务，用单个 planner agent（比 3 轮 round-robin
                # group chat 更稳、更快、且最终消息即规划本身而非 tester 反馈）。
                plan_prompt = (
                    "Plan the following task as concrete executable steps for the "
                    "AOS autonomous agent system. Available tools (use exactly these "
                    "names as bracketed tags): web.search, action.code_exec, "
                    "inference.llm, memory.semantic.\n"
                    "web.search = search the internet\n"
                    "action.code_exec = run LOCAL terminal/Python commands on this "
                    "Windows machine (pip/winget/choco install, python scripts, echo "
                    "redirect to write files)\n"
                    "inference.llm = analyze search results and produce text/content\n"
                    "memory.semantic = store/recall important information\n"
                    "Output each step on its own line as: N. [tool_name] <what to do>\n"
                    "STRICT SAFETY & RELIABILITY RULES (a plan violating any is rejected):\n"
                    "1. Windows system. Use winget/choco for install, NOT brew.\n"
                    "2. NEVER use 'git push' or push to any remote repository; the "
                    "agent must not publish/push code. 'git clone' only for well-known "
                    "public repos you are CERTAIN exist; prefer generating content "
                    "locally instead.\n"
                    "3. To write a file, use a LOCAL Python command with a <CONTENT> "
                    "placeholder, e.g.\n"
                    "   action.code_exec = python -c \"open(r'D:/AOS/_output/out.md','w',encoding='utf-8').write('<CONTENT>')\"\n"
                    "   The system automatically fills <CONTENT> with the previous "
                    "inference.llm step's real output. Do NOT assume tools like pandoc "
                    "/ markdown editors are installed, and do NOT depend on external "
                    "templates or services.\n"
                    "4. Do NOT invent external repos, URLs, APIs, credentials or "
                    "services. Only use the real capabilities above. Build file "
                    "content from web.search + inference.llm, then write it locally.\n"
                    "5. When a step writes a file, ALWAYS use the <CONTENT> placeholder "
                    "(never embed the actual text in the python command — it breaks "
                    "the string literal and crashes). The system fills <CONTENT> with "
                    "the previous inference.llm output. Use EXACTLY ONE write step per "
                    "file (mode 'w'); do NOT create multiple append ('a') steps. "
                    "Never reference other steps' names as Python variables — they are "
                    "not in scope and will crash.\n"
                    "6. Keep the plan SHORT: at most 4 steps. For a report/file task "
                    "the typical shape is: 1) web.search, 2) inference.llm (produce the "
                    "FULL content), 3) action.code_exec (write <CONTENT> to the file), "
                    "optionally 4) memory.semantic. Do not describe a human team; "
                    "describe tool calls the system will execute.\n"
                    f"Task: {topic}"
                )
                reply = self._run_single_agent(
                    plan_prompt,
                    system_message=(
                        "You are a precise task planner for an autonomous Windows "
                        "agent. Output ONLY the numbered step list exactly as "
                        "instructed. No preamble, no extra commentary, no questions."
                    ),
                )
                return InvokeResult(ok=True, data={"engine": "ag2", "plan": reply})
            return InvokeResult(
                ok=False, error=f"unsupported capability {req.capability.value}"
            )
        except Exception as e:  # surface real failures instead of faking success
            logger.warning("ag2 group chat invoke failed: %s", e)
            return InvokeResult(ok=False, error=f"ag2 group chat failed: {e}")

    def health(self) -> bool:
        # 主动尝试导入（prewarm 已在后台预热；预热中 guarded_import 返回 None
        # 不阻塞，等预热线程完成后再标 live）。仅观测，失败绝不抛。
        if not _AG2_AVAILABLE:
            try:
                _ensure_autogen()
            except Exception:  # noqa: BLE001
                pass
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
