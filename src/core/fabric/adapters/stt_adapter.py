"""STT 适配器 —— AOS fabric 的 VOICE_STT 平面（语音识别：音频 -> 文本）。

引擎无关契约（对齐 AOS 第一性「不绑定、未来-proof」）：
- whisper_cpp：本地 whisper.cpp CLI（ggml 模型，全离线、8G 可跑）。
- faster_whisper：本地 Python 库（int8 量化，CPU/GPU 皆可）。
- web_speech：浏览器端 Web Speech API 已完成识别，服务端只接收 transcript
  （零服务端依赖、任何环境可用，是诚实的兜底路径）。

重依赖全部惰性导入（import 时零副作用）；health() 如实反映「本服务端此刻
能否真正把音频转成文字」——whisper_cpp 检查二进制+模型，faster_whisper
检查库，web_speech 永远 True（它只收 transcript）。缺引擎不谎报 live。

设计原则（与 threejs_adapter / search_adapter 一致）：
- 纯增量、零新依赖；适配器薄，只把 AOS 调用翻译成引擎原生调用。
- 端云合作：云端 STT 用不了（无 key/无网）就本地 whisper，本地也没有就
  退回 web_speech（浏览器识别），层层兜底。
"""
from __future__ import annotations

import base64
import logging
import os
import subprocess
import tempfile
import threading

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

# 自动探测链：whisper_cpp 二进制 -> faster_whisper 库 -> web_speech(浏览器兜底)。
# 可用 AOS_STT_ENGINE 显式指定；指定后只认该引擎，不回退。
_WHISPER_BIN_CANDIDATES = [
    os.environ.get("AOS_WHISPER_CPP_BIN", ""),
    "whisper-cli",
    "whisper",
    os.path.join("whisper.cpp", "build", "bin", "whisper-cli"),
    os.path.join("whisper.cpp", "build", "bin", "main"),
    os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli"),
]
_WHISPER_MODEL_CANDIDATES = [
    os.environ.get("AOS_WHISPER_MODEL", ""),
    os.path.expanduser("~/whisper.cpp/models/ggml-base.bin"),
    os.path.expanduser("~/whisper.cpp/models/ggml-small.bin"),
]


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    # whisper-cli / whisper 可能是 PATH 里的命令（非文件）
    for p in paths:
        if p and ("/" not in p and "\\" not in p):
            import shutil
            if shutil.which(p):
                return p
    return None


def _hf_cache_dir() -> str:
    return os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface/hub")


def _faster_whisper_model_cached(size: str) -> bool:
    """faster-whisper 把模型缓存为 models--Systran--faster-whisper-<size>。

    仅检查缓存目录是否存在（不触发下载）；不存在即「待下载」→ 诚实 not-ready。
    """
    d = os.path.join(_hf_cache_dir(), f"models--Systran--faster-whisper-{size}")
    return os.path.isdir(d)


def _pick_engine() -> str:
    forced = os.environ.get("AOS_STT_ENGINE")
    if forced:
        return forced
    if _first_existing(_WHISPER_BIN_CANDIDATES) and _first_existing(_WHISPER_MODEL_CANDIDATES):
        return "whisper_cpp"
    try:
        import faster_whisper  # noqa: F401 - 仅探测导入
        return "faster_whisper"
    except Exception:
        return "web_speech"


class STTAdapter(BaseAgentAdapter):
    """语音识别适配器（VOICE_STT）。引擎可配、缺依赖优雅降级。"""

    def __init__(self, engine: str | None = None) -> None:
        self._engine = engine or _pick_engine()
        self._lock = threading.Lock()
        logger.info("STTAdapter: engine=%s", self._engine)

    @property
    def engine_id(self) -> str:
        return "stt"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.VOICE_STT]

    # ---- 引擎可用性（如实）----
    def _whisper_cpp_paths(self):
        binp = _first_existing(_WHISPER_BIN_CANDIDATES)
        modelp = _first_existing(_WHISPER_MODEL_CANDIDATES)
        return binp, modelp

    def health(self) -> bool:
        if self._engine == "whisper_cpp":
            binp, modelp = self._whisper_cpp_paths()
            return bool(binp and modelp)
        if self._engine == "faster_whisper":
            try:
                import faster_whisper  # noqa: F401
                size = os.environ.get("AOS_WHISPER_SIZE", "base")
                return _faster_whisper_model_cached(size)
            except Exception:
                return False
        # web_speech：服务端只收 transcript，永远可用
        return True

    def health_detail(self) -> dict:
        if self._engine == "whisper_cpp":
            binp, modelp = self._whisper_cpp_paths()
            return {
                "engine": "whisper_cpp",
                "bin": binp,
                "model": modelp,
                "ready": bool(binp and modelp),
                "note": "需 whisper.cpp 二进制 + ggml 模型（全离线）",
            }
        if self._engine == "faster_whisper":
            try:
                import faster_whisper  # noqa: F401
                size = os.environ.get("AOS_WHISPER_SIZE", "base")
                cached = _faster_whisper_model_cached(size)
                return {"engine": "faster_whisper", "ready": cached,
                        "model_size": size, "model_cached": cached,
                        "note": "全离线；首次需从 HuggingFace 下载 ggml 模型（约 75-150MB）"}
            except Exception as e:
                return {"engine": "faster_whisper", "ready": False, "error": repr(e)}
        return {"engine": "web_speech", "ready": True,
                "note": "浏览器已完成识别，服务端只收 transcript"}

    # ---- 执行 ----
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        # 浏览器路径：前端已用 Web Speech 转好文字，直接透传
        transcript = (payload.get("transcript") or "").strip()
        if transcript:
            return InvokeResult(ok=True, data={"text": transcript, "engine": "web_speech"})

        # 服务端路径：需真正把音频转文字
        if self._engine == "web_speech":
            return InvokeResult(
                ok=False,
                error="web_speech 引擎无法在服务端识别音频；"
                      "请由浏览器 Web Speech API 识别后传 transcript 字段。",
            )

        audio_path = payload.get("audio_path")
        audio_b64 = payload.get("audio_b64")
        if not audio_path and audio_b64:
            try:
                suffix = payload.get("audio_suffix", "wav")
                fd, audio_path = tempfile.mkstemp(suffix="." + suffix.lstrip("."))
                with os.fdopen(fd, "wb") as fh:
                    fh.write(base64.b64decode(audio_b64))
            except Exception as e:
                return InvokeResult(ok=False, error=f"音频解码失败: {e}")

        if not audio_path or not os.path.isfile(audio_path):
            return InvokeResult(ok=False, error="STT 需要 audio_path 或 audio_b64")

        try:
            if self._engine == "whisper_cpp":
                text = self._run_whisper_cpp(audio_path)
            else:
                text = self._run_faster_whisper(audio_path)
        except Exception as e:
            return InvokeResult(ok=False, error=f"STT 执行失败: {e}")
        finally:
            # 仅清理我们临时写的文件
            if audio_b64 and audio_path and os.path.isfile(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

        if not text or not text.strip():
            return InvokeResult(ok=False, error="STT 未识别出文本")
        return InvokeResult(ok=True, data={"text": text.strip(), "engine": self._engine})

    # ---- 流式识别（边说边出字）----
    def supports_streaming(self) -> bool:
        """是否真·流式：faster_whisper 原生 segment 流式；whisper_cpp 退化整段；web_speech 不适用。"""
        return self._engine in ("faster_whisper", "whisper_cpp")

    def stream_transcribe(self, audio_path: str, language: str = "zh") -> "Iterator[str]":
        """流式转写：对一段音频边识别边 yield 部分文本（Iterator[str]）。

        - faster_whisper：transcribe() 返回 segment 生成器，天然流式 → 每句 yield 一次。
        - whisper_cpp：无原生实时增量 → 整段识别后 yield 一次（接口一致但非真流式）。
        - web_speech：无音频输入，不支持 → 抛错（应改用 transcript 直传）。

        上层（http SSE / 前端分段录音）对每段音频调一次本方法，累积 partial 即「边说边出字」。
        """
        if not audio_path or not os.path.isfile(audio_path):
            raise RuntimeError("stream_transcribe 需要已落盘的 audio_path")
        if self._engine == "web_speech":
            raise RuntimeError("web_speech 无音频输入，不支持流式；请浏览器识别后传 transcript")
        if self._engine == "faster_whisper":
            from faster_whisper import WhisperModel
            model = WhisperModel(os.environ.get("AOS_WHISPER_SIZE", "base"),
                                 device=os.environ.get("AOS_WHISPER_DEVICE", "cpu"))
            for seg in model.transcribe(audio_path, language=language, beam_size=5):
                text = (seg.text or "").strip()
                if text:
                    yield text
        else:  # whisper_cpp 退化：整段后 yield 一次
            full = self._run_whisper_cpp(audio_path)
            if full and full.strip():
                yield full.strip()

    # ---- 引擎实现（重依赖惰性导入）----
    def _run_whisper_cpp(self, audio_path: str) -> str:
        binp, modelp = self._whisper_cpp_paths()
        if not binp or not modelp:
            raise RuntimeError("whisper_cpp 二进制或模型缺失")
        cmd = [binp, "-m", modelp, "-f", audio_path,
               "--no-timestamps", "-l", "zh", "-nt"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:300] or "whisper_cpp 非零退出")
        # 去掉时间戳与空白行，拼成纯文本
        lines = [ln.strip() for ln in proc.stdout.splitlines()
                 if ln.strip() and not ln.strip().startswith("[")]
        return " ".join(lines)

    def _run_faster_whisper(self, audio_path: str) -> str:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.environ.get("AOS_WHISPER_SIZE", "base"),
                             device=os.environ.get("AOS_WHISPER_DEVICE", "cpu"))
        segs, _ = model.transcribe(audio_path, language="zh", beam_size=5)
        return " ".join(s.text for s in segs).strip()
