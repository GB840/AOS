"""方言平等路由（母纲原则 7「技术普惠·方言平等」的真落地能力层）。

宪法依据（AGENTS.md §0.0）：
    母纲「让 AI 不再收割老百姓，而是陪伴老百姓」
    原则 7：不会说普通话的老人、说方言的县城小老板，也要能用。
    §0.0.3 硬检验 1「断网检验」：不联网、不付费，方言识别也要能跑。

它做什么（不是占位，是真路由）：
    1. 维护「方言目标 → 真实引擎/模型」的能力矩阵（真实开源引擎，非杜撰）；
    2. 真探测引擎是否**此刻真能用**（库装没装、模型下没下）；
    3. 按方言真分派到对应引擎执行识别；
    4. 引擎缺失时，给出**可直接照敲的落地命令**，而不是一句「不支持」。

诚实纪律（理念 9 可验证即真理）：
    - `supported_dialects()` 返回的是**此刻真能识别**的方言，不是「矩阵上写了」的。
      引擎没装 / 模型没下 → 该引擎覆盖的方言一律不算数。
    - 覆盖矩阵只写引擎官方**明确声明**支持的方言，官方没说的绝不脑补。
    - 识别失败就报错，绝不静默退回普通话模型假装识别成功。

真实引擎（已联网核实，2026-08）：
    - funasr / Fun-ASR-Nano-2512（通义实验室，Apache-2.0）
      官方声明：中文 7 大方言（吴/粤/闽/客/赣/湘/晋）+ 26 种地域口音
      （河南、陕西、湖北、四川、重庆、云南、贵州、广东、广西等）。
      有 llama.cpp / GGUF 量化版（约 484MB），纯 CPU 可跑 → 断网检验通过。
      https://github.com/FunAudioLLM/Fun-ASR
    - vosk（Alpha Cephei，Apache-2.0）：中文普通话小模型 40-50MB，全离线。
    - faster_whisper / whisper_cpp：普通话为主，方言表现不稳 → 只认普通话。

设计：
    - 重依赖**全部惰性导入**，import 本模块零副作用、零网络。
    - 后端可注入（`DialectASR(backends=...)`），便于单测在无模型环境下验证路由。
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ===========================================================================
# 能力矩阵：引擎 -> 官方明确声明支持的方言（对齐 constitution_gaps.DIALECT_TARGETS）
# ===========================================================================
# 依据 Fun-ASR-Nano-2512 官方 README：7 大方言 = 吴、粤、闽、客、赣、湘、晋；
# 26 地域口音含 河南(中原官话)、湖北/四川/重庆/云南/贵州(西南官话)、
# 陕西(中原官话)、东北、北京、江淮 等。
# **未声明的不写**：徽语、平话、儋州话、兰银官话 官方未点名 → 留缺口，不脑补。
FUNASR_DIALECTS: List[str] = [
    "官话-东北", "官话-北京", "官话-中原", "官话-西南", "官话-江淮",
    "晋语",
    "吴语-太湖(上海话)", "吴语-温州", "吴语-台州",
    "赣语",
    "湘语-长益", "湘语-娄邵",
    "闽语-闽北", "闽语-闽东(福州话)", "闽语-闽南(厦门/台语)", "闽语-莆仙",
    "客家话", "粤语",
]

# 普通话 = 官话-北京。Vosk / Whisper 只诚实认这一个。
MANDARIN_ONLY: List[str] = ["官话-北京"]

ENGINE_COVERAGE: Dict[str, List[str]] = {
    "funasr": FUNASR_DIALECTS,
    "vosk": MANDARIN_ONLY,
    "faster_whisper": MANDARIN_ONLY,
    "whisper_cpp": MANDARIN_ONLY,
}

# 路由优先级：覆盖广且离线可跑的排前面。
ENGINE_PRIORITY: List[str] = ["funasr", "vosk", "faster_whisper", "whisper_cpp"]

FUNASR_MODEL_ID = os.environ.get(
    "AOS_FUNASR_MODEL", "FunAudioLLM/Fun-ASR-Nano-2512"
)

# 各引擎的落地命令（用户照敲即可，不给「请自行安装」这种废话）
INSTALL_PLAYBOOK: Dict[str, Dict[str, str]] = {
    "funasr": {
        "install": 'pip install -U "funasr>=1.3.28" torch torchaudio',
        "model": (
            "python -c \"from modelscope import snapshot_download; "
            "snapshot_download('FunAudioLLM/Fun-ASR-Nano-2512')\"   "
            "# 国内走 ModelScope；或设 AOS_FUNASR_HUB=hf 走 HuggingFace"
        ),
        "verify": (
            'python -c "from funasr import AutoModel; '
            "print('funasr ok')\""
        ),
        "note": "约 800M 参数；无 GPU 可改用 llama.cpp GGUF 量化版（~484MB，纯 CPU）",
        "license": "Apache-2.0（通义实验室，可商用）",
    },
    "vosk": {
        "install": "pip install vosk",
        "model": (
            "下载 vosk-model-cn-0.22 解压到 ~/.cache/vosk-models/ "
            "（或设 AOS_VOSK_MODEL 指向模型目录）"
        ),
        "verify": 'python -c "import vosk; print(\'vosk ok\')"',
        "note": "40-50MB，低资源老机器友好，但仅普通话",
        "license": "Apache-2.0",
    },
    "faster_whisper": {
        "install": "pip install faster-whisper",
        "model": "首次运行自动下载（约 75-150MB）；或设 AOS_WHISPER_SIZE=base",
        "verify": 'python -c "import faster_whisper; print(\'ok\')"',
        "note": "普通话可用，方言不稳，本路由不把方言派给它",
        "license": "MIT",
    },
    "whisper_cpp": {
        "install": "编译 whisper.cpp 后设 AOS_WHISPER_CPP_BIN 指向 whisper-cli",
        "model": "下载 ggml-base.bin 到 ~/whisper.cpp/models/",
        "verify": "whisper-cli --help",
        "note": "纯 C++ 全离线；仅普通话",
        "license": "MIT",
    },
}


# ===========================================================================
# 引擎真探测：不看矩阵写了什么，看此刻机器上到底有没有
# ===========================================================================

def _funasr_ready() -> bool:
    """funasr 库已装 **且** 模型已在本地缓存，才算真能用。"""
    try:
        import funasr  # noqa: F401 - 仅探测
    except Exception:
        return False
    return _funasr_model_cached()


def _funasr_model_cached() -> bool:
    """检查 Fun-ASR 模型是否已落盘（不触发下载，避免探测即联网）。"""
    explicit = os.environ.get("AOS_FUNASR_MODEL_DIR")
    if explicit:
        return os.path.isdir(explicit)
    tail = FUNASR_MODEL_ID.replace("/", os.sep)
    flat = FUNASR_MODEL_ID.replace("/", "--")
    candidates = [
        os.path.join(os.path.expanduser("~"), ".cache", "modelscope", "hub", tail),
        os.path.join(os.path.expanduser("~"), ".cache", "modelscope", "hub",
                     "models", tail),
        os.path.join(
            os.environ.get("HF_HOME") or os.path.join(
                os.path.expanduser("~"), ".cache", "huggingface", "hub"),
            f"models--{flat}",
        ),
    ]
    return any(os.path.isdir(c) for c in candidates)


def _vosk_ready() -> bool:
    try:
        from core.fabric.adapters.vosk_backend import VoskSTT  # 复用已有后端
    except Exception:
        return False
    try:
        return bool(VoskSTT().available)
    except Exception:
        return False


def _faster_whisper_ready() -> bool:
    try:
        from core.fabric.adapters.stt_adapter import _faster_whisper_model_cached
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    try:
        return bool(_faster_whisper_model_cached(
            os.environ.get("AOS_WHISPER_SIZE", "base")))
    except Exception:
        return False


def _whisper_cpp_ready() -> bool:
    try:
        from core.fabric.adapters.stt_adapter import (
            _WHISPER_BIN_CANDIDATES, _WHISPER_MODEL_CANDIDATES, _first_existing,
        )
    except Exception:
        return False
    try:
        binp = _first_existing(list(_WHISPER_BIN_CANDIDATES))
        modelp = _first_existing(list(_WHISPER_MODEL_CANDIDATES))
        return bool(binp and modelp)
    except Exception:
        return False


_READY_PROBES: Dict[str, Callable[[], bool]] = {
    "funasr": _funasr_ready,
    "vosk": _vosk_ready,
    "faster_whisper": _faster_whisper_ready,
    "whisper_cpp": _whisper_cpp_ready,
}


def engine_ready(engine: str) -> bool:
    """该引擎此刻是否真能把音频转成文字（库 + 模型都到位）。"""
    probe = _READY_PROBES.get(engine)
    if probe is None:
        return False
    try:
        return bool(probe())
    except Exception as exc:  # 探测本身异常 = 不可用，绝不谎报可用
        logger.debug("engine_ready(%s) 探测异常: %r", engine, exc)
        return False


def ready_engines() -> List[str]:
    return [e for e in ENGINE_PRIORITY if engine_ready(e)]


# ===========================================================================
# 方言路由
# ===========================================================================

def all_targets() -> List[str]:
    """宪法目标方言清单（唯一真值源在 constitution_gaps，避免两处漂移）。"""
    from kernel.constitution_gaps import DIALECT_TARGETS  # 惰性，避免循环导入

    return list(DIALECT_TARGETS)


def declared_coverage() -> Dict[str, List[str]]:
    """矩阵层：每个方言**理论上**由哪些引擎覆盖（不代表此刻可用）。"""
    out: Dict[str, List[str]] = {d: [] for d in all_targets()}
    for engine in ENGINE_PRIORITY:
        for d in ENGINE_COVERAGE.get(engine, []):
            if d in out:
                out[d].append(engine)
    return out


def supported_dialects() -> List[str]:
    """**此刻真能识别**的方言（已就绪引擎的覆盖并集）。引擎没装就是空。"""
    ready = set(ready_engines())
    if not ready:
        return []
    targets = all_targets()
    sup = {d for e in ready for d in ENGINE_COVERAGE.get(e, []) if d in targets}
    return [d for d in targets if d in sup]


def route(dialect: str) -> Optional[Dict[str, str]]:
    """把方言路由到一个**此刻真能用**的引擎。不可用返回 None（不假装能跑）。"""
    forced = os.environ.get("AOS_DIALECT_ASR_ENGINE")
    if forced:
        if dialect in ENGINE_COVERAGE.get(forced, []) and engine_ready(forced):
            return {"engine": forced, "dialect": dialect, "reason": "环境变量强制指定"}
        return None
    for engine in ENGINE_PRIORITY:
        if dialect in ENGINE_COVERAGE.get(engine, []) and engine_ready(engine):
            return {"engine": engine, "dialect": dialect, "reason": "按优先级自动选择"}
    return None


def install_plan(dialect: str) -> Dict[str, object]:
    """方言不可用时，给出**可直接照敲**的落地路径，而不是一句「不支持」。

    这是原则 7 的态度：暂时跑不了，也要明确告诉老百姓怎么才能跑起来。
    """
    targets = all_targets()
    if dialect not in targets:
        return {
            "dialect": dialect,
            "known_target": False,
            "message": f"「{dialect}」不在宪法 22 种目标方言清单内",
            "targets": targets,
        }
    engines = declared_coverage().get(dialect, [])
    if not engines:
        return {
            "dialect": dialect,
            "known_target": True,
            "available_now": False,
            "engines": [],
            "message": (
                f"目前**没有任何已核实的开源引擎**公开声明支持「{dialect}」。"
                "这是真实缺口，不脑补覆盖。"
            ),
        }
    steps = [
        {"engine": e, "ready": engine_ready(e), **INSTALL_PLAYBOOK.get(e, {})}
        for e in engines
    ]
    return {
        "dialect": dialect,
        "known_target": True,
        "available_now": any(s["ready"] for s in steps),
        "engines": engines,
        "steps": steps,
    }


def coverage_report() -> Dict[str, object]:
    """一张表看清：目标多少、真支持多少、矩阵理论覆盖多少、缺口在哪。"""
    targets = all_targets()
    declared = declared_coverage()
    real = set(supported_dialects())
    declared_ok = [d for d in targets if declared.get(d)]
    return {
        "targets": len(targets),
        "declared_covered": len(declared_ok),
        "really_supported": len(real),
        "ready_engines": ready_engines(),
        "missing_no_engine": [d for d in targets if not declared.get(d)],
        "missing_engine_not_installed": [
            d for d in targets if declared.get(d) and d not in real
        ],
        "supported": sorted(real, key=targets.index),
    }


# ===========================================================================
# 真识别：按方言分派到引擎
# ===========================================================================

class DialectASR:
    """方言语音识别分派器。

    `backends` 可注入（engine -> callable(audio_path, dialect) -> str），
    用于单测在无模型机器上验证「路由逻辑本身」是否正确。
    """

    def __init__(self, backends: Optional[Dict[str, Callable[[str, str], str]]] = None):
        self._backends = dict(backends) if backends else {}
        self._injected = bool(backends)

    # --- 可用性（注入模式下按注入的算） ---
    def _engine_ready(self, engine: str) -> bool:
        if self._injected:
            return engine in self._backends
        return engine_ready(engine)

    def ready_engines(self) -> List[str]:
        return [e for e in ENGINE_PRIORITY if self._engine_ready(e)]

    def supported_dialects(self) -> List[str]:
        ready = set(self.ready_engines())
        targets = all_targets()
        sup = {d for e in ready for d in ENGINE_COVERAGE.get(e, []) if d in targets}
        return [d for d in targets if d in sup]

    def route(self, dialect: str) -> Optional[str]:
        forced = os.environ.get("AOS_DIALECT_ASR_ENGINE")
        if forced:
            if dialect in ENGINE_COVERAGE.get(forced, []) and self._engine_ready(forced):
                return forced
            return None
        for engine in ENGINE_PRIORITY:
            if dialect in ENGINE_COVERAGE.get(engine, []) and self._engine_ready(engine):
                return engine
        return None

    def transcribe(self, audio_path: str, dialect: str = "官话-北京") -> Dict[str, object]:
        """把音频按方言识别成文字。

        返回 {"ok": bool, "text": str, "engine": str, "dialect": str, ...}
        不可用时 ok=False 并附 `plan`（照敲命令），**绝不静默换普通话模型冒充**。
        """
        if not audio_path or not os.path.isfile(audio_path):
            return {"ok": False, "dialect": dialect,
                    "error": "audio_path 不存在，无法识别"}

        engine = self.route(dialect)
        if engine is None:
            return {
                "ok": False,
                "dialect": dialect,
                "error": f"「{dialect}」此刻没有可用引擎（未安装或无模型）",
                "plan": install_plan(dialect),
            }

        fn = self._backends.get(engine)
        try:
            if fn is not None:
                text = fn(audio_path, dialect)
            elif engine == "funasr":
                text = _run_funasr(audio_path, dialect)
            else:
                text = _run_legacy_stt(engine, audio_path)
        except Exception as exc:
            return {"ok": False, "dialect": dialect, "engine": engine,
                    "error": f"{engine} 识别失败: {exc}"}

        text = (text or "").strip()
        if not text:
            return {"ok": False, "dialect": dialect, "engine": engine,
                    "error": f"{engine} 未识别出文本"}
        return {"ok": True, "text": text, "engine": engine, "dialect": dialect}


# --- 真引擎执行（重依赖惰性导入） ---

def _run_funasr(audio_path: str, dialect: str) -> str:
    """Fun-ASR-Nano 真识别。模型自身判别方言/口音，无需传方言编码。"""
    from funasr import AutoModel

    hub = os.environ.get("AOS_FUNASR_HUB", "ms")  # 国内默认 ModelScope
    device = os.environ.get("AOS_FUNASR_DEVICE", "cpu")
    model_dir = os.environ.get("AOS_FUNASR_MODEL_DIR") or FUNASR_MODEL_ID
    model = AutoModel(model=model_dir, trust_remote_code=True,
                      device=device, hub=hub)
    res = model.generate(input=[audio_path], cache={}, batch_size=1,
                         language="中文", itn=True)
    if not res:
        return ""
    first = res[0]
    if isinstance(first, dict):
        return str(first.get("text", ""))
    return str(first)


def _run_legacy_stt(engine: str, audio_path: str) -> str:
    """复用仓库已有 STT 适配器（vosk / whisper 系），不重造。"""
    from core.fabric.adapters.stt_adapter import STTAdapter
    from core.fabric.adapter import InvokeRequest

    adapter = STTAdapter(engine=engine)
    result = adapter.invoke(InvokeRequest(payload={"audio_path": audio_path}))
    if not getattr(result, "ok", False):
        raise RuntimeError(getattr(result, "error", "STT 失败"))
    return str((result.data or {}).get("text", ""))


# --- 便捷单例 ---

_DEFAULT: Optional[DialectASR] = None


def get_dialect_asr() -> DialectASR:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = DialectASR()
    return _DEFAULT


def ffmpeg_available() -> bool:
    """音频转码能力（vosk 要求 16k 单声道 wav）。缺了如实说，不假装。"""
    return bool(shutil.which(os.environ.get("AOS_FFMPEG_BIN", "ffmpeg")))
