"""全链路三级量化置信（AGENTS.md 理念6）。

统一对外输出口径：低 / 中 / 高 + emoji + 量化依据，杜绝各端点各说各话。
所有声明带结构化原始指标（命中条数、退出码……），以量化数据替代二元成败判断。

判定口径（与白皮书 §6 表格一致）：
  - 🔴 低置信：正向样本 0（如 0 条搜索结果 / exit_code != 0）
  - 🟡 中置信：正向样本 1~4（如 1-4 条结果 / 部分依赖缺失）
  - 🟢 高置信：正向样本 >= 5（如 >=5 条结果 / 全链路成功）
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

LOW, MID, HIGH = 0, 1, 2
_EMOJI = {LOW: "🔴", MID: "🟡", HIGH: "🟢"}
_LABEL = {LOW: "低", MID: "中", HIGH: "高"}


@dataclass
class Confidence:
    level: int
    emoji: str
    label: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "emoji": self.emoji,
            "label": self.label,
            "reason": self.reason,
        }


def assess(positive: int,
           threshold_mid: int = 1,
           threshold_high: int = 5,
           reason_fmt: Optional[Callable[[int], str]] = None) -> Confidence:
    """按正向样本数判定三级置信（默认 0→低, 1-4→中, >=5→高）。"""
    if positive <= 0:
        lvl = LOW
    elif positive < threshold_high:
        lvl = MID
    else:
        lvl = HIGH
    reason = (reason_fmt(positive) if reason_fmt
              else f"正向样本 {positive}：{_LABEL[lvl]}置信"
                   f"（阈值 中>={threshold_mid}, 高>={threshold_high}）")
    return Confidence(lvl, _EMOJI[lvl], _LABEL[lvl], reason)


def assess_search(result_count: int) -> Dict[str, Any]:
    """搜索结果条数 → 三级置信（白皮书 §6 搜索口径）。"""
    def _fmt(n: int) -> str:
        lvl = _LABEL[LOW] if n <= 0 else _LABEL[MID] if n < 5 else _LABEL[HIGH]
        return f"搜索命中 {n} 条结果：{lvl}置信"
    return assess(result_count, reason_fmt=_fmt).to_dict()


def assess_command(exit_code: int, had_output: bool = True) -> Dict[str, Any]:
    """命令执行 → 三级置信：exit_code==0 且有真实输出为高，否则为低。"""
    if exit_code != 0 or not had_output:
        return Confidence(
            LOW, _EMOJI[LOW], _LABEL[LOW],
            f"exit_code={exit_code} 或无真实输出：低置信",
        ).to_dict()
    return Confidence(
        HIGH, _EMOJI[HIGH], _LABEL[HIGH],
        f"exit_code=0 且有真实输出：高置信",
    ).to_dict()
