"""L4 双向思辨演化调节器 —— 完全自研核心（生命体OS 白皮书 L4A）。

三档可调（低/中/高），主动对观点生成反向论证，打破认知茧房。
低档：弱反向提示；高档：强对抗性挑战（可接真 LLM，此处用启发式兜底）。
"""
from __future__ import annotations

from enum import Enum
from typing import List, Literal

Level = Literal["low", "mid", "high"]


class DialecticRegulator:
    """双向思辨：主动找自己观点的茬，避免自说自话。"""

    # 不同档位的反向质疑强度（生成对抗论点数量）
    _STRENGTH = {"low": 1, "mid": 2, "high": 3}

    def __init__(self, level: Level = "mid"):
        self.level = level

    def challenge(self, viewpoint: str) -> List[str]:
        """对给定观点生成反向论证（启发式版，不依赖 LLM）。"""
        n = self._STRENGTH[self.level]
        templates = [
            f"反方：{viewpoint} 是否忽略了其前提假设的局限性？",
            f"反方：若资源或环境变化，{viewpoint} 是否仍然成立？",
            f"反方：{viewpoint} 的反对者会指出哪些被低估的风险？",
        ]
        return templates[:n]

    def set_level(self, level: Level) -> None:
        self.level = level
