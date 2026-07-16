"""VoiceWakeLoop —— 0.3 秒级常驻语音唤醒（AOS 语音芯粒的「耳朵」）。

设计目标（对标 Daisy 的「常驻 VAD + 0.3 秒唤醒」）：
- 后台线程持续监听麦克风，用 **VAD（语音活动检测）** 判断「现在是不是在说话」。
- 检测到说话起点 → 持续累积音频 → 静音超时（尾点）即判定一句话说完 → 触发
  回调（默认跑一次完整语音回合：STT→AOS 能力→TTS）。无需每次按按钮。
- 软件检测延迟 < 10ms（一帧 30ms 音频的处理时间），达标「0.3 秒唤醒」里的
  「听得见就开始」部分（从说话到系统反应 <= 0.3s，硬件/系统延迟另计）。

诚实边界（与 STT/TTS 同款「不谎报」原则）：
- 无麦克风 / sounddevice 无输入设备 → health()=False，start() 返回 False，
  调用方应退回前端 🎤 按钮（浏览器 Web Speech API）。
- webrtcvad 装不上（如沙箱无 gcc）→ 自动用**纯 numpy 能量+过零率 VAD** 兜底，
  质量略低但零依赖、可真跑、可单测。health() 如实标 vad_engine。
- 本模块只负责「听得到、切得准」，真正的识别/理解交给 STTAdapter 与 companion。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 唤醒回调签名：收到一段完整话语的音频(np.float32 mono, 16k) → 任意（一般跑语音回合）
WakeCallback = Callable[[np.ndarray], None]


# ============================================================================
# VAD 实现：优先 webrtcvad，否则 numpy 能量+过零率兜底
# ============================================================================
def numpy_vad(frame: np.ndarray, sample_rate: int = 16000,
              energy_thresh: float = 0.012, zcr_thresh: float = 0.18) -> bool:
    """纯 numpy 语音活动检测（零依赖）。

    frame: 一帧音频(np.float32, 已归一化到 ~[-1,1])。
    用「短时能量」+「过零率」双门限：语音既有能量、又不会过零率过高
    （纯噪声往往能量低或过零率异常高）。返回 True=疑似语音。
    """
    f = np.asarray(frame, dtype=np.float32).ravel()
    if f.size == 0:
        return False
    energy = float(np.sqrt(np.mean(f ** 2)))
    if energy < energy_thresh:
        return False
    # 过零率（符号变化比例）
    signs = (f > 0).astype(np.int8)
    zcr = float(np.mean(np.abs(np.diff(signs))))
    # 语音过零率通常适中；过高（接近 1）多为高频噪声，过低（0）可能是直流/卡顿
    if zcr > zcr_thresh:
        return False
    return True


def make_vad(webrtc_aggressiveness: int = 3):
    """返回 VAD 判定函数 frame(np.float32 mono 16k) -> bool。

    优先 webrtcvad（质量好、专为语音优化）；不可用时返回 numpy_vad 兜底。
    """
    try:
        import webrtcvad  # type: ignore

        v = webrtcvad.Vad(webrtc_aggressiveness)

        def _wv(frame: np.ndarray) -> bool:
            # webrtcvad 要 16-bit PCM、特定采样率(8/16/32/48k)、10/20/30ms 帧
            f = np.clip(np.asarray(frame, dtype=np.float32).ravel(), -1.0, 1.0)
            pcm16 = (f * 32767.0).astype(np.int16).tobytes()
            try:
                return bool(v.is_speech(pcm16, 16000))
            except Exception:
                return numpy_vad(frame, 16000)

        return _wv, "webrtcvad"
    except Exception:
        return numpy_vad, "numpy"


# ============================================================================
# 常驻唤醒循环
# ============================================================================
class VoiceWakeLoop:
    """后台常驻监听：麦克风 → VAD → 切出完整话语 → 触发回调。

    用法：
        loop = VoiceWakeLoop(on_utterance=my_handler)
        if loop.health():
            loop.start()        # 开始常驻监听
        # ... 之后 loop.stop() 停止
    """

    def __init__(
        self,
        on_utterance: Optional[WakeCallback] = None,
        sample_rate: int = 16000,
        device: Optional[int] = None,
        frame_ms: int = 30,
        silence_timeout_ms: int = 600,   # 静音超过此值判定一句话结束
        min_speech_ms: int = 350,        # 一句话最短时长（滤掉咳嗽/杂音）
        max_speech_ms: int = 15000,      # 单句最长（防卡死）
        vad_engine: str = "auto",
    ) -> None:
        self.on_utterance = on_utterance
        self.sample_rate = sample_rate
        self.device = device
        self.frame_ms = frame_ms
        self.silence_timeout_ms = silence_timeout_ms
        self.min_speech_ms = min_speech_ms
        self.max_speech_ms = max_speech_ms
        self.frame_samples = int(sample_rate * frame_ms / 1000)

        self._vad_fn, self._vad_engine = (
            make_vad() if vad_engine == "auto" else (numpy_vad, "numpy")
        )
        self._running = False
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._buf: list[np.ndarray] = []        # 累积音频（用于切出整句）
        self._speaking = False
        self._speech_ms = 0
        self._silence_ms = 0
        self.last_error: Optional[str] = None
        self.total_utterances = 0

    # ---- 可用性 ----
    def health(self) -> bool:
        try:
            import sounddevice as sd  # type: ignore
            idx = self.device if self.device is not None else sd.default.device[0]
            if idx is None:
                return False
            dev = sd.query_devices(idx)
            return int(dev.get("max_input_channels", 0)) > 0
        except Exception as e:  # 无声卡 / PortAudio 未初始化
            self.last_error = f"no audio input device: {e}"
            return False

    def vad_engine_name(self) -> str:
        return self._vad_engine

    @property
    def running(self) -> bool:
        return self._running

    # ---- 控制 ----
    def start(self) -> bool:
        """启动常驻监听。返回是否成功（无声卡则返回 False）。"""
        if self._running:
            return True
        try:
            import sounddevice as sd  # type: ignore
        except Exception as e:
            self.last_error = f"sounddevice unavailable: {e}"
            return False
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                device=self.device,
                channels=1,
                dtype="float32",
                blocksize=self.frame_samples,
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as e:  # 无麦克风 / 设备被占
            self.last_error = f"cannot open input stream: {e}"
            logger.warning("VoiceWakeLoop 启动失败（无麦克风或设备占用）: %s", e)
            return False
        self._running = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()
        logger.info("VoiceWakeLoop 已启动（vad=%s, 采样=%d）", self._vad_engine, self.sample_rate)
        return True

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning("音频流停止/关闭失败（非致命）: %s", e)
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    # ---- 音频回调（音频线程，必须快）----
    def _on_audio(self, indata, frames, t, status):
        if status:
            logger.debug("wake stream status: %s", status)
        chunk = np.asarray(indata, dtype=np.float32).ravel()
        self._detect(chunk)

    # ---- VAD 状态机（在音频线程跑，纯 numpy 很快）----
    def _detect(self, chunk: np.ndarray) -> None:
        # 缓冲由 detect 统一维护（测试直接喂帧也能自洽）
        with self._lock:
            self._buf.append(chunk.copy())
            # 限制缓冲增长（最多保留约 16 秒）
            if len(self._buf) > 600:
                self._buf = self._buf[-600:]
        is_speech = bool(self._vad_fn(chunk))
        if is_speech:
            self._speaking = True
            self._silence_ms = 0
            self._speech_ms += self.frame_ms
            if self._speech_ms >= self.max_speech_ms:
                self._emit()  # 超长强制截断
        else:
            if self._speaking:
                self._silence_ms += self.frame_ms
                if self._silence_ms >= self.silence_timeout_ms and \
                   self._speech_ms >= self.min_speech_ms:
                    self._emit()

    def _emit(self) -> None:
        with self._lock:
            audio = np.concatenate(self._buf) if self._buf else np.zeros(0, np.float32)
            self._buf = []
        was_speaking = self._speaking
        self._speaking = False
        self._speech_ms = 0
        self._silence_ms = 0
        if not was_speaking or audio.size == 0:
            return
        self.total_utterances += 1
        logger.info("wake: 截获一段话语（%.2fs）", audio.size / self.sample_rate)
        if self.on_utterance is not None:
            # 在 worker 线程跑回调，避免阻塞音频回调
            threading.Thread(target=self._safe_cb, args=(audio,), daemon=True).start()

    def _safe_cb(self, audio: np.ndarray) -> None:
        try:
            self.on_utterance(audio)
        except Exception as e:  # 永不崩监听循环
            logger.exception("wake on_utterance 回调异常: %s", e)

    # ---- 主泵（占位，检测在回调里完成；此线程用于未来扩展/保活）----
    def _pump(self) -> None:
        while self._running:
            time.sleep(0.1)


# ============================================================================
# 便捷：把唤醒截获的音频接成一次完整语音回合
# ============================================================================
def make_wake_turn_handler(pipeline=None, user_id: str = "default"):
    """构造 on_utterance 回调：收到音频 → 存 wav → 跑 VoicePipeline 整回合。

    返回 (handler, 最近一次结果容器)，方便测试/前端轮询最近回应。
    """
    from .voice_chiplet import VoicePipeline
    import soundfile as sf
    import tempfile
    import os

    pipe = pipeline or VoicePipeline(user_id=user_id)
    last: dict = {}

    def handler(audio: np.ndarray) -> dict:
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            sf.write(path, audio, 16000)
            res = pipe.handle_voice_turn(audio_path=path)
            out = {
                "ok": res.ok,
                "user_text": res.user_text,
                "reply": res.reply,
                "audio_url": res.audio_url,
                "tts_engine": res.tts_engine,
                "error": res.error,
            }
        finally:
            try:
                os.remove(path)
            except Exception as e:
                logger.warning("临时音频文件清理失败（非致命）: %s", e)
        last.clear()
        last.update(out)
        return out

    handler.last = last  # type: ignore
    return handler, last
