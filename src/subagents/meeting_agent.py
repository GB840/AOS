"""
Meeting Agent - 会议自动化流水线子智能体

多 Agent 编排（复用现有芯粒，不新建模型/组件）：
  1. 转录  (voice.stt)             — 音频 → 文本（无音频则直接用传入 transcript）
  2. 摘要/行动项 (inference.llm)   — 文本 → 结构化会议纪要与行动项
  3. 结构化交接 (HandoffEnvelope)  — 存 IMA 知识库（复用已落地的结构化交接后端）

接入方式与 IMA / ViMax 同形（subagent + skill 调用 + API 端点），都是腾讯系场景的延伸。
"""

import os
import re
import json
import uuid
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MeetingAgent:
    """
    会议自动化流水线子智能体

    经 SubAgentRegistry 调度，把一次会议（转录文本或音频）编排成：
    转录 → LLM 摘要/行动项 → 结构化交接信封存 IMA。
    """

    NAME = "meeting"
    DESCRIPTION = "会议自动化流水线 — 转录 → 摘要/行动项 → 结构化交接存 IMA 知识库"
    CAPABILITIES = [
        "meeting_transcribe",
        "meeting_summary",
        "meeting_action_items",
        "structured_handoff",
        "tencent_ima",
    ]
    OPERATIONS = {
        "run": {
            "name": "run",
            "description": "运行会议流水线：传入 transcript 或 audio，产出结构化会议纪要与行动项并存 IMA",
            "params": ["transcript", "audio_path", "audio_b64", "audio_suffix",
                       "task_id", "title", "attendees", "auto_handoff"],
        },
    }

    def __init__(self):
        self._initialized = True

    # ---------------- 流水线定义 ----------------
    def _build_steps(self, audio: Optional[Dict[str, str]], transcript: str) -> list:
        """构造 OrchestrationChiplet 的 steps 定义（直接复用现有芯粒能力）。"""
        if audio:
            stt_in = (
                {"audio_path": audio["path"]}
                if audio.get("path")
                else {"audio_b64": audio["b64"], "audio_suffix": audio.get("suffix", "wav")}
            )
            return [
                {"capability": "voice.stt", "in": stt_in},
                {
                    "capability": "inference.llm",
                    "in_from": "previous",
                    "prompt": (
                        "你是一名专业的会议记录助手。以下是某次会议的转录文本。"
                        "请只输出一个严格的 JSON 对象（不要使用代码块标记，不要任何额外说明），结构如下：\n"
                        "{\n"
                        '  "summary": "一句话会议结论",\n'
                        '  "decisions": ["关键决议1", "关键决议2"],\n'
                        '  "action_items": [{"owner": "负责人", "task": "任务描述", "deadline": "截止日期或TBD"}],\n'
                        '  "open_questions": ["尚未确定的问题1"]\n'
                        "}\n"
                    ),
                },
            ]
        # 无音频：直接用 transcript 跑 LLM 综合
        return [
            {
                "capability": "inference.llm",
                "in": {
                    "prompt": (
                        "你是一名专业的会议记录助手。以下是某次会议的转录文本：\n"
                        f"{transcript}\n\n"
                        "请只输出一个严格的 JSON 对象（不要使用代码块标记，不要任何额外说明），结构如下：\n"
                        "{\n"
                        '  "summary": "一句话会议结论",\n'
                        '  "decisions": ["关键决议1", "关键决议2"],\n'
                        '  "action_items": [{"owner": "负责人", "task": "任务描述", "deadline": "截止日期或TBD"}],\n'
                        '  "open_questions": ["尚未确定的问题1"]\n'
                        "}\n"
                    )
                },
            }
        ]

    # ---------------- 文本/JSON 解析 ----------------
    @staticmethod
    def _extract_text(obj: Any) -> str:
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            for k in ("text", "result", "content", "output", "response", "message"):
                v = obj.get(k)
                if isinstance(v, str):
                    return v
            choices = obj.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message", {}).get("content")
                if isinstance(msg, str):
                    return msg
            return json.dumps(obj, ensure_ascii=False)
        return str(obj)

    @staticmethod
    def _parse_meeting(text: str) -> Dict[str, Any]:
        """把 LLM 输出解析成会议结构；解析失败则整段当 summary（不丢信息）。"""
        if not text:
            return {"summary": "", "decisions": [], "action_items": [], "open_questions": []}
        t = text.strip()
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            t = m.group(0)
        try:
            obj = json.loads(t)
        except Exception:
            return {"summary": text, "decisions": [], "action_items": [], "open_questions": []}
        return {
            "summary": obj.get("summary", "") or "",
            "decisions": obj.get("decisions") or [],
            "action_items": obj.get("action_items") or [],
            "open_questions": obj.get("open_questions") or [],
        }

    # ---------------- 信封 / 落库 ----------------
    def _build_envelope(self, task_id, title, attendees, meeting) -> Any:
        from core.fabric.handoff import HandoffEnvelope
        facts: list = []
        if meeting.get("decisions"):
            facts += [f"决议: {d}" for d in meeting["decisions"]]
        if meeting.get("summary"):
            facts.append(f"结论: {meeting['summary']}")
        if attendees:
            facts.append(f"参会人: {attendees}")
        actions = meeting.get("action_items") or []
        if actions:
            lines = [f"{a.get('owner', '?')} → {a.get('task', '?')} (截止: {a.get('deadline', 'TBD')})"
                     for a in actions]
            facts.append("行动项:\n" + "\n".join(lines))
        risk = meeting.get("open_questions") or []
        return HandoffEnvelope(
            task_id=task_id,
            title=title,
            summary=meeting.get("summary") or title,
            confirmed_facts=facts,
            assumptions=[],
            risk_boundary=risk,
            open_questions=risk,
            handoff_to="项目组",
            source="MeetingAgent",
            tags=["handoff", "meeting"],
        )

    @staticmethod
    def _store(envelope) -> Dict[str, Any]:
        try:
            from core.fabric.handoff import store_handoff
            return store_handoff(envelope)
        except Exception as e:
            logger.error("会议交接存 IMA 失败: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    # ---------------- 主入口 ----------------
    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        transcript = (input_data.get("transcript") or "").strip()
        audio_path = input_data.get("audio_path")
        audio_b64 = input_data.get("audio_b64")
        audio_suffix = input_data.get("audio_suffix", "wav")
        task_id = input_data.get("task_id") or f"meeting-{uuid.uuid4().hex[:8]}"
        title = input_data.get("title") or f"会议-{task_id}"
        attendees = input_data.get("attendees") or ""
        auto_handoff = input_data.get("auto_handoff", True)

        has_audio = bool(audio_path or audio_b64)
        if not has_audio and not transcript:
            return {"success": False, "error": "需要提供 transcript 或 audio_path/audio_b64"}

        audio = None
        if audio_path:
            audio = {"path": audio_path}
        elif audio_b64:
            audio = {"b64": audio_b64, "suffix": audio_suffix}

        steps = self._build_steps(audio, transcript)
        spec = {
            "steps": steps,
            "initial": {"transcript": transcript},
            "task_id": task_id,
            "auto_handoff": False,  # 我们自己存定制会议信封（含会议专属字段）
        }

        # 经 OrchestrationChiplet 跑流水线（多 Agent 编排：STT 芯粒 + LLM 芯粒）
        try:
            from mcp.protocol import _get_hub
            hub = _get_hub()
            res = hub.route("system.workflow", spec)
        except Exception as e:
            logger.error("会议流水线编排失败: %s", e, exc_info=True)
            return {"success": False, "error": f"流水线编排失败: {e}"}

        if not getattr(res, "ok", False):
            return {
                "success": False,
                "error": getattr(res, "error", "流水线执行失败"),
                "trace": (getattr(res, "data", {}) or {}).get("trace"),
            }

        final = (res.data or {}).get("final", {})
        llm_text = self._extract_text(final)
        meeting = self._parse_meeting(llm_text)

        handoff_res = None
        if auto_handoff:
            envelope = self._build_envelope(task_id, title, attendees, meeting)
            handoff_res = self._store(envelope)

        return {
            "success": True,
            "task_id": task_id,
            "meeting": meeting,
            "raw_llm": llm_text,
            "handoff": handoff_res,
            "pipeline": {
                "ok_steps": (res.data or {}).get("ok_steps"),
                "failed_steps": (res.data or {}).get("failed_steps"),
            },
        }

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """SubAgentRegistry / HTTP 同步调用入口"""
        try:
            return self.run(input_data)
        except Exception as e:
            logger.error("MeetingAgent 执行失败: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    # 兼容异步入口（保持与其他 subagent 同形）
    async def async_handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.handle, input_data)

    def is_ready(self) -> bool:
        return True

    def list_operations(self) -> Dict[str, Any]:
        return self.OPERATIONS


def get_meeting_subagent() -> "MeetingAgent":
    return MeetingAgent()


def register_meeting_subagent(registry=None):
    """注册会议子智能体到 SubAgentRegistry（与 IMA / ViMax 同形）"""
    if registry is None:
        from subagents.registry import SubAgentRegistry
        registry = SubAgentRegistry()
    agent = MeetingAgent()
    registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
    logger.info("Meeting 子智能体已注册")
    return agent
