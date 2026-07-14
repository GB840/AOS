"""VoiceChiplet —— AOS 的语音编排芯粒（方案三：语音嵌入内核，而非独立助手）。

这是 AOS 比「独立语音 agent」(如 Daisy mark-II) 牛的地方：
- 语音只是 FabricHub 的一个**可替换芯粒**——它的「脑子」是整个内核
  （3D 生命体 / 联网搜索 / 规划 ag2 / 记忆 mem0），不是只会聊天的单一 agent。
- 状态机 + 持续对话 + 3 秒打断窗口（对标 Daisy 的「回答后 3 秒续聊/打断」），
  但实现与引擎解耦，whisper.cpp / edge-tts / kokoro 任意替换。
- 端云合作：本地 whisper 用不了→浏览器 Web Speech 兜底；本地 kokoro 用不了
  →edge-tts→浏览器 speechSynthesis，层层降级不崩。

两个核心构件：
1. ConversationStateMachine：idle/listening/processing/speaking + 打断窗口。
   纯逻辑、可单测，不依赖任何音频 IO。
2. VoicePipeline：把 STT→AOS 能力路由→TTS 串成一次「语音回合」，
   stt/respond/tts 都可注入，便于无真实麦克风/模型时测试。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# 1) 对话状态机（持续对话 + 打断窗口）
# ============================================================================
class ConversationStateMachine:
    """语音对话的生命周期：idle → listening → processing → speaking。

    打断（barge-in）：在 speaking 状态下、barge_window 秒内检测到用户再次
    开口，立即中断当前播报、回到 listening，实现「自然对话流」（问一次等一次
   升级为随时插话）。窗口外或已播完则正常回到 idle。
    """

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"

    def __init__(self, barge_window: float = 3.0) -> None:
        self.state = self.IDLE
        self.barge_window = barge_window
        self._speak_start: float = 0.0
        self.interrupted = False
        self.turns = 0
        self.history: list[tuple[str, str]] = []  # (event, new_state)

    def _set(self, new_state: str, event: str = "") -> None:
        if new_state != self.state:
            self.history.append((event or new_state, new_state))
            self.state = new_state

    def on_user_start(self) -> None:
        """用户开始说话（VAD 触发）。若在播报窗口内 → 打断。"""
        if self.state == self.SPEAKING and self._in_barge_window():
            self.interrupted = True
            logger.info("barge-in: 打断当前播报，回到 listening")
            self._set(self.LISTENING, "barge_in")
        else:
            self._set(self.LISTENING, "user_start")

    def on_user_utterance(self, text: str = "") -> None:
        """用户说完一句话（已识别成文本）。进入处理。"""
        self.turns += 1
        self.interrupted = False
        self._set(self.PROCESSING, "utterance")

    def on_response_ready(self) -> None:
        """AOS 产出回复，开始播报。记录播报起点以计算打断窗口。"""
        self._speak_start = time.perf_counter()
        self._set(self.SPEAKING, "speak")

    def on_speech_end(self) -> None:
        """播报结束，回到空闲等待下一轮。"""
        self._set(self.IDLE, "speech_end")

    def _in_barge_window(self) -> bool:
        return (time.perf_counter() - self._speak_start) <= self.barge_window

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "turns": self.turns,
            "interrupted": self.interrupted,
            "barge_window": self.barge_window,
            "in_barge_window": self._in_barge_window() if self.state == self.SPEAKING else None,
        }


# ============================================================================
# 2) 语音流水线（一次「语音回合」：听 → 想 → 说）
# ============================================================================
@dataclass
class VoiceTurnResult:
    ok: bool
    user_text: str = ""
    reply: str = ""
    audio_url: Optional[str] = None
    tts_engine: Optional[str] = None
    mood: Optional[str] = None
    state: dict = field(default_factory=dict)
    error: Optional[str] = None


class VoicePipeline:
    """STT → AOS 能力路由 → TTS 的一次编排。

    respond_fn 默认接 AOS 的 3D 生命体同伴（companion.handle_companion_message），
    因此「对着伙伴说话 → 它去调 3D/搜索/AOS 能力 → 用声音回应」整条链路打通。
    stt/tts 默认用本模块适配器（懒加载），也可注入用于测试。
    """

    def __init__(
        self,
        stt_fn: Optional[Callable[[dict], str]] = None,
        respond_fn: Optional[Callable[[str], dict]] = None,
        tts_fn: Optional[Callable[[str], dict]] = None,
        barge_window: float = 3.0,
        user_id: str = "default",
    ) -> None:
        self.user_id = user_id
        self.fsm = ConversationStateMachine(barge_window=barge_window)
        # 注入优先；否则默认懒加载 AOS 真实芯粒
        self._stt_fn = stt_fn or self._default_stt
        self._respond_fn = respond_fn or self._default_respond
        self._tts_fn = tts_fn or self._default_tts

    # ---- 默认实现（懒加载 AOS 真实引擎）----
    def _default_stt(self, payload: dict) -> str:
        from .adapters.stt_adapter import STTAdapter
        from .adapter import InvokeRequest
        r = STTAdapter().invoke(InvokeRequest(capability="voice.stt", payload=payload))
        if not r.ok:
            raise RuntimeError(r.error or "STT 失败")
        return r.data["text"]

    def _default_respond(self, text: str) -> dict:
        from . import companion as _companion
        return _companion.handle_companion_message(text, self.user_id)

    def _default_tts(self, text: str) -> dict:
        from .adapters.tts_adapter import TTSAdapter
        from .adapter import InvokeRequest
        r = TTSAdapter().invoke(InvokeRequest(capability="voice.tts",
                                              payload={"text": text}))
        if not r.ok:
            # 诚实降级：TTS 引擎不可用，返回文本由前端 speechSynthesis 兜底
            return {"text": text, "engine": "web_speech", "audio_url": None,
                    "error": r.error}
        return r.data

    # ---- 一次语音回合 ----
    def handle_voice_turn(
        self,
        transcript: str = "",
        audio_path: str = "",
        audio_b64: str = "",
        audio_suffix: str = "wav",
    ) -> VoiceTurnResult:
        # 1) 听：拿到用户文本
        self.fsm.on_user_start()
        if transcript and transcript.strip():
            user_text = transcript.strip()
        else:
            if not audio_path and not audio_b64:
                return VoiceTurnResult(ok=False, error="需要 transcript 或 audio")
            payload = {}
            if audio_path:
                payload["audio_path"] = audio_path
            if audio_b64:
                payload["audio_b64"] = audio_b64
                payload["audio_suffix"] = audio_suffix
            try:
                user_text = self._stt_fn(payload)
            except Exception as e:
                return VoiceTurnResult(ok=False, error=f"STT 失败: {e}")
        self.fsm.on_user_utterance(user_text)

        # 2) 想：路由到 AOS 能力（同伴编排）
        try:
            resp = self._respond_fn(user_text)
            reply = (resp.get("reply") if isinstance(resp, dict) else str(resp)) or ""
            mood = resp.get("mood") if isinstance(resp, dict) else None
        except Exception as e:
            return VoiceTurnResult(ok=False, user_text=user_text, error=f"响应失败: {e}")
        self.fsm.on_response_ready()

        # 3) 说：合成语音（失败则前端兜底）
        audio_url = None
        tts_engine = None
        try:
            tts_out = self._tts_fn(reply)
            audio_url = tts_out.get("audio_url")
            tts_engine = tts_out.get("engine")
        except Exception as e:
            logger.warning("TTS 失败，前端 speechSynthesis 兜底: %s", e)
        self.fsm.on_speech_end()

        return VoiceTurnResult(
            ok=True,
            user_text=user_text,
            reply=reply,
            audio_url=audio_url,
            tts_engine=tts_engine,
            mood=mood,
            state=self.fsm.snapshot(),
        )


# 便捷入口：用默认 AOS 引擎跑一次语音回合。
def handle_voice_turn(
    transcript: str = "",
    audio_path: str = "",
    audio_b64: str = "",
    user_id: str = "default",
    barge_window: float = 3.0,
) -> VoiceTurnResult:
    return VoicePipeline(user_id=user_id, barge_window=barge_window).handle_voice_turn(
        transcript=transcript, audio_path=audio_path, audio_b64=audio_b64)
