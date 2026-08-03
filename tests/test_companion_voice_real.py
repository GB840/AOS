"""Tier 0 方言语音陪伴通道 · ②级实证测试（不连外网、不 mock 体征）。

验证 CompanionVoice：
- 入口不再因云版依赖(pydantic_settings)缺失而崩溃；
- 可用性如实反映「此刻真能跑」，不误报离线可用；
- 方言路由真派发到注入后端、不可用则诚实给落地命令、绝不冒充；
- 听/说在缺模型时仍走本地链路不崩、说永远降级到浏览器兜底保证陪伴不中断；
- 方言 TTS 音色映射只覆盖已核实的，不冒充未核实方言。
"""
import os
import wave

import pytest

from voice import CompanionVoice
from core.fabric.adapters.vosk_backend import VoskSTT
from kernel.dialect_asr import DialectASR


def _silence_wav(path: str, seconds: int = 1) -> str:
    """生成一段 16k 16bit 单声道静音 wav（vosk 要求格式），用于本地链路实证。"""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * (16000 * 2 * seconds))
    return path


def test_voice_import_no_longer_crashes():
    """修复真实缺陷：云版 asr.py 硬依赖 utils.config(pydantic_settings)，
    缺依赖时整个 voice 包 import 崩溃。现在默认只导 CompanionVoice（本地优先）。"""
    import voice
    assert "CompanionVoice" in voice.__all__
    cv = CompanionVoice()
    assert isinstance(cv, CompanionVoice)


def test_health_reflects_reality_not_wishful():
    """诚实分级硬纪律：health() 的 local_stt_ready / offline_capable 必须反映真实，
    不能因为『引擎库装了』就谎报离线可用。"""
    cv = CompanionVoice()
    h = cv.health()
    # local_stt_ready 必须等于 Vosk 真实可用性
    assert h["local_stt_ready"] == VoskSTT().available
    # offline_capable 不能以引擎名为准，必须以 tts 真实 health() 为准
    assert h["offline_capable"] == bool(
        h["local_stt_ready"] and h["tts_ready"]
        and h["tts_engine"] in ("piper", "kokoro", "web_speech"))
    # dialects_local 是此刻真能识别的（无模型环境应为空）
    if not h["local_stt_ready"]:
        assert h["dialects_local"] == []


def test_listen_missing_file_is_honest():
    cv = CompanionVoice()
    res = cv.listen("/nonexistent/path.wav")
    assert res["ok"] is False
    assert "不存在" in res["error"]


def test_listen_silent_wav_runs_local_not_crash(tmp_path):
    """本地链路真实跑通（沙箱若装了 vosk 模型则真加载识别），不崩、不冒充。"""
    wav = _silence_wav(os.path.join(tmp_path, "s.wav"))
    cv = CompanionVoice()
    res = cv.listen(wav)
    assert isinstance(res, dict)
    assert "ok" in res
    # 若本地 STT 真的就绪，应走本地分支（带 local 标记）；静音无文本则诚实失败
    if cv.health()["local_stt_ready"]:
        assert "local" in res  # 走了 Vosk 本地分支
        # 静音识别不出文本 → 诚实 ok=False（不谎报成功）
        assert res["ok"] is False


def test_dialect_routing_dispatches_to_injected_backend(tmp_path):
    """方言真路由：把后端注入，验证 listen 按方言派发到正确引擎并返回其文本。"""
    def _fake_vosk(path, dialect):
        return "上海话测试文本"
    cv = CompanionVoice()
    cv._dialect = DialectASR(backends={"vosk": _fake_vosk})
    wav = _silence_wav(os.path.join(tmp_path, "s.wav"))
    res = cv.listen(wav, dialect="官话-北京")
    assert res["ok"] is True
    assert res["text"] == "上海话测试文本"
    assert res["engine"] == "vosk"
    assert res["local"] is True


def test_dialect_unavailable_is_honest_not_impersonated(tmp_path):
    """方言不可用（注入空后端）→ 诚实返回失败 + 落地命令，绝不静默换普通话冒充。"""
    cv = CompanionVoice()
    cv._dialect = DialectASR(backends={})  # 无任何可用引擎
    wav = _silence_wav(os.path.join(tmp_path, "s.wav"))
    res = cv.listen(wav, dialect="粤语")  # cloud_asr 默认 False
    assert res["ok"] is False
    assert "plan" in res  # 给了照敲的落地路径
    assert "error" in res


def test_speak_never_silences_companion():
    """陪伴不中断：无论本地 TTS 模型在不在，speak 至少能走到浏览器朗读兜底返回 ok。"""
    cv = CompanionVoice()
    res = cv.speak("你好")
    assert res["ok"] is True
    assert res["engine"] in ("piper", "kokoro", "edge_tts", "web_speech")
    # web_speech 兜底时标记 local=True（前端浏览器朗读，不依赖网络/服务）
    if res.get("fallback") == "web_speech":
        assert res["local"] is True


def test_speak_dialect_voice_mapping_honest():
    """方言 TTS 音色映射只覆盖已核实的；未核实方言退回默认且不冒充。"""
    cv = CompanionVoice()
    voice_yue, is_yue = cv._tts_voice_for("粤语")
    assert is_yue is True
    assert voice_yue == "zh-HK-WanLungNeural"
    # 吴/闽/客/赣/湘/晋 等 edge_tts 无真方言 voice → 不映射，诚实退回默认
    for d in ("吴语-太湖(上海话)", "闽语-闽南(厦门/台语)", "客家话",
              "赣语", "湘语-长益", "晋语"):
        v, mapped = cv._tts_voice_for(d)
        assert mapped is False
        assert v == cv._tts_voice_for(None)[0]  # 退回默认普通话音色


def test_capabilities_shape():
    cv = CompanionVoice()
    caps = cv.capabilities()
    for key in ("listen_local", "speak_offline", "speak_free_online",
                "speak_browser_fallback", "dialects_listen",
                "dialects_speak_mapped", "offline_capable"):
        assert key in caps
    # 映射覆盖的音色集合与 companion 内部常量一致
    assert set(caps["dialects_speak_mapped"]) == {
        "粤语", "官话-东北", "官话-中原", "官话-西南"}
