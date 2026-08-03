"""Vosk 离线语音识别（STT）—— 真接开源，非自研等价。

许可证：Apache-2.0（Alpha Cephei），可商用。
官方：https://github.com/alphacep/vosk-api  | 模型：https://alphacephei.com/vosk/models

设计纪律（对齐 AOS「诚实降级」第一性）：
- 重依赖 `vosk` 惰性导入：未安装时 `VOSK_AVAILABLE=False`，`available` 返回 False，
  绝不退回内存冒充、绝不假装“离线识别可用”。
- 模型需下载，由 `ensure_model()` 在首次使用时下载（opt-in，需网络），或用户自行
  放置并设 `AOS_VOSK_MODEL` 指向模型目录；已下载到默认缓存目录的模型会被**自动发现**。
- 默认选**小模型**（中文 vosk-model-small-cn-0.22 约 42MB / 英文
  vosk-model-small-en-us-0.15 约 40MB），对齐母纲原则 7「老人的老机器也要能跑」。
  大模型（vosk-model-cn-0.22 约 1.3GB）识别更准但吃内存，需显式设
  `AOS_VOSK_MODEL_NAME=vosk-model-cn-0.22` 才用。
- 音频须为 16kHz 16bit 单声道 PCM WAV；其它格式由调用方用 ffmpeg 转码。
"""
from __future__ import annotations

import json
import logging
import os
import wave
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import vosk  # 重型 C 扩展，惰性导入

    VOSK_AVAILABLE = True
except Exception:  # pragma: no cover - 仅在未安装 vosk 时触发
    vosk = None
    VOSK_AVAILABLE = False


# 默认模型（按语言）：URL 末段即压缩包名，解压后目录同名。
# 一律取 small 版：低资源老机器友好（母纲原则 7），大模型需显式指定。
_DEFAULT_MODELS = {
    "cn": "vosk-model-small-cn-0.22",   # ~42MB
    "en": "vosk-model-small-en-us-0.15",  # ~40MB
}

# 自动发现时的候选顺序：显式指定 > 小模型 > 大模型（有啥用啥，不强迫再下一次）
_DISCOVER_ORDER = {
    "cn": ["vosk-model-small-cn-0.22", "vosk-model-cn-0.22"],
    "en": ["vosk-model-small-en-us-0.15", "vosk-model-en-us-0.22"],
}


def _default_model_dir() -> str:
    return os.environ.get("AOS_VOSK_MODEL_DIR") or os.path.expanduser("~/.cache/vosk-models")


def _model_cached(model_dir: str, name: str) -> bool:
    return os.path.isdir(os.path.join(model_dir, name))


def discover_model(lang: str = "cn") -> Optional[str]:
    """在默认缓存目录里找已下载的模型目录，找到返回绝对路径，否则 None。

    修复真实缺陷：此前只认 `AOS_VOSK_MODEL` 环境变量，导致 `ensure_model()`
    下载到缓存目录后 `available` 仍报 False（装了却说没装，违反诚实纪律）。
    """
    base = _default_model_dir()
    if not os.path.isdir(base):
        return None
    key = (lang or "cn")[:2]
    names = list(_DISCOVER_ORDER.get(key, []))
    explicit = os.environ.get("AOS_VOSK_MODEL_NAME")
    if explicit:
        names.insert(0, explicit)
    for name in names:
        p = os.path.join(base, name)
        if os.path.isdir(p):
            return p
    # 兜底：目录里任何形如 vosk-model-*<lang>* 的目录都算
    try:
        for entry in sorted(os.listdir(base)):
            if entry.startswith("vosk-model") and key in entry:
                p = os.path.join(base, entry)
                if os.path.isdir(p):
                    return p
    except OSError:
        pass
    return None


class VoskSTT:
    """Vosk 离线语音识别封装（单例式按需加载模型）。"""

    def __init__(self, model_path: Optional[str] = None, lang: str = "cn") -> None:
        self.lang = lang
        # 优先级：显式传入 > 环境变量 > 默认缓存目录里已下载的模型（自动发现）
        self.model_path = (
            model_path
            or os.environ.get("AOS_VOSK_MODEL")
            or discover_model(lang)
        )
        self._model = None

    # ---- 可用性（如实）----
    @property
    def available(self) -> bool:
        """vosk 已装 且 模型目录存在 → 真能离线识别；否则 False，不谎报。"""
        if not VOSK_AVAILABLE:
            return False
        if not self.model_path or not os.path.isdir(self.model_path):
            return False
        return True

    def health_detail(self) -> dict:
        return {
            "engine": "vosk",
            "lib_available": VOSK_AVAILABLE,
            "model_path": self.model_path,
            "model_present": bool(self.model_path and os.path.isdir(self.model_path)),
            "ready": self.available,
            "note": "Apache-2.0 离线 STT；需下载约 40-50MB 模型（首次使用自动下载或设 AOS_VOSK_MODEL）",
        }

    # ---- 模型获取（opt-in 下载）----
    def ensure_model(self, model_dir: Optional[str] = None) -> str:
        """确保模型存在；不存在则下载（需网络）。返回模型目录路径。"""
        if self.model_path and os.path.isdir(self.model_path):
            return self.model_path
        base = model_dir or _default_model_dir()
        os.makedirs(base, exist_ok=True)
        name = os.environ.get("AOS_VOSK_MODEL_NAME") or _DEFAULT_MODELS.get(
            self.lang[:2], _DEFAULT_MODELS["en"])
        target = os.path.join(base, name)
        if _model_cached(base, name):
            self.model_path = target
            return target
        import io
        import urllib.request
        import zipfile

        url = f"https://alphacephei.com/vosk/models/{name}.zip"
        logger.info("下载 Vosk 模型 %s（~40-50MB）...", name)
        data = urllib.request.urlopen(url, timeout=300).read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(base)
        self.model_path = target
        logger.info("Vosk 模型已就绪：%s", target)
        return target

    # ---- 加载（内部）----
    def _load(self):
        if self._model is None:
            if not self.available:
                raise RuntimeError(
                    "Vosk 模型缺失：请设 AOS_VOSK_MODEL 指向模型目录，或调用 ensure_model() 下载"
                )
            self._model = vosk.Model(self.model_path)
        return self._model

    # ---- 转写 ----
    def transcribe_file(self, wav_path: str) -> dict:
        """对一段 WAV 做离线转写，返回 {'text': str, 'provider': 'vosk', 'model': name}。

        要求：16kHz 16bit 单声道 PCM WAV。非此格式由调用方先 ffmpeg 转码。
        """
        if not VOSK_AVAILABLE:
            raise RuntimeError("vosk 未安装：pip install vosk")
        if not os.path.isfile(wav_path):
            raise FileNotFoundError(wav_path)
        model = self._load()
        wf = wave.open(wav_path, "rb")
        try:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                raise RuntimeError("Vosk 需要 16kHz 16bit 单声道 PCM WAV（请先 ffmpeg 转码）")
            rec = vosk.KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)
            result = json.loads(rec.FinalResult())
            return {
                "text": result.get("text", "").strip(),
                "provider": "vosk",
                "model": os.path.basename(self.model_path or ""),
            }
        finally:
            wf.close()
