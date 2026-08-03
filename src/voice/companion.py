"""Tier 0 方言语音陪伴通道 —— 本地优先 · 方言平等 · 断网可跑（肉体层 embodiment 首选载体）。

对齐（全局第一性）：
- 母纲「让 AI 不再收割老百姓，而是陪伴老百姓」；原则 7「技术普惠 · 方言平等」；
  不收割四条硬检验①「断网检验」：不联网、不付费，方言识别 + 语音陪伴也要能跑。
- 九大理念 9「可验证即真理」：所有可用性以「此刻真能跑」为准，不可用就明说 + 给落地命令，
  绝不静默退回普通话模型 / 用云 API 冒充本地可用。

复用（铁律二：现有够好 → 不造）：
- core.fabric.adapters.vosk_backend.VoskSTT  —— Apache-2.0 离线 STT（40-50MB 小模型，老机器可跑）
- kernel.dialect_asr.DialectASR             —— 方言真路由（funasr 覆盖 7 大方言 / vosk 覆盖普通话）
- core.fabric.adapters.tts_adapter.TTSAdapter —— 引擎真探测：piper/kokoro 全离线 > edge_tts(免费需联网) > web_speech(浏览器兜底)

设计纪律：
- 本模块导入**零副作用、零网络**；重依赖（vosk/funasr/edge_tts/kokoro/piper）全部惰性导入。
- 默认本地优先：listen 默认 Vosk（或方言经 DialectASR 派到本地引擎）；speak 默认离线 TTS。
- 云 API（百度/讯飞/智谱）**不进默认路径**：仅当 CompanionVoice(cloud_asr=True) 且本地失败才兜底，
  且不挡本地默认、不谎报「离线可用」。
- 不依赖 utils.config / pydantic_settings（云版 asr.py 的坑），只用 os.environ + 本地底座。
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Tuple

from core.fabric.adapters.vosk_backend import VoskSTT
from core.fabric.adapters.tts_adapter import TTSAdapter
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from kernel.dialect_asr import DialectASR

logger = logging.getLogger(__name__)

# 方言 → edge_tts 音色（仅含已核实存在的；其余退回默认普通话音色 + 诚实标记）。
# 诚实边界：edge_tts 只有「地区口音版普通话(辽/陕) + 粤语(港) + 台湾国语」，
# 没有吴/闽/客/赣/湘/晋等真方言 voice；这些方言的 TTS 目前无免费离线方案，不冒充。
# 已联网核实（2026-08）：zh-CN-liaoning-XiaobeiNeural / zh-CN-shaanxi-XiaoniNeural /
# zh-HK-WanLungNeural 均为真实可用 voice；其余方言直接退回默认，不脑补 voice 名。
_EDGE_DIALECT_VOICES: Dict[str, str] = {
    "粤语": "zh-HK-WanLungNeural",
    "官话-东北": "zh-CN-liaoning-XiaobeiNeural",
    "官话-中原": "zh-CN-shaanxi-XiaoniNeural",
    "官话-西南": "zh-CN-shaanxi-XiaoniNeural",
}

_DEFAULT_VOICE = os.environ.get("AOS_TTS_VOICE", "zh-CN-XiaoxiaoNeural")


class CompanionVoice:
    """本地优先的方言语音陪伴通道。

    把「耳朵(Vosk/方言 ASR)」和「嘴巴(TTS)」拼成一个断网可跑、方言平等的陪伴接口。
    它是肉体层 embodiment 的 Tier 0 首选载体，不依赖任何重外部服务（云 API 仅 opt-in 兜底）。
    """

    def __init__(self, lang: str = "cn", tts_engine: Optional[str] = None,
                 cloud_asr: bool = False) -> None:
        self.lang = lang
        self._vosk = VoskSTT(lang=lang)            # 惰性；available 诚实探测
        self._dialect = DialectASR()               # 方言真路由
        self._tts = TTSAdapter(engine=tts_engine)  # 引擎真探测
        self._cloud_asr = bool(cloud_asr)

    # ------------------------------------------------------------------
    # 听（ASR + 方言路由）
    # ------------------------------------------------------------------
    def listen(self, audio_path: str, dialect: Optional[str] = None) -> Dict[str, object]:
        """音频(16k 16bit 单声道 wav) → 文字。

        优先级：方言路由(本地引擎) > Vosk 本地普通话 > 云兜底(仅显式开启)。
        任何一层不可用都诚实返回 error + plan，绝不冒充。
        """
        if not audio_path or not os.path.isfile(audio_path):
            return {"ok": False, "error": "audio_path 不存在，无法识别"}

        # 1) 方言路由（本地优先：funasr 覆盖 7 大方言 / vosk 覆盖普通话）
        if dialect:
            res = self._dialect.transcribe(audio_path, dialect)
            if res.get("ok"):
                return {"ok": True, "text": res["text"], "engine": res["engine"],
                        "dialect": dialect, "local": True}
            if not self._cloud_asr:
                return {"ok": False, "dialect": dialect,
                        "error": res.get("error", "该方言此刻无可用本地引擎"),
                        "plan": res.get("plan")}

        # 2) 默认 Vosk 本地（普通话 / 官话-北京）
        if self._vosk.available:
            try:
                r = self._vosk.transcribe_file(audio_path)
                text = (r.get("text") or "").strip()
                if text:
                    return {"ok": True, "text": text, "engine": "vosk",
                            "dialect": dialect or "官话-北京", "local": True}
                if not self._cloud_asr:
                    return {"ok": False, "error": "Vosk 未识别出文本（音频可能无声或含噪声）",
                            "local": True}
            except Exception as e:
                if not self._cloud_asr:
                    return {"ok": False, "error": f"Vosk 本地识别失败: {e}", "local": True}

        # 3) 云兜底（仅显式开启，且不挡本地默认）
        if self._cloud_asr:
            return self._cloud_listen(audio_path)

        return {"ok": False,
                "error": "本地语音识别不可用（未装 vosk/未下模型，且未开启云兜底）",
                "plan": self._local_plan()}

    def _cloud_listen(self, audio_path: str) -> Dict[str, object]:
        """云 ASR 兜底（百度/讯飞）。惰性 import 旧云版；缺依赖/缺密钥则诚实跳过。"""
        try:
            from .asr import ASREngine
        except Exception as e:                       # 缺 pydantic_settings 等
            return {"ok": False, "error": f"云 ASR 兜底不可用（依赖缺失）: {e}"}
        try:
            eng = ASREngine()
            with open(audio_path, "rb") as fh:
                audio = fh.read()
            r = eng.recognize(audio)
            if r.get("success"):
                return {"ok": True, "text": r["text"], "engine": r.get("provider"),
                        "dialect": None, "local": False}
            return {"ok": False, "error": r.get("error", "云 ASR 失败")}
        except Exception as e:
            return {"ok": False, "error": f"云 ASR 兜底调用失败: {e}"}

    # ------------------------------------------------------------------
    # 说（TTS + 方言音色）
    # ------------------------------------------------------------------
    def speak(self, text: str, dialect: Optional[str] = None) -> Dict[str, object]:
        """文字 → 音频。

        引擎优先级（TTSAdapter 真探测）：piper/kokoro 全离线 > edge_tts(免费需联网) >
        web_speech(浏览器朗读兜底)。dialect 指定时选已核实的方言音色，否则默认普通话。
        选中引擎实际不健康（如 piper 库在但模型缺）时，降级到 web_speech 浏览器朗读，
        保证「陪伴不中断」——绝不因 TTS 模型缺失让整轮静音。
        """
        if not text or not text.strip():
            return {"ok": False, "error": "speak 需要 text"}
        voice, is_dialect_voice = self._tts_voice_for(dialect)
        payload: Dict[str, object] = {"text": text}
        if voice:
            payload["voice"] = voice
        res = self._invoke_tts(payload)
        if res["ok"]:
            res["dialect"] = dialect
            res["dialect_voice"] = is_dialect_voice
            return res
        # 降级：浏览器朗读兜底，保证陪伴不中断（web_speech 始终可用且不依赖网络）
        if self._tts._engine != "web_speech":
            try:
                fb = TTSAdapter(engine="web_speech")
                r2 = fb.invoke(InvokeRequest(
                    capability=Capability.VOICE_TTS, payload=payload))
                if r2.ok:
                    data = r2.data or {}
                    return {"ok": True, "text": text, "engine": data.get("engine"),
                            "audio_path": data.get("audio_path"),
                            "audio_url": data.get("audio_url"),
                            "dialect": dialect, "dialect_voice": is_dialect_voice,
                            "local": True, "fallback": "web_speech"}
            except Exception:
                pass
        res["dialect"] = dialect
        res["dialect_voice"] = is_dialect_voice
        return res

    def _invoke_tts(self, payload: Dict[str, object]) -> Dict[str, object]:
        """调当前 TTS 引擎，统一成 CompanionVoice 的结果形状。"""
        try:
            res = self._tts.invoke(InvokeRequest(
                capability=Capability.VOICE_TTS, payload=payload))
        except Exception as e:
            return {"ok": False, "error": f"TTS 合成失败: {e}"}
        if not res.ok:
            return {"ok": False, "error": res.error}
        data = res.data or {}
        engine = data.get("engine")
        return {"ok": True, "text": payload.get("text"), "engine": engine,
                "audio_path": data.get("audio_path"), "audio_url": data.get("audio_url"),
                "local": engine in ("piper", "kokoro", "web_speech")}

    def _tts_voice_for(self, dialect: Optional[str]) -> Tuple[str, bool]:
        if dialect and dialect in _EDGE_DIALECT_VOICES:
            return _EDGE_DIALECT_VOICES[dialect], True
        return _DEFAULT_VOICE, False

    # ------------------------------------------------------------------
    # 诚实可用性
    # ------------------------------------------------------------------
    def health(self) -> Dict[str, object]:
        dialects = self._dialect.supported_dialects()
        tts_engine = self._tts._engine
        tts_ready = self._tts.health()
        return {
            "local_stt_ready": self._vosk.available,
            "dialects_local": dialects,
            "tts_engine": tts_engine,
            "tts_ready": tts_ready,
            "offline_capable": bool(
                self._vosk.available and tts_ready
                and tts_engine in ("piper", "kokoro", "web_speech")),
            "cloud_asr_enabled": self._cloud_asr,
            "note": "本地优先；断网可跑需要 vosk 模型 + piper/kokoro 均就绪",
        }

    def capabilities(self) -> Dict[str, object]:
        """给前端的诚实能力清单：哪些能断网跑、哪些方言能听/能说。"""
        h = self.health()
        return {
            "listen_local": h["local_stt_ready"],
            "speak_offline": h["tts_engine"] in ("piper", "kokoro"),
            "speak_free_online": h["tts_engine"] == "edge_tts",
            "speak_browser_fallback": h["tts_engine"] == "web_speech",
            "dialects_listen": h["dialects_local"],
            "dialects_speak_mapped": sorted(_EDGE_DIALECT_VOICES.keys()),
            "offline_capable": h["offline_capable"],
        }

    def _local_plan(self) -> Dict[str, object]:
        """本地不可用时的落地指引（不甩锅，给照敲命令）。"""
        from kernel.dialect_asr import install_plan
        return {
            "vosk": {
                "install": "pip install vosk",
                "model": "首次使用自动下载 vosk-model-small-cn-0.22(~42MB) 到 ~/.cache/vosk-models/",
                "verify": 'python -c "import vosk; print(\'vosk ok\')"',
            },
            "dialect_expand": install_plan("官话-北京"),
        }
