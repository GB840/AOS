"""Piper 离线语音合成（TTS）—— 真接开源，替代 Fish Speech 禁商用权重。

许可证：Apache-2.0（Michael Hansen / rhasspy），可商用。
项目：rhasspy/piper  | 语音模型：rhasspy/piper-voices (HuggingFace)
官方：https://github.com/rhasspy/piper

设计纪律（对齐 AOS「诚实降级」第一性，参考 vosk_backend.py）：
- 重依赖 `piper` 惰性导入：未安装时 `PIPER_AVAILABLE=False`，`available` 返回 False，
  绝不退回内存冒充、绝不假装“离线合成可用”。
- 语音模型（.onnx + .onnx.json）需下载（中文 huayan medium 约 60MB），
  由 `ensure_voice()` 在首次使用时从 HuggingFace 下载（opt-in，需网络），
  或用户自行放置并设 `AOS_PIPER_VOICE` 指向 .onnx 模型路径。
- 输出 16bit PCM WAV（采样率由模型自带配置决定，通常 16kHz/22.05kHz）。
"""
from __future__ import annotations

import io
import logging
import os
import wave
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import piper  # 重型 ONNX 推理引擎，惰性导入

    PIPER_AVAILABLE = True
except Exception:  # pragma: no cover - 仅在未安装 piper 时触发
    piper = None
    PIPER_AVAILABLE = False


# 默认语音：中文 huayan medium（质量/体积平衡，~60MB，Apache-2.0 模型权重）
_DEFAULT_VOICE = os.environ.get("AOS_PIPER_VOICE_NAME", "zh_CN-huayan-medium")


def _default_voice_dir() -> str:
    return os.environ.get("AOS_PIPER_VOICE_DIR") or os.path.expanduser("~/.cache/piper-voices")


def _voice_model_path(name: str) -> str:
    """给定语音名，返回本地 .onnx 模型路径（config 同名 .onnx.json 同级）。"""
    base = _default_voice_dir()
    return os.path.join(base, name, f"{name}.onnx")


def _hf_url(name: str) -> Tuple[str, str]:
    """构造 HuggingFace piper-voices 下载 URL（标准仓库目录结构）。

    piper-voices 路径：<lang>/<region>/<name>/<quality>/<name>.onnx
    语音名形如 zh_CN-huayan-medium → lang=zh, region=zh_CN, name=zh_CN-huayan, quality=medium
    """
    parts = name.split("-")
    if len(parts) >= 3:
        region = parts[0]
        quality = parts[-1]
        base_name = "-".join(parts[:-1])
        lang = region.split("_")[0]
    else:
        lang = region = base_name = name
        quality = "medium"
    onnx = f"{base_name}-{quality}.onnx"
    url = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        f"{lang}/{region}/{base_name}/{quality}/{onnx}"
    )
    return url, onnx


class PiperTTS:
    """Piper 离线语音合成封装（按需加载语音模型）。"""

    def __init__(self, model_path: Optional[str] = None, voice_name: Optional[str] = None) -> None:
        self.model_path = model_path or os.environ.get("AOS_PIPER_VOICE")
        self.voice_name = voice_name or _DEFAULT_VOICE
        self._voice = None

    # ---- 可用性（如实）----
    @property
    def available(self) -> bool:
        """piper 已装 且 模型存在 → 真能离线合成；否则 False，不谎报。"""
        if not PIPER_AVAILABLE:
            return False
        if not self.model_path or not os.path.isfile(self.model_path):
            return False
        return True

    def health_detail(self) -> dict:
        return {
            "engine": "piper",
            "license": "Apache-2.0",
            "lib_available": PIPER_AVAILABLE,
            "model_path": self.model_path,
            "model_present": bool(self.model_path and os.path.isfile(self.model_path)),
            "ready": self.available,
            "note": "Apache-2.0 离线 TTS（替代 Fish Speech CC-BY-NC-SA 禁商用）；需下载语音模型（中文 huayan ~60MB，首次使用自动下载或设 AOS_PIPER_VOICE）",
        }

    # ---- 模型获取（opt-in 下载）----
    def ensure_voice(self, voice_name: Optional[str] = None, voice_dir: Optional[str] = None) -> str:
        """确保语音模型存在；不存在则从 HuggingFace 下载（需网络）。返回 .onnx 路径。"""
        if self.model_path and os.path.isfile(self.model_path):
            return self.model_path
        name = voice_name or self.voice_name
        base = voice_dir or _default_voice_dir()
        target_onnx = _voice_model_path(name)
        if os.path.isfile(target_onnx):
            self.model_path = target_onnx
            return target_onnx
        url, onnx = _hf_url(name)
        os.makedirs(os.path.dirname(target_onnx), exist_ok=True)
        logger.info("下载 Piper 语音模型 %s（HuggingFace）...", name)
        self._download_file(url, target_onnx)
        # 配置 json 与模型同名，缺失不致命（PiperVoice 会走默认）
        cfg_url = url[: -len(".onnx")] + ".onnx.json"
        cfg_dest = target_onnx[: -len(".onnx")] + ".onnx.json"
        try:
            self._download_file(cfg_url, cfg_dest)
        except Exception as e:  # 配置缺失不致命
            logger.warning("Piper 语音配置下载失败（可忽略）：%s", e)
        self.model_path = target_onnx
        return target_onnx

    @staticmethod
    def _download_file(url: str, dest: str) -> None:
        import urllib.request

        with urllib.request.urlopen(url, timeout=300) as r:
            data = r.read()
        with open(dest, "wb") as fh:
            fh.write(data)

    # ---- 加载（内部）----
    def _load(self):
        if self._voice is None:
            if not self.available:
                raise RuntimeError(
                    "Piper 语音模型缺失：请设 AOS_PIPER_VOICE 指向 .onnx 模型，或调用 ensure_voice() 下载"
                )
            self._voice = piper.PiperVoice.load(self.model_path)  # type: ignore[attr-defined]
        return self._voice

    # ---- 合成 ----
    def synthesize(self, text: str) -> Tuple[bytes, str]:
        """合成文本为 WAV 字节（16bit PCM）。返回 (wav_bytes, 'wav')。"""
        if not PIPER_AVAILABLE:
            raise RuntimeError("piper 未安装：pip install piper-tts")
        voice = self._load()
        buf = io.BytesIO()
        wf = wave.open(buf, "wb")
        try:
            voice.synthesize_wav(text, wf)  # type: ignore[attr-defined]
        finally:
            wf.close()
        return buf.getvalue(), "wav"

    def synthesize_file(self, text: str, wav_path: str) -> dict:
        """合成并写入 WAV 文件。返回 {'text', 'provider':'piper', 'model', 'path'}。"""
        data, ext = self.synthesize(text)
        with open(wav_path, "wb") as fh:
            fh.write(data)
        return {
            "text": text,
            "provider": "piper",
            "model": os.path.basename(self.model_path or ""),
            "path": wav_path,
        }
