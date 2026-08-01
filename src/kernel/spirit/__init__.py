"""L4 精神层 —— 多文明共处、代际教化与共识演化（生命体OS 白皮书 L4）。

子模块：
- values_market  L4B 多文明价值观插件市场（可插拔价值观 + 冲突仲裁 + 宪法红线不可覆盖）
- mentorship     L4C 师徒协议（老实例带新实例，考核通过才放权）
- datong         L4D 大同指数 + L4E 文明试错镜像（多样性/公平/共识的量化 + 沙盘预演）
- consensus      L4F 共识自演化通道（提案→辩论→加权投票→生效，宪法条款需超级多数）

注：L4A 双向思辨演化调节器已实现于 `kernel/soul/dialectic.py`（先于本包落地，不重复造）。

诚实度：② 单元验证（tests/test_spirit_layer.py）；接入真实多租户运行为 ③ 待验。
"""

from .values_market import (
    ValuePlugin, ValuesMarket, ValueConflict, CONSTITUTION_REDLINES,
)
from .mentorship import Mentorship, Apprentice, Trial
from .datong import DatongIndex, CivilizationMirror, MirrorResult
from .consensus import ConsensusChannel, Proposal, Vote

__all__ = [
    "ValuePlugin", "ValuesMarket", "ValueConflict", "CONSTITUTION_REDLINES",
    "Mentorship", "Apprentice", "Trial",
    "DatongIndex", "CivilizationMirror", "MirrorResult",
    "ConsensusChannel", "Proposal", "Vote",
]
