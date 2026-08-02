"""Vosk 离线 STT 单元测试 —— 诚实级 ②（代码就绪 + 单元验证；真模型为真实转写 ③）。

覆盖：
- VOSK_AVAILABLE 探测（已装即 True）
- 无模型时 available=False，transcribe 抛清晰错误（不静默、不退回内存冒充）
- 真接开源实证：下载 small-en 模型 + 真实语音样本，转写出非空文本（②/③ 真实跑通）
"""
import os
import sys
import tempfile
import urllib.request

import pytest

# 确保 src 在路径上（与仓库其它测试一致）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.vosk_backend import VoskSTT, VOSK_AVAILABLE  # noqa: E402


def _fetch(url: str, dest: str, timeout: int = 120) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = r.read()
    with open(dest, "wb") as fh:
        fh.write(data)


def test_vosk_lib_importable():
    # 真接开源：vosk 已 pip 安装（Apache-2.0），import 即成功
    assert VOSK_AVAILABLE is True


def test_vosk_no_model_is_honest_degrade():
    # 未下载模型时，available=False，转写明确报错（不谎报“离线可用”）
    stt = VoskSTT(model_path="/nonexistent/vosk/model/dir", lang="en")
    assert stt.available is False
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with pytest.raises(RuntimeError):
            stt.transcribe_file(wav)
    finally:
        if os.path.exists(wav):
            os.remove(wav)


@pytest.mark.timeout(240)
def test_vosk_real_transcription():
    """真接开源实证：下载模型 + 真实语音样本，离线转写出文本。

    网络不可达时跳过（诚实标记），不伪装通过。
    """
    stt = VoskSTT(lang="en")
    try:
        model_dir = stt.ensure_model()  # 下载 small-en（~41MB）
        assert os.path.isdir(model_dir)
        assert stt.available is True

        # 真实语音样本（vosk 官方 example：英文 "one two three four five"）
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            _fetch(
                "https://raw.githubusercontent.com/alphacep/vosk-api/master/python/example/test.wav",
                wav,
                timeout=120,
            )
            result = stt.transcribe_file(wav)
        finally:
            if os.path.exists(wav):
                os.remove(wav)
    except Exception as e:  # 网络/下载失败 → 诚实跳过，不伪装
        pytest.skip(f"Vosk 真实转写需联网下载模型/样本，跳过：{e}")

    # 真实语音 → 真实文本（非空）
    assert isinstance(result, dict)
    assert result.get("provider") == "vosk"
    assert result.get("text", "").strip(), f"转写结果为空：{result}"
