"""Eval Framework 模块 —— 评估框架与回归基线（Task 3）。

落地理念9「可验证即真理」+ 理念6「诚实+量化置信」：
- 数据集驱动的轨迹评分（trajectory scoring）
- 基线对比 + 回归检测（pass_rate / duration / cost 退化告警）
- 每次评估运行的报告持久化（data/eval/runs/）

入口：
- EvalHarness / get_eval_harness() —— 单例
- EvalCase / CaseResult / EvalRun —— 数据模型
"""
from .eval_harness import (
    EvalCase,
    CaseResult,
    EvalRun,
    EvalHarness,
    get_eval_harness,
)

__all__ = [
    "EvalCase",
    "CaseResult",
    "EvalRun",
    "EvalHarness",
    "get_eval_harness",
]
