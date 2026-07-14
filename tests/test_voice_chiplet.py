"""VoiceChiplet 单元测试 —— 状态机 + 全链路编排（mock 驱动，无需真实麦克风/模型）。

验证点（均不依赖 whisper/kokoro 等重依赖，纯逻辑可复现）：
1. ConversationStateMachine：idle→listening→processing→speaking 状态流转 +
   3 秒窗口内的 barge-in（打断）正确触发。
2. VoicePipeline.handle_voice_turn：听(transcript)→想(respond)→说(tts) 全链路，
   STT 仅在无 transcript 时被调用；音频合成失败优雅降级不崩。
3. STTAdapter：web_speech 透传 transcript；VOICE_STT 能力声明正确。
4. TTSAdapter：web_speech 返回 audio_url=None(前端朗读兜底)，不抛。
5. handle_voice_turn 默认路径（真实 companion + web_speech）端到端可跑。
"""
from __future__ import annotations

import time

from core.fabric.voice_chiplet import (
    ConversationStateMachine,
    VoicePipeline,
    handle_voice_turn,
)
from core.fabric.capability import Capability
from core.fabric.adapters.stt_adapter import STTAdapter
from core.fabric.adapters.tts_adapter import TTSAdapter


# ---------------------------------------------------------------------------
# 1) 状态机 + 打断窗口
# ---------------------------------------------------------------------------
def test_state_machine_transitions():
    fsm = ConversationStateMachine(barge_window=3.0)
    assert fsm.state == fsm.IDLE
    fsm.on_user_start()
    assert fsm.state == fsm.LISTENING
    fsm.on_user_utterance("你好")
    assert fsm.state == fsm.PROCESSING
    fsm.on_response_ready()
    assert fsm.state == fsm.SPEAKING
    fsm.on_speech_end()
    assert fsm.state == fsm.IDLE
    assert fsm.turns == 1


def test_barge_in_within_window():
    fsm = ConversationStateMachine(barge_window=3.0)
    fsm.on_user_start()
    fsm.on_user_utterance("第一句")
    fsm.on_response_ready()  # 进入 speaking，记录起点
    # 窗口内用户再次开口 → 打断
    fsm.on_user_start()
    assert fsm.state == fsm.LISTENING
    assert fsm.interrupted is True
    # 第二句正常处理
    fsm.on_user_utterance("打断后的第二句")
    assert fsm.state == fsm.PROCESSING
    assert fsm.turns == 2


def test_no_barge_in_after_window():
    fsm = ConversationStateMachine(barge_window=0.05)
    fsm.on_user_start()
    fsm.on_user_utterance("第一句")
    fsm.on_response_ready()
    time.sleep(0.12)  # 超过窗口
    fsm.on_user_start()  # 窗口外，不打断，仍为 listening 起点
    # 窗口外不应标记 interrupted（on_user_start 仅对 speaking+窗口内置 interrupted）
    assert fsm.state == fsm.LISTENING
    # interrupted 在上一轮 speaking 时已清零（on_user_utterance 重置）
    assert fsm.interrupted is False


# ---------------------------------------------------------------------------
# 2) VoicePipeline 全链路（mock 驱动）
# ---------------------------------------------------------------------------
def test_pipeline_with_transcript_skips_stt():
    calls = {"stt": 0, "respond": 0, "tts": 0}

    def stt_fn(payload):
        calls["stt"] += 1
        return payload.get("transcript", "")

    def respond_fn(text):
        calls["respond"] += 1
        return {"reply": f"回应：{text}", "mood": "happy"}

    def tts_fn(text):
        calls["tts"] += 1
        return {"text": text, "audio_url": "/x.mp3", "engine": "mock"}

    pipe = VoicePipeline(stt_fn=stt_fn, respond_fn=respond_fn, tts_fn=tts_fn)
    res = pipe.handle_voice_turn(transcript="做个宇宙粒子星河")
    assert res.ok is True
    assert res.user_text == "做个宇宙粒子星河"
    assert res.reply == "回应：做个宇宙粒子星河"
    assert res.audio_url == "/x.mp3"
    assert res.state["state"] == "idle"
    assert calls["stt"] == 0   # transcript 直传，不应触发 STT
    assert calls["respond"] == 1
    assert calls["tts"] == 1


def test_pipeline_tts_failure_degrades_gracefully():
    def stt_fn(payload):
        return payload.get("transcript", "")

    def respond_fn(text):
        return {"reply": "好的", "mood": "calm"}

    def tts_fn(text):
        raise RuntimeError("TTS 引擎挂了")

    pipe = VoicePipeline(stt_fn=stt_fn, respond_fn=respond_fn, tts_fn=tts_fn)
    res = pipe.handle_voice_turn(transcript="你好")
    # 即便 TTS 崩，回合仍 ok，audio_url=None，由前端兜底
    assert res.ok is True
    assert res.reply == "好的"
    assert res.audio_url is None


def test_pipeline_audio_path_triggers_stt():
    calls = {"stt": 0}

    def stt_fn(payload):
        calls["stt"] += 1
        assert payload.get("audio_path") == "/tmp/a.wav"
        return "语音识别结果"

    def respond_fn(text):
        return {"reply": f"对：{text}"}

    def tts_fn(text):
        return {"text": text, "audio_url": None, "engine": "web_speech"}

    pipe = VoicePipeline(stt_fn=stt_fn, respond_fn=respond_fn, tts_fn=tts_fn)
    res = pipe.handle_voice_turn(audio_path="/tmp/a.wav")
    assert res.user_text == "语音识别结果"
    assert calls["stt"] == 1


# ---------------------------------------------------------------------------
# 3) STT / TTS 适配器（web_speech 兜底路径，零重依赖）
# ---------------------------------------------------------------------------
def test_stt_adapter_declares_capability_and_passthrough():
    a = STTAdapter(engine="web_speech")
    caps = [c.value if hasattr(c, "value") else str(c) for c in a.advertise_capabilities()]
    assert Capability.VOICE_STT.value in caps
    assert a.health() is True
    from core.fabric.adapter import InvokeRequest
    r = a.invoke(InvokeRequest(capability="voice.stt", payload={"transcript": "你好世界"}))
    assert r.ok is True
    assert r.data["text"] == "你好世界"


def test_tts_adapter_web_speech_no_audio():
    a = TTSAdapter(engine="web_speech")
    caps = [c.value if hasattr(c, "value") else str(c) for c in a.advertise_capabilities()]
    assert Capability.VOICE_TTS.value in caps
    assert a.health() is True
    from core.fabric.adapter import InvokeRequest
    r = a.invoke(InvokeRequest(capability="voice.tts", payload={"text": "你好"}))
    assert r.ok is True
    assert r.data["audio_url"] is None
    assert r.data["engine"] == "web_speech"


# ---------------------------------------------------------------------------
# 4) 默认路径端到端（真实 companion + web_speech，不依赖任何重引擎）
# ---------------------------------------------------------------------------
def test_default_voice_turn_end_to_end():
    res = handle_voice_turn(transcript="做个宇宙粒子星河", user_id="test_voice")
    assert res.ok is True
    assert res.user_text == "做个宇宙粒子星河"
    assert isinstance(res.reply, str) and res.reply
    # 若环境有可用 TTS 引擎（如 edge_tts），audio_url 指向合成音频；
    # 否则为 None，由前端 speechSynthesis 朗读兜底。两种都合法。
    assert res.audio_url is None or res.audio_url.startswith("/api/voice/audio/")
    assert res.state["state"] == "idle"
