"""语音模块入口。

默认导出 CompanionVoice（本地优先 · 方言平等 · 断网可跑的 Tier 0 陪伴通道）。
云版 ASR/TTS（百度/讯飞/智谱）作为 opt-in 兜底：依赖 utils.config(pydantic_settings)，
缺依赖时不拖垮整个 voice 包——仅当 CompanionVoice 显式开启云兜底时才惰性 import。
"""
from .companion import CompanionVoice

__all__ = ["CompanionVoice"]

try:
    from .asr import ASREngine
    from .tts import TTSEngine
    __all__ += ["ASREngine", "TTSEngine"]
except Exception:  # pragma: no cover - 缺 pydantic_settings 等依赖
    ASREngine = None
    TTSEngine = None
