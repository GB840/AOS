"""Evolve —— 智能体自动进化引擎。

基于使用数据和用户反馈，自动优化智能体的：
- 提示词（多版本 A/B 测试）
- 工作流结构（步骤顺序、重试策略）
- 模型选择（简单任务用小模型，复杂任务用大模型）

设计原则：
- 数据驱动：所有优化都基于真实数据，不拍脑袋
- 灰度发布：先给少数用户测，效果好再全量
- 可回滚：效果不好随时退回去
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_EVOLVE_DIR = os.environ.get(
    "AOS_EVOLVE_DIR",
    os.path.join("data", "workspaces", "fabric", "evolve"),
)


def _evolve_dir() -> str:
    os.makedirs(_EVOLVE_DIR, exist_ok=True)
    return _EVOLVE_DIR


@dataclass
class ABTest:
    """一个 A/B 测试。"""
    id: str = ""
    workflow_id: str = ""
    name: str = ""
    variant_a: Dict[str, Any] = field(default_factory=dict)
    variant_b: Dict[str, Any] = field(default_factory=dict)
    metric: str = "success_rate"  # success_rate / duration / user_rating
    status: str = "running"  # running / winner_a / winner_b / draw / stopped
    a_runs: int = 0
    b_runs: int = 0
    a_success: int = 0
    b_success: int = 0
    a_avg_duration: float = 0.0
    b_avg_duration: float = 0.0
    started_at: str = ""
    ended_at: str = ""
    winner: str = ""  # a / b / draw


class EvolveEngine:
    """自动进化引擎。"""

    def __init__(self):
        self._ab_tests: Dict[str, ABTest] = {}
        self._load_tests()

    # ── A/B 测试 ──

    def create_ab_test(self, workflow_id: str, name: str,
                        variant_a: Dict, variant_b: Dict,
                        metric: str = "success_rate") -> ABTest:
        """创建一个新的 A/B 测试。"""
        import uuid
        test = ABTest(
            id=uuid.uuid4().hex[:8],
            workflow_id=workflow_id,
            name=name,
            variant_a=variant_a,
            variant_b=variant_b,
            metric=metric,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._ab_tests[test.id] = test
        self._save_tests()
        return test

    def get_variant(self, workflow_id: str) -> Optional[Dict]:
        """获取一个测试的变体（随机分配）。

        用于灰度发布：调用前先拿变体，用变体参数运行工作流。
        """
        for test in self._ab_tests.values():
            if test.workflow_id == workflow_id and test.status == "running":
                # 随机分配，各 50% 概率
                variant = random.choice(["a", "b"])
                return {
                    "test_id": test.id,
                    "variant": variant,
                    "params": test.variant_a if variant == "a" else test.variant_b,
                }
        return None

    def record_result(self, test_id: str, variant: str, success: bool,
                       duration: float) -> None:
        """记录一次测试结果。"""
        test = self._ab_tests.get(test_id)
        if not test or test.status != "running":
            return

        if variant == "a":
            test.a_runs += 1
            if success:
                test.a_success += 1
            test.a_avg_duration = self._avg(test.a_avg_duration, test.a_runs, duration)
        elif variant == "b":
            test.b_runs += 1
            if success:
                test.b_success += 1
            test.b_avg_duration = self._avg(test.b_avg_duration, test.b_runs, duration)

        # 检查是否有统计显著性（简化版：每组至少 10 次，差距 > 10% 就判定）
        if test.a_runs >= 10 and test.b_runs >= 10:
            self._check_winner(test)

        self._save_tests()

    def _check_winner(self, test: ABTest) -> None:
        """检查是否有胜出者。"""
        a_rate = test.a_success / test.a_runs if test.a_runs > 0 else 0
        b_rate = test.b_success / test.b_runs if test.b_runs > 0 else 0

        if test.metric == "success_rate":
            diff = abs(a_rate - b_rate)
            if diff > 0.1:  # 差距 > 10%
                if a_rate > b_rate:
                    test.winner = "a"
                    test.status = "winner_a"
                else:
                    test.winner = "b"
                    test.status = "winner_b"
                test.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                logger.info("A/B 测试 %s 结束，胜出者: %s", test.id, test.winner)
        elif test.metric == "duration":
            if test.a_avg_duration > 0 and test.b_avg_duration > 0:
                diff_pct = abs(test.a_avg_duration - test.b_avg_duration) / min(test.a_avg_duration, test.b_avg_duration)
                if diff_pct > 0.2:  # 差距 > 20%
                    if test.a_avg_duration < test.b_avg_duration:
                        test.winner = "a"
                        test.status = "winner_a"
                    else:
                        test.winner = "b"
                        test.status = "winner_b"
                    test.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def stop_test(self, test_id: str) -> bool:
        """停止一个测试。"""
        test = self._ab_tests.get(test_id)
        if not test:
            return False
        test.status = "stopped"
        test.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_tests()
        return True

    def list_tests(self, workflow_id: str = "", status: str = "") -> List[Dict]:
        """列出 A/B 测试。"""
        tests = []
        for t in self._ab_tests.values():
            if workflow_id and t.workflow_id != workflow_id:
                continue
            if status and t.status != status:
                continue
            tests.append(asdict(t))
        tests.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return tests

    # ── 自动优化建议 ──

    def suggest_optimizations(self, workflow_id: str,
                               metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """基于指标数据生成优化建议。"""
        suggestions = []

        success_rate = metrics.get("success_rate", 0)
        avg_duration = metrics.get("avg_duration", 0)
        step_stats = metrics.get("step_stats", {})

        # 建议 1：成功率低？
        if success_rate < 50:
            suggestions.append({
                "type": "success_rate",
                "priority": "high",
                "suggestion": "成功率偏低，建议增加失败重试和故障转移",
                "detail": f"当前成功率 {success_rate}%，目标建议 > 80%",
            })

        # 建议 2：太慢？
        if avg_duration > 60:
            suggestions.append({
                "type": "performance",
                "priority": "medium",
                "suggestion": "平均耗时较长，建议优化慢步骤",
                "detail": f"当前平均 {avg_duration:.1f}s，建议降到 30s 以内",
            })

        # 建议 3：提示词优化 A/B 测试
        suggestions.append({
            "type": "prompt_ab_test",
            "priority": "medium",
            "suggestion": "创建提示词 A/B 测试，找到最优版本",
            "detail": "可以测试 2-3 个不同风格的提示词，看哪个效果好",
        })

        # 建议 4：模型选择优化
        suggestions.append({
            "type": "model_optimization",
            "priority": "low",
            "suggestion": "考虑按任务复杂度自动选择模型",
            "detail": "简单任务用小模型（省钱快），复杂任务用大模型（效果好）",
        })

        return suggestions

    # ── 内部方法 ──

    @staticmethod
    def _avg(current_avg: float, count: int, new_value: float) -> float:
        """增量式计算平均值。"""
        if count <= 1:
            return new_value
        return current_avg + (new_value - current_avg) / count

    def _load_tests(self) -> None:
        path = os.path.join(_evolve_dir(), "ab_tests.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for tid, td in data.items():
                        self._ab_tests[tid] = ABTest(**td)
            except Exception as e:
                logger.warning("加载 A/B 测试失败: %s", e)

    def _save_tests(self) -> None:
        path = os.path.join(_evolve_dir(), "ab_tests.json")
        try:
            data = {tid: asdict(t) for tid, t in self._ab_tests.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("保存 A/B 测试失败: %s", e)


# 单例
_engine: Optional[EvolveEngine] = None


def get_evolve_engine() -> EvolveEngine:
    global _engine
    if _engine is None:
        _engine = EvolveEngine()
    return _engine
