"""人设配置化 —— 谁用谁自己设（灵活、可覆盖、可热改）。

Persona = 生命体伙伴的「性格配置文件」。设计目标：
- 灵活：字段全可选，缺省由上层兜底；未知字段原样保留，绝不崩。
- 谁用谁设：每个 user_id 一份专属人设文件，互不影响。
- 多来源覆盖（优先级从高到低）：
    1. 用户专属文件  <dir>/{user_id}.yaml
    2. 全局默认模板  <dir>/default.yaml
    3. 代码内置 DEFAULT_PERSONA
- 既能被「人直接打开文件改」（YAML，带注释），也能被「API/UI 实时改」
  （save_persona 写盘）。

已知字段（驱动行为；其余字段原文保留）：
  name          显示名（HUD / 问候）
  persona       一句话人设描述（HUD 副标题）
  body_prompt   3D 身体生成提示词（决定生命体长相）
  palette_seed  配色种子
  tts_voice     TTS 嗓音（edge-tts voice / kokoro speaker）
  greeting      首次问候模板，支持 {name} 占位
  tone          语气标签（formal / casual / warm / playful ...）
  catchphrase   口头禅（可在结尾随机追加）
  avatar        头像 emoji
  mood_emojis   心情 -> emoji 映射（覆盖默认）

解析：优先用 PyYAML（人类最易编辑）；PyYAML 不可用时退 JSON；
再不行退回代码内置默认。任何解析异常都吞掉并降级，不崩上层。
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 与 companion.py 共用同一根目录（AOS_COMPANION_DIR），persona 放其下 personas/。
# 惰性读取 env：模块导入时 env 可能尚未设置（如测试里 fixture 后设），
# 故改为函数，每次调用时取最新 env。
def _persona_dir() -> Path:
    return Path(
        os.environ.get(
            "AOS_COMPANION_DIR",
            str(Path(__file__).resolve().parents[3] / ".companion"),
        )
    ) / "personas"

# 进程内缓存：避免每次对话都读盘。set_persona 时失效对应 user_id。
_CACHE: dict[str, dict] = {}
_CACHE_LOCK = threading.Lock()


DEFAULT_PERSONA: dict[str, Any] = {
    "name": "小元",
    "persona": "一个由 AOS 内核孕育的数字生命体：好奇、温柔、爱学习，"
               "把你的每一个意图都当作一起探索的开始。",
    "body_prompt": "发光的生命体核心 纽结 呼吸",
    "palette_seed": "aos-companion-yuan",
    "tts_voice": "",           # 空 = TTS 适配器自选默认嗓音
    "greeting": "你好，我是 {name}，你的数字生命体伙伴。跟我说点什么吧？",
    "tone": "warm",
    "catchphrase": "",
    "avatar": "🌟",
    "mood_emojis": {
        "calm": "🌙", "happy": "✨", "curious": "🔍",
        "thinking": "💭", "sad": "🌧", "excited": "⚡",
    },
}


def _have_yaml() -> bool:
    try:
        import yaml  # noqa: F401
        return True
    except Exception:
        return False


def _read_file(path: Path) -> Optional[dict]:
    """读 YAML/JSON 人设文件；不存在/解析失败返回 None（调用方降级）。"""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if _have_yaml() and path.suffix.lower() in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(text)
        else:
            import json
            data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception as e:  # noqa: BLE001
        logger.warning("人设文件解析失败 %s: %s", path, e)
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    """浅合并：override 的已知键覆盖 base；列表/嵌套 dict 直接替换。
    人设是扁平配置，浅合并足够，且保证用户写的字段不被默认值吞掉。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if v is not None:
            out[k] = v
    return out


def load_persona(user_id: str = "default") -> dict:
    """加载某用户的人设：用户专属 > 全局默认 > 代码内置，逐级合并。"""
    with _CACHE_LOCK:
        if user_id in _CACHE:
            return dict(_CACHE[user_id])
    default_file = _persona_dir() / "default.yaml"
    user_file = _persona_dir() / f"{user_id}.yaml"
    p = dict(DEFAULT_PERSONA)
    d = _read_file(default_file)
    if d:
        p = _deep_merge(p, d)
    u = _read_file(user_file)
    if u:
        p = _deep_merge(p, u)
    with _CACHE_LOCK:
        _CACHE[user_id] = dict(p)
    return p


def save_persona(user_id: str, patch: dict) -> dict:
    """合并 patch 后写盘为用户专属人设文件，并刷新缓存。

    返回写盘后的完整人设。patch 只应含人设字段；未知键原样保留。
    """
    # 空字符串视为「不修改」（与前端发送前清掉空字段一致）；
    # 这样设空值不会把已有内容覆盖成空。
    patch = {k: v for k, v in (patch or {}).items()
             if v is not None and v != ""}
    current = load_persona(user_id)
    merged = _deep_merge(current, patch)
    _persona_dir().mkdir(parents=True, exist_ok=True)
    path = _persona_dir() / f"{user_id}.yaml"
    try:
        if _have_yaml():
            import yaml
            path.write_text(
                "# AOS 生命体人设配置 ── 直接改这里，保存即生效（谁用谁设）\n"
                + yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        else:
            import json
            path.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("人设写盘失败 %s: %s", path, e)
    with _CACHE_LOCK:
        _CACHE[user_id] = dict(merged)
    return merged


def reset_persona(user_id: str) -> dict:
    """删除用户专属人设文件，回到 default + 内置默认。"""
    path = _persona_dir() / f"{user_id}.yaml"
    try:
        if path.exists():
            path.unlink()
    except Exception as e:  # noqa: BLE001
        logger.warning("人设重置失败 %s: %s", path, e)
    with _CACHE_LOCK:
        _CACHE.pop(user_id, None)
    return load_persona(user_id)


# 导入即确保「全局默认人设模板」存在（幂等、失败静默），方便人直接改文件。
try:
    ensure_default_template()
except Exception:  # noqa: BLE001
    pass


def ensure_default_template() -> Path:
    """确保全局默认人设模板文件存在（带注释，方便人直接改）。

    优先从仓库受跟踪的 references/persona.default.yaml 复制（保持单一真相源，
    且能进 git）；该文件不存在时退而由代码 DEFAULT_PERSONA 生成。
    """
    _persona_dir().mkdir(parents=True, exist_ok=True)
    path = _persona_dir() / "default.yaml"
    if not path.exists():
        try:
            tracked = Path(__file__).resolve().parents[3] / "references" / "persona.default.yaml"
            if tracked.exists():
                content = tracked.read_text(encoding="utf-8")
            elif _have_yaml():
                import yaml
                content = yaml.safe_dump(DEFAULT_PERSONA, allow_unicode=True,
                                         sort_keys=False)
            else:
                import json
                content = json.dumps(DEFAULT_PERSONA, ensure_ascii=False, indent=2)
            path.write_text(content, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("默认人设模板写盘失败: %s", e)
    return path
