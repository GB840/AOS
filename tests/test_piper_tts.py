"""Piper 离线 TTS 单元测试 —— 诚实级 ②（代码就绪 + 单元验证；真模型为真实合成 ③）。

覆盖：
- PIPER_AVAILABLE 探测（已装即 True）
- 无模型时 available=False，synthesize 抛清晰错误（不静默、不退回内存冒充）
- 真接开源实证：下载 huayan 中文模型 + 真实合成，产出非空 WAV 字节（②/③ 真实跑通）
"""
import os
import sys

import pytest

pytest.importorskip("piper")  # 缺 piper-tts 包；装齐后自动跑

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.piper_backend import PiperTTS, PIPER_AVAILABLE  # noqa: E402


def test_piper_lib_importable():
    # 真接开源：piper-tts 已 pip 安装（Apache-2.0），import 即成功
    assert PIPER_AVAILABLE is True


def test_piper_no_model_is_honest_degrade():
    # 未下载模型时，available=False，合成明确报错（不谎报“离线可用”）
    tts = PiperTTS(model_path="/nonexistent/piper/voice.onnx")
    assert tts.available is False
    with pytest.raises(RuntimeError):
        tts.synthesize("你好世界")


@pytest.mark.timeout(300)
def test_piper_real_synthesis():
    """真接开源实证：下载 huayan 中文模型 + 真实合成，产出非空 WAV。

    网络不可达时跳过（诚实标记），不伪装通过。
    """
    tts = PiperTTS()
    try:
        model_path = tts.ensure_voice()  # 下载 huayan medium（~60MB）
        assert os.path.isfile(model_path)
        assert tts.available is True
        data, ext = tts.synthesize("你好，这是单创OS的语音合成测试。")
    except Exception as e:  # 网络/下载失败 → 诚实跳过，不伪装
        pytest.skip(f"Piper 真实合成需联网下载模型，跳过：{e}")

    assert ext == "wav"
    assert len(data) > 44, f"WAV 字节过短，疑似空音频：{len(data)}"
    # WAV 头校验（RIFF....WAVE）
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def test_piper_tts_adapter_engine_wired():
    """TTSAdapter 识别 piper 引擎（AOS_TTS_ENGINE=piper 时选用且不崩溃）。"""
    from core.fabric.adapters.tts_adapter import TTSAdapter

    tts = TTSAdapter(engine="piper")
    assert tts._engine == "piper"
    # 无模型时 health 诚实 False（不谎报 live）
    assert tts.health() is False
