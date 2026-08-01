"""L0 人本生命状态建模内核 —— 最高决策标尺（白皮书 L0）。

生命状态向量：energy / mood / focus / debt。
状态真实影响路由与决策（非展示用）：energy 低时自动降档选轻模型；
mood 低落时降低冒险容忍度（供 L3 决策消费）。

诚实度：本模块为 ① 代码就绪，配 tests/test_life_state.py 达 ② 单元验证；
接入 autopilot 自动降档为后续 ② 动作（见 LIFEFORM_OS_BUILD_PLAN.md §3）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

DEFAULT_LIFE_STATE_DIR = Path(__file__).resolve().parents[1] / "data" / "life_state"


@dataclass
class LifeState:
    energy: float = 1.0     # 能量 0..1，连续推理递减
    mood: float = 0.5       # 情绪 0..1（0 低落 / 1 兴奋）
    focus: float = 1.0      # 专注 0..1，任务切换重置为 1.0
    debt: float = 0.0       # 债务 0..N，失败/未完成任务递增
    updated_at: float = field(default_factory=time.time)

    # 阈值常量（不可配置为「无上限」）
    LOW_ENERGY: float = 0.3
    MAX_DEBT: float = 5.0

    def decay(self, cost: float = 0.05, failed: float = 0.0) -> "LifeState":
        """连续推理消耗 energy；失败增加 debt。返回 self 便于链式。"""
        self.energy = max(0.0, self.energy - cost)
        if failed:
            self.debt = min(self.MAX_DEBT, self.debt + failed)
        self.updated_at = time.time()
        return self

    def reset_focus(self) -> "LifeState":
        self.focus = 1.0
        return self

    def risk_tolerance(self) -> float:
        """冒险容忍度：情绪高→更敢试；债务高→更保守。范围约 -0.3..0.8。"""
        return round(0.3 + 0.5 * self.mood - 0.1 * self.debt, 4)

    def pick_engine_tier(self, heavy: str, light: str) -> str:
        """energy 低于阈值时降级到轻模型，否则用重型。供 autopilot 调用。"""
        return light if self.energy < self.LOW_ENERGY else heavy

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()
                if k not in ("LOW_ENERGY", "MAX_DEBT")}

    @classmethod
    def from_dict(cls, d: dict) -> "LifeState":
        d = {k: v for k, v in dict(d).items()
             if k in cls.__dataclass_fields__ and k not in ("LOW_ENERGY", "MAX_DEBT")}
        return cls(**d)


class LifeStateStore:
    """按用户持久化生命状态（每用户一份 life_state.json）。"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base = Path(base_dir) if base_dir else DEFAULT_LIFE_STATE_DIR
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.base / f"{user_id}.json"

    def load(self, user_id: str = "default") -> LifeState:
        p = self._path(user_id)
        if p.exists():
            try:
                return LifeState.from_dict(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
        return LifeState()

    def save(self, user_id: str, state: LifeState) -> None:
        self._path(user_id).write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
