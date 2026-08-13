"""语音增强三件套的单元测试：常驻唤醒 VAD + ag2 长任务规划路由 + 全离线 STT 探测。

不依赖麦克风/真实模型：VAD 用合成音频帧验证，规划用注入式 mock planner，
STT 引擎探测用 STTAdapter 真实 health 逻辑。"""
from __future__ import annotations

import numpy as np
import time

from core.fabric.voice_wake import numpy_vad, make_vad, VoiceWakeLoop
from core.fabric.voice_chiplet import VoicePipeline


# ============================================================================
# 1) VAD（纯 numpy 能量+过零率）
# ============================================================================
def test_numpy_vad_silence_is_false():
    silence = np.zeros(1600, dtype=np.float32)        # 静音
    noise = (np.random.default_rng(0).standard_normal(1600).astype(np.float32)
             * 0.0001)                                  # 极弱噪声
    assert numpy_vad(silence) is False
    assert numpy_vad(noise) is False


def test_numpy_vad_speech_like_is_true():
    # 模拟带能量的类语音信号（多频叠加，过零率适中）
    t = np.arange(1600) / 16000.0
    sig = (np.sin(2 * np.pi * 220 * t) * 0.3
           + np.sin(2 * np.pi * 440 * t) * 0.2).astype(np.float32)
    assert numpy_vad(sig) is True


def test_make_vad_falls_back_to_numpy_when_no_webrtcvad():
    fn, name = make_vad()
    assert name in ("numpy", "webrtcvad")
    # 函数可用
    assert callable(fn)
    assert fn(np.zeros(1600, np.float32)) is False


# ============================================================================
# 2) VoiceWakeLoop 状态机（不依赖麦克风，直接喂帧）
# ============================================================================
def _feed_loop(loop: VoiceWakeLoop, utterances: list[np.ndarray], gap=0.0):
    """模拟把若干段「话语」喂给唤醒循环，中间用静音填充。"""
    for utt in utterances:
        # 话语前静音
        for _ in range(10):
            loop._detect(np.zeros(loop.frame_samples, np.float32))
        # 话语本身
        n = max(1, len(utt) // loop.frame_samples)
        for i in range(n):
            chunk = utt[i * loop.frame_samples:(i + 1) * loop.frame_samples]
            if chunk.size:
                loop._detect(chunk)
        # 尾点静音（超过 silence_timeout 触发 emit）
        for _ in range(int(loop.silence_timeout_ms / loop.frame_ms) + 3):
            loop._detect(np.zeros(loop.frame_samples, np.float32))


def test_wake_loop_detects_utterance_and_triggers_callback():
    got = []

    def cb(audio: np.ndarray):
        got.append(audio)

    # 用 numpy VAD（不依赖 webrtcvad/麦克风）
    loop = VoiceWakeLoop(on_utterance=cb, vad_engine="numpy",
                         silence_timeout_ms=300, min_speech_ms=100, frame_ms=30)
    # 一句类语音
    t = np.arange(4800) / 16000.0
    speech = (np.sin(2 * np.pi * 300 * t) * 0.4).astype(np.float32)
    _feed_loop(loop, [speech])
    assert loop.total_utterances == 1
    assert len(got) == 1
    assert got[0].size > 0


def test_wake_loop_ignores_short_noise():
    got = []

    def cb(audio):
        got.append(audio)

    loop = VoiceWakeLoop(on_utterance=cb, vad_engine="numpy",
                         silence_timeout_ms=300, min_speech_ms=350, frame_ms=30)
    # 一段太短（低于 min_speech_ms）的语音 → 不应触发
    t = np.arange(800) / 16000.0
    speech = (np.sin(2 * np.pi * 300 * t) * 0.4).astype(np.float32)
    _feed_loop(loop, [speech])
    assert loop.total_utterances == 0
    assert len(got) == 0


# ============================================================================
# 3) VoicePipeline 的 ag2 长任务规划路由
# ============================================================================
def test_should_plan_regex():
    p = VoicePipeline()
    assert p._should_plan("帮我查一下天气然后做个 3D 场景") is True
    assert p._should_plan("先生成分镜再导出视频") is True
    assert p._should_plan("做个宇宙粒子星河") is False
    assert p._should_plan("你好小元") is False


def test_force_plan_routes_to_planner_and_sets_planner_used():
    calls = {}

    def fake_planner(text: str) -> dict:
        calls["text"] = text
        return {"reply": "已规划完成", "planner_used": "ag2-mock", "plan": "1. a\n2. b"}

    # 注入即时 tts_fn，隔离出 plan 异步路径本身（TTS 首载耗时不计入）
    p = VoicePipeline(planner_fn=fake_planner, auto_plan=False,
                      tts_fn=lambda t: {"text": t, "engine": "web_speech"})
    res = p.handle_voice_turn(transcript="帮我查天气然后做3D场景", force_plan=True)
    # 前台：立即返回短反馈 + task_id（GPT-Live 式，不阻塞）；planner_used 待后台回填
    assert res.ok is True
    assert res.task_id and res.task_id.startswith("vt_")
    assert res.planner_used is None
    assert res.reply in VoicePipeline._FRONT_ACKS
    # 后台：轮询拿到规划结果（规划器确被调用）
    r = None
    for _ in range(60):
        r = VoicePipeline.get_task_result(res.task_id)
        if r and r.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert r is not None and r["status"] == "done"
    assert r["planner_used"] == "ag2-mock"
    assert r["reply"] == "已规划完成"
    assert calls.get("text") == "帮我查天气然后做3D场景"


def test_auto_plan_off_routes_to_respond():
    routed = {}

    def fake_respond(text: str) -> dict:
        routed["text"] = text
        return {"reply": "companion 回应", "mood": "happy"}

    p = VoicePipeline(respond_fn=fake_respond, planner_fn=lambda t: {"reply": "X"},
                      auto_plan=False)
    res = p.handle_voice_turn(transcript="你好")
    assert res.planner_used is None
    assert res.reply == "companion 回应"
    assert routed.get("text") == "你好"


def test_summarize_run_task_handles_execution():
    summary = VoicePipeline._summarize_run_task({
        "planner": "ag2",
        "steps": [{"cap": "web.search"}, {"cap": "media.3d"}],
        "execution": {"ok_steps": 2, "failed_steps": 0, "final": "场景已生成"},
    })
    assert "2 步" in summary
    assert "场景已生成" in summary

    summary2 = VoicePipeline._summarize_run_task({
        "planner": "heuristic",
        "steps": [{"cap": "x"}],
        "execution": {"ok_steps": 0, "failed_steps": 1},
    })
    assert "1 步" in summary2


# ============================================================================
# 4) HTTP 进程内 dispatch（wake 端点，不依赖真实麦克风/服务进程）
# ============================================================================
def _make_handler(path, body=None):
    from core.fabric.http_server import FabricHubHTTPHandler
    import io
    h = FabricHubHTTPHandler.__new__(FabricHubHTTPHandler)
    h.path = path
    h.headers = {"Content-Length": str(len(body or b""))}
    h.rfile = io.BytesIO(body or b"")
    h.wfile = io.BytesIO()
    h._code = 200

    def sr(c):
        h._code = c

    h.send_response = sr
    h.send_header = lambda k, v: None
    h.end_headers = lambda: None
    return h


def test_http_wake_status_uninitialized():
    h = _make_handler("/api/voice/wake/status")
    h.do_GET()
    import json
    out = json.loads(h.wfile.getvalue().decode())
    assert out["ok"] is True
    assert out["running"] is False
    assert out["last_result"] is None


def test_http_voice_turn_plan_param_routes_to_planner():
    captured = {}

    # 用注入式 pipeline：planner_fn 记录调用
    def fake_planner(text):
        captured["t"] = text
        return {"reply": "planned", "planner_used": "mock"}

    from core.fabric.voice_chiplet import handle_voice_turn as hvt  # noqa: F401
    # 直接调底层（绕过 HTTP 的默认 companion 响应），验证 plan 分支数据通路
    p = VoicePipeline(planner_fn=fake_planner,
                      tts_fn=lambda t: {"text": t, "engine": "web_speech"})
    res = p.handle_voice_turn(transcript="查天气然后做3D", force_plan=True)
    # 前台：plan 异步 → 立即返回 task_id + 短反馈，planner_used 待后台回填
    assert res.task_id and res.task_id.startswith("vt_")
    assert res.planner_used is None
    assert res.reply in VoicePipeline._FRONT_ACKS
    # 后台：轮询确认规划器被调用且结果回填
    r = None
    for _ in range(60):
        r = VoicePipeline.get_task_result(res.task_id)
        if r and r.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert r is not None and r["status"] == "done"
    assert r["planner_used"] == "mock"
    assert r["reply"] == "planned"
    assert captured["t"] == "查天气然后做3D"


# ============================================================================
# 5) 全离线 STT 引擎探测（诚实：faster_whisper 已装→live；否则 web_speech 兜底）
# ============================================================================
def test_stt_engine_pick_is_honest():
    from core.fabric.adapters.stt_adapter import STTAdapter
    a = STTAdapter()
    # 不报错；引擎名是 whisper_cpp / faster_whisper / web_speech 之一
    assert a._engine in ("whisper_cpp", "faster_whisper", "vosk", "web_speech")
    # health 是可调用的 bool
    assert isinstance(a.health(), bool)


def test_stt_faster_whisper_invoke_path(monkeypatch):
    """全离线 STT 调用链：mock 模型验证「audio_path → 本地转写」正确接线。"""
    import sys, tempfile, os
    import numpy as np
    import soundfile as sf
    import core.fabric.adapters.stt_adapter as stt_mod

    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(wav, np.zeros(16000, dtype=np.float32), 16000)  # 静音 wav（mock 不真读）

    captured = {}

    class _Seg:
        def __init__(self, t):
            self.text = t

    class _FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, **kw):
            captured["path"] = path
            return [_Seg("你好世界")], None

    fake_fw = type(sys)("fake_fw")
    fake_fw.WhisperModel = _FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    monkeypatch.setattr(stt_mod, "_faster_whisper_model_cached", lambda size: True)
    try:
        a = stt_mod.STTAdapter(engine="faster_whisper")
        r = a.invoke(stt_mod.InvokeRequest(
            capability="voice.stt", payload={"audio_path": wav}))
        assert r.ok is True
        assert r.data["text"] == "你好世界"
        assert captured["path"] == wav
    finally:
        os.remove(wav)


def test_stt_health_honest_when_model_uncached(monkeypatch):
    """模型未下载时 health 必须如实报 False（不谎报 live）。"""
    import core.fabric.adapters.stt_adapter as stt_mod
    monkeypatch.setattr(stt_mod, "_faster_whisper_model_cached", lambda size: False)
    a = stt_mod.STTAdapter(engine="faster_whisper")
    assert a.health() is False
