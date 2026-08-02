"""TTS 适配器 —— AOS fabric 的 VOICE_TTS 平面（语音合成：文本 -> 音频）。

引擎无关契约（对齐 AOS 第一性「不绑定、未来-proof」）：
- edge_tts：微软云端 TTS（免费、中文音色好、需联网；国内一般可达）。
- kokoro：本地神经网络 TTS（pip install kokoro，全离线、质量高）。
- xtts：Coqui XTTS-v2（本地、支持多语/克隆，体积大）。
- web_speech：浏览器 speechSynthesis 朗读，服务端只回文本（零依赖兜底）。

重依赖全部惰性导入；health() 如实反映引擎是否真能合成音频。
缺引擎不谎报 live——companion 前端会改用浏览器 speechSynthesis 兜底。

输出：合成成功写入 AOS_VOICE_AUDIO_DIR（默认 data/workspaces/fabric/voice_audio/），
返回 {text, audio_url, audio_path, engine}；web_speech 则返回 {text, engine:"web_speech"}，
audio_url=None，由前端朗读。
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading

from typing import Iterator

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

_AUDIO_DIR = os.environ.get(
    "AOS_VOICE_AUDIO_DIR",
    os.path.join("data", "workspaces", "fabric", "voice_audio"),
)


def _audio_dir() -> str:
    os.makedirs(_AUDIO_DIR, exist_ok=True)
    return _AUDIO_DIR


def _safe_async_run(coro):
    """安全地在同步上下文中运行协程：如果已有事件循环在运行则创建新循环在线程中执行。"""
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 已在事件循环中（如 asyncio.to_thread），在新线程中创建独立循环
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def _pick_engine() -> str:
    forced = os.environ.get("AOS_TTS_ENGINE")
    if forced:
        return forced
    try:
        import kokoro  # noqa: F401
        return "kokoro"
    except Exception as e:
        logger.warning("kokoro 引擎不可用，尝试下一引擎: %s", e)
    try:
        import piper  # noqa: F401 - Apache-2.0 离线 TTS，无网络依赖
        return "piper"
    except Exception as e:
        logger.warning("piper 引擎不可用，尝试下一引擎: %s", e)
    try:
        import edge_tts  # noqa: F401
        return "edge_tts"
    except Exception:
        return "web_speech"


class TTSAdapter(BaseAgentAdapter):
    """语音合成适配器（VOICE_TTS）。引擎可配、缺依赖优雅降级。"""

    def __init__(self, engine: str | None = None) -> None:
        self._engine = engine or _pick_engine()
        self._lock = threading.Lock()
        logger.info("TTSAdapter: engine=%s", self._engine)

    @property
    def engine_id(self) -> str:
        return "tts"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.VOICE_TTS]

    def health(self) -> bool:
        if self._engine == "web_speech":
            return True
        if self._engine == "edge_tts":
            try:
                import edge_tts  # noqa: F401
                return True
            except Exception:
                return False
        if self._engine == "kokoro":
            try:
                import kokoro  # noqa: F401
                return True
            except Exception:
                return False
        if self._engine == "xtts":
            try:
                import TTS  # noqa: F401
                return True
            except Exception:
                return False
        if self._engine == "piper":
            try:
                from .piper_backend import PIPER_AVAILABLE

                if not PIPER_AVAILABLE:
                    return False
                # 模型存在才真能合成；仅装库无模型 → 诚实 False
                mp = os.environ.get("AOS_PIPER_VOICE")
                if mp and os.path.isfile(mp):
                    return True
                from .piper_backend import _DEFAULT_VOICE, _voice_model_path

                return os.path.isfile(_voice_model_path(_DEFAULT_VOICE))
            except Exception:
                return False
        return False

    def health_detail(self) -> dict:
        ok = self.health()
        return {
            "engine": self._engine,
            "ready": ok,
            "note": ("web_speech=浏览器朗读兜底" if self._engine == "web_speech"
                     else f"{self._engine} 需对应库/模型"),
        }

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        text = (payload.get("text") or payload.get("prompt") or "").strip()
        if not text:
            return InvokeResult(ok=False, error="TTS 需要 text")
        # 浏览器兜底：只回文本，由前端 speechSynthesis 朗读
        if self._engine == "web_speech":
            return InvokeResult(ok=True, data={"text": text, "engine": "web_speech",
                                               "audio_url": None})
        try:
            audio_bytes, ext = self._synthesize(text, payload)
        except Exception as e:
            return InvokeResult(ok=False, error=f"TTS 合成失败({self._engine}): {e}")

        # 落盘并返回可访问 URL
        digest = hashlib.sha256((self._engine + "|" + text).encode("utf-8")).hexdigest()[:16]
        fname = f"{digest}.{ext}"
        fpath = os.path.join(_audio_dir(), fname)
        with self._lock:
            with open(fpath, "wb") as fh:
                fh.write(audio_bytes)
        return InvokeResult(ok=True, data={
            "text": text,
            "engine": self._engine,
            "audio_path": fpath,
            "audio_url": f"/api/voice/audio/{digest}.{ext}",
        })

    # ---- 流式合成（边生成边播放）----
    def supports_streaming(self) -> bool:
        """是否真·流式：edge_tts / kokoro 原生 chunk 流式；web_speech / xtts 退化整段。"""
        return self._engine in ("edge_tts", "kokoro")

    def stream_synthesize(self, text: str, payload: dict | None = None) -> "Iterator[tuple[bytes, str]]":
        """流式合成：边生成边 yield (audio_chunk_bytes, ext)。

        - edge_tts：comm.stream() 是 audio chunk 生成器（真流式）。
        - kokoro：pipeline() 是句子生成器（真流式）。
        - web_speech / xtts：退化整段 yield 一次。

        上层（http SSE / 前端）拿到 chunk 后立即推给客户端播放 → 「边生成边播」。
        """
        payload = payload or {}
        if not text or not text.strip():
            return
        if self._engine == "edge_tts":
            for data in self._stream_edge_tts(text, payload):
                yield (data, "mp3")
        elif self._engine == "kokoro":
            for data in self._stream_kokoro(text, payload):
                yield (data, "wav")
        else:  # web_speech / xtts 退化整段
            audio, ext = self._synthesize(text, payload)
            yield (audio, ext)

    def _stream_edge_tts(self, text: str, payload: dict):
        """edge_tts 异步 audio chunk 生成器 → 同步 Iterator[bytes]。"""
        import asyncio
        import edge_tts
        voice = payload.get("voice") or os.environ.get("AOS_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
        loop = asyncio.new_event_loop()
        comm = edge_tts.Communicate(text, voice)

        async def _agen():
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        agen = _agen()
        try:
            while True:
                data = loop.run_until_complete(agen.__anext__())
                yield data
        except StopAsyncIteration:
            pass
        finally:
            loop.close()

    def _stream_kokoro(self, text: str, payload: dict):
        """kokoro 句子生成器 → 每句 wav bytes。"""
        from kokoro import KPipeline
        import io
        import soundfile as sf
        lang = payload.get("lang", "z")
        voice = payload.get("voice") or os.environ.get("AOS_TTS_VOICE", "zf_001")
        pipeline = KPipeline(lang_code=lang)
        for _, _, audio in pipeline(text, voice=voice):
            buf = io.BytesIO()
            sf.write(buf, audio, 24000)
            yield buf.getvalue()

    # ---- 引擎实现（重依赖惰性导入）----
    def _synthesize(self, text: str, payload: dict) -> tuple[bytes, str]:
        if self._engine == "edge_tts":
            return self._run_edge_tts(text, payload), "mp3"
        if self._engine == "kokoro":
            return self._run_kokoro(text, payload), "wav"
        if self._engine == "xtts":
            return self._run_xtts(text, payload), "wav"
        if self._engine == "piper":
            return self._run_piper(text, payload), "wav"
        raise RuntimeError(f"未知 TTS 引擎 {self._engine}")

    def _run_piper(self, text: str, payload: dict) -> bytes:
        """Piper 离线 TTS（Apache-2.0，替代 Fish Speech 禁商用权重）。

        已有模型则直接合成；无模型则 opt-in 尝试从 HuggingFace 下载
        （需网络，主机稳定网络可跑），下载失败报清晰错误，不静默、不冒充。
        """
        from .piper_backend import PiperTTS

        model_path = payload.get("model_path") or os.environ.get("AOS_PIPER_VOICE")
        voice_name = payload.get("voice_name") or os.environ.get("AOS_PIPER_VOICE_NAME")
        tts = PiperTTS(model_path=model_path, voice_name=voice_name)
        if not tts.available:
            try:
                tts.ensure_voice()
            except Exception as e:
                raise RuntimeError(
                    f"Piper 语音模型缺失且自动下载失败：{e}"
                    "（请设 AOS_PIPER_VOICE 指向 .onnx 或确保联网）"
                )
        data, _ext = tts.synthesize(text)
        return data

    def _run_edge_tts(self, text: str, payload: dict) -> bytes:
        import edge_tts
        voice = payload.get("voice") or os.environ.get(
            "AOS_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
        comm = edge_tts.Communicate(text, voice)
        # 收集到内存字节流（不落临时文件）
        import io
        buf = io.BytesIO()
        async def _save():
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
        # 使用 _safe_async_run 避免在已有事件循环中调用 asyncio.run() 导致 RuntimeError
        _safe_async_run(_save())
        return buf.getvalue()

    def _run_kokoro(self, text: str, payload: dict) -> bytes:
        from kokoro import KPipeline
        import soundfile as sf
        import io
        lang = payload.get("lang", "z")
        voice = payload.get("voice") or os.environ.get("AOS_TTS_VOICE", "zf_001")
        pipeline = KPipeline(lang_code=lang)
        buf = io.BytesIO()
        # Kokoro 返回生成器；取第一句音频写入 wav 缓冲
        for _, _, audio in pipeline(text, voice=voice):
            sf.write(buf, audio, 24000)
            break
        return buf.getvalue()

    def _run_xtts(self, text: str, payload: dict) -> bytes:
        from TTS.api import TTS
        import soundfile as sf
        import io
        model = os.environ.get("AOS_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
        tts = TTS(model_name=model, progress_bar=False, gpu=False)
        wav = tts.tts(text=text, speaker_wav=payload.get("speaker_wav"),
                      language=payload.get("language", "zh"))
        buf = io.BytesIO()
        sf.write(buf, wav, 24000)
        return buf.getvalue()
