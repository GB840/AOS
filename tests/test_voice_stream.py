"""流式语音架构（方案①）单测：覆盖流式 STT/TTS/状态机/barge-in/SSE 端点。

全部用 mock 注入，不依赖真实麦克风、权重或外网——验证「边说边出字 / 边播边打断」
的**逻辑契约**而非具体模型。真实模型（whisper.cpp / kokoro / edge_tts）接入后在
用户主机浏览器/麦克风验证。
"""
import base64
import os
import tempfile

from core.fabric.voice_chiplet import VoicePipeline


def _pipe(stt_stream, respond, tts_stream, planner=None):
    return VoicePipeline(
        stt_stream_fn=stt_stream,
        respond_fn=respond,
        tts_stream_fn=tts_stream,
        planner_fn=planner,
    )


def test_stream_turn_yields_partials_and_audio():
    """整句 transcript 时：partial(整句) -> reply_start -> reply_token -> audio_chunk* -> done。"""
    pipe = _pipe(
        stt_stream=lambda ap: iter(["你", "好世界"]),
        respond=lambda t: {"reply": "回应:" + t, "mood": "happy"},
        tts_stream=lambda t, p: iter([(b"a1", "mp3"), (b"a2", "mp3")]),
    )
    events = list(pipe.handle_voice_turn_stream(transcript="你好世界"))
    types = [e["type"] for e in events]
    assert types[0] == "partial"
    assert types[-1] == "done"
    assert events[0]["text"] == "你好世界"
    chunks = [e for e in events if e["type"] == "audio_chunk"]
    assert len(chunks) == 2
    # audio_chunk 数据可解码
    assert base64.b64decode(chunks[0]["data"]) == b"a1"
    assert chunks[0]["ext"] == "mp3"
    assert events[-1]["reply"] == "回应:你好世界"
    assert events[-1]["state"]["state"] == "idle"


def test_stream_barge_in_interrupts():
    """流式 barge-in：interrupt_checker 第 2 次返回 True → 立即 interrupted，不再 done。"""
    counter = {"n": 0}

    def checker():
        counter["n"] += 1
        return counter["n"] >= 3

    pipe = _pipe(
        stt_stream=lambda ap: iter(["x"]),
        respond=lambda t: {"reply": "r"},
        tts_stream=lambda t, p: iter([(b"a", "mp3"), (b"b", "mp3"), (b"c", "mp3")]),
    )
    events = list(pipe.handle_voice_turn_stream(transcript="x", interrupt_checker=checker))
    types = [e["type"] for e in events]
    assert "interrupted" in types
    assert types[-1] == "interrupted"
    assert "done" not in types  # 被打断不应 yield done
    # 第一个 audio_chunk 已出，第二个前被打断
    audio = [e for e in events if e["type"] == "audio_chunk"]
    assert len(audio) == 1


def test_stream_plan_uses_background():
    """force_plan：前台 yield reply_start + ack token + done(task_id)；后台异步跑。"""
    pipe = _pipe(
        stt_stream=lambda ap: iter(["x"]),
        respond=lambda t: {"reply": "r"},
        tts_stream=lambda t, p: iter([(b"a", "mp3")]),
        planner=lambda t: {"reply": "plan result", "planner_used": "mock"},
    )
    events = list(pipe.handle_voice_turn_stream(transcript="做A然后B", force_plan=True))
    types = [e["type"] for e in events]
    assert "reply_start" in types
    assert "reply_token" in types
    dones = [e for e in events if e["type"] == "done"]
    assert len(dones) == 1
    assert dones[0]["task_id"], "应返回后台任务 id"
    assert dones[0]["ok"] is True


def _mock_handler():
    """造一个最小 mock HTTP handler：覆盖流式/JSON 写出，避免依赖真实 socket 属性。"""
    from core.fabric import http_server as HS
    h = HS.FabricHubHTTPHandler.__new__(HS.FabricHubHTTPHandler)
    h._send_json = lambda *a, **k: None
    return h


def test_sse_turn_stream_endpoint(monkeypatch):
    """HTTP：POST /api/voice/turn/stream 用 SSE 推事件（mock pipeline 生成器）。"""
    from core.fabric import http_server as HS
    from core.fabric.voice_chiplet import VoicePipeline

    def fake_gen(**kw):
        yield {"type": "partial", "text": "hi"}
        yield {"type": "done", "ok": True, "reply": "hi back"}

    monkeypatch.setattr(VoicePipeline, "handle_voice_turn_stream", staticmethod(fake_gen))

    captured = []
    h = _mock_handler()
    h._stream_response = lambda gen: captured.extend(list(gen))

    h._post_voice_turn_stream({"transcript": "hi"})
    types = [e["type"] for e in captured]
    assert "partial" in types
    assert "done" in types
    assert captured[-1]["reply"] == "hi back"


def test_sse_stt_stream_endpoint(monkeypatch):
    """HTTP：POST /api/voice/stt/stream 推 partial（mock STT 流式）。"""
    from core.fabric import http_server as HS
    from core.fabric.adapters.stt_adapter import STTAdapter

    def fake_stream(path):
        yield "你好"
        yield "世界"

    monkeypatch.setattr(STTAdapter, "stream_transcribe", staticmethod(fake_stream))

    captured = []
    h = _mock_handler()
    h._stream_response = lambda gen: captured.extend(list(gen))

    fd, ap = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        h._post_voice_stt_stream({"audio_path": ap})
    finally:
        os.remove(ap)
    types = [e["type"] for e in captured]
    assert types == ["partial", "partial"]
    assert captured[0]["text"] == "你好"


def test_adapters_expose_streaming_interface():
    """适配器暴露流式接口；supports_streaming 对 web_speech 诚实返回 False。"""
    from core.fabric.adapters.stt_adapter import STTAdapter
    from core.fabric.adapters.tts_adapter import TTSAdapter

    stt = STTAdapter(engine="web_speech")
    assert hasattr(stt, "stream_transcribe")
    assert stt.supports_streaming() is False  # web_speech 无音频输入

    tts = TTSAdapter(engine="web_speech")
    assert hasattr(tts, "stream_synthesize")
    assert tts.supports_streaming() is False  # web_speech 退化整段
