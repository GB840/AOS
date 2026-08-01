"""L3 灵魂层：记忆与身份 / 价值排序 / 情感状态（白皮书 L3）。

acgs-lite（AGPL-3.0）仅作只读借鉴，本包零外部依赖、无 import acgs 任何符号
（CI 扫描 kernel/soul 不得 import acgs，见 LIFEFORM_OS_BUILD_PLAN.md §4.3）。
"""
from .value_hierarchy import ValueHierarchy
from .emotion_state import EmotionState

__all__ = ["ValueHierarchy", "EmotionState"]
