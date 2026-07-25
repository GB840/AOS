"""因果实验框架——让autopilot自动做A/B实验，从observational升级到interventional。

这是Pearl因果之梯第二层（do-calculus）的AOS落地：
- observational：从历史Trace统计关联（CausalModel已有）
- interventional：通过随机分流实验估计因果效应（本模块新增）

核心思路：当CausalModel的样本不足或置信区间过宽时，自动发起一次
'实验'——对同一任务随机选两个引擎执行，比较结果，积累do-intervention数据。
"""
from __future__ import annotations

import math
import random
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Experiment:
    """一次A/B实验。"""
    experiment_id: str
    capability: str
    engine_a: str
    engine_b: str
    # 实验配置
    sample_size: int = 10          # 每组最少样本数
    significance_level: float = 0.05  # 显著性水平
    # 实验结果
    results_a: List[Dict[str, Any]] = field(default_factory=list)
    results_b: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "running"  # running / completed / cancelled
    winner: Optional[str] = None
    p_value: Optional[float] = None
    effect_size: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "capability": self.capability,
            "engine_a": self.engine_a,
            "engine_b": self.engine_b,
            "sample_size": self.sample_size,
            "significance_level": self.significance_level,
            "results_a": self.results_a,
            "results_b": self.results_b,
            "status": self.status,
            "winner": self.winner,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class CausalExperimentEngine:
    """因果实验引擎——自动发起A/B实验，积累intervention数据。

    与CausalModel配合：CausalModel负责observational统计，本引擎负责interventional实验。
    当observational数据不足以做出可靠决策时，自动发起实验。

    典型工作流：
    1. autopilot调用should_experiment(capability)判断是否需要实验
    2. 若需要，create_experiment()创建实验并返回experiment_id
    3. 每次执行前assign_engine()随机选引擎A/B
    4. 执行后record_outcome()记录结果
    5. 样本够时analyze()出结果
    6. integrate_to_causal_model()把实验数据写入CausalModel
    """

    def __init__(self, causal_model=None, distiller=None):
        """
        Args:
            causal_model: CausalModel实例，用于读取历史统计和写入实验结果
            distiller: EvolutionDistiller实例，用于持久化实验数据
        """
        self._model = causal_model
        self._distiller = distiller
        self._experiments: Dict[str, Experiment] = {}
        self._active_experiments: Dict[str, str] = {}  # capability -> experiment_id
        self._lock = threading.RLock()

    def should_experiment(self, capability: str) -> bool:
        """判断某能力是否需要做实验。

        条件：
        1. 该能力有两个以上候选引擎（能组实验）
        2. 现有样本的置信区间过宽（width > 0.3）或样本不足
        3. 没有正在进行的同类实验
        """
        with self._lock:
            # 条件3：已有进行中的同类实验，不重复发起
            if capability in self._active_experiments:
                exp_id = self._active_experiments[capability]
                exp = self._experiments.get(exp_id)
                if exp and exp.status == "running":
                    return False

        # 条件1+2：检查CausalModel中的数据质量
        if self._model is None:
            return True  # 无CausalModel时，默认需要实验来积累数据

        try:
            stats = self._model.get_engine_stats(capability)
            if not stats or len(stats) < 2:
                return True  # 候选引擎不足，等其他路径判断

            # 检查置信区间宽度
            for engine_name, engine_stats in stats.items():
                ci_width = self._get_ci_width(engine_stats)
                if ci_width > 0.3:
                    return True  # 置信区间过宽，需要更多数据

            # 检查样本量
            min_samples = min(s.get("count", 0) for s in stats.values())
            if min_samples < self._min_samples_for_significance():
                return True

        except Exception:
            # CausalModel查询失败，保守地发起实验
            return True

        return False

    def create_experiment(self, capability: str, engines: List[str]) -> Experiment:
        """创建一个新的A/B实验，随机选两个引擎。

        Args:
            capability: 能力类型（如 web.search）
            engines: 候选引擎列表

        Returns:
            新创建的Experiment对象
        """
        if len(engines) < 2:
            raise ValueError(f"至少需要2个候选引擎，当前只有{len(engines)}个")

        # 随机选两个引擎
        selected = random.sample(engines, 2)
        exp_id = f"exp_{capability.replace('.', '_')}_{uuid.uuid4().hex[:8]}"

        experiment = Experiment(
            experiment_id=exp_id,
            capability=capability,
            engine_a=selected[0],
            engine_b=selected[1],
        )

        with self._lock:
            self._experiments[exp_id] = experiment
            self._active_experiments[capability] = exp_id

        return experiment

    def assign_engine(self, experiment_id: str) -> str:
        """为一次调用分配实验组（随机选A或B）。

        使用公平的随机分配，确保两组样本量大致平衡。
        """
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None:
                raise ValueError(f"实验 {experiment_id} 不存在")
            if exp.status != "running":
                raise ValueError(f"实验 {experiment_id} 状态为 {exp.status}，无法分配")

        # 公平分配：优先选样本量少的组
        count_a = len(exp.results_a)
        count_b = len(exp.results_b)

        if count_a < count_b:
            return exp.engine_a
        elif count_b < count_a:
            return exp.engine_b
        else:
            # 样本量相同时随机选
            return random.choice([exp.engine_a, exp.engine_b])

    def record_outcome(self, experiment_id: str, engine: str, success: bool,
                       latency_ms: float = 0, tokens: int = 0) -> None:
        """记录实验结果。

        Args:
            experiment_id: 实验ID
            engine: 执行引擎名
            success: 是否成功
            latency_ms: 延迟（毫秒）
            tokens: 消耗的token数
        """
        outcome = {
            "success": success,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "timestamp": time.time(),
        }

        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None:
                raise ValueError(f"实验 {experiment_id} 不存在")
            if exp.status != "running":
                return  # 实验已结束，忽略迟到的结果

            if engine == exp.engine_a:
                exp.results_a.append(outcome)
            elif engine == exp.engine_b:
                exp.results_b.append(outcome)
            else:
                raise ValueError(f"引擎 {engine} 不属于实验 {experiment_id}")

            # 检查是否样本充足，自动结束实验
            if (len(exp.results_a) >= exp.sample_size and
                    len(exp.results_b) >= exp.sample_size):
                self._finalize_experiment(experiment_id)

    def analyze(self, experiment_id: str) -> Dict[str, Any]:
        """分析实验结果——用双样本比例检验（z-test）判断是否有显著差异。

        返回：
        - winner: 胜出引擎
        - p_value: p值
        - effect_size: 效应量（绝对差异）
        - confidence: 置信级别
        - recommendation: 建议（使用胜出引擎 / 需要更多样本 / 无显著差异）
        """
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None:
                raise ValueError(f"实验 {experiment_id} 不存在")

        n_a = len(exp.results_a)
        n_b = len(exp.results_b)

        if n_a == 0 or n_b == 0:
            return {
                "winner": None,
                "p_value": None,
                "effect_size": None,
                "confidence": "low",
                "recommendation": "需要更多样本",
            }

        # 计算成功率
        s_a = sum(1 for r in exp.results_a if r["success"])
        s_b = sum(1 for r in exp.results_b if r["success"])
        rate_a = s_a / n_a
        rate_b = s_b / n_b

        # 双样本比例z检验
        z_stat, p_value = self._z_test_proportions(n_a, s_a, n_b, s_b)

        # 效应量（绝对差异）
        effect_size = abs(rate_a - rate_b)

        # 判断胜出
        winner = None
        confidence = "low"
        recommendation = "需要更多样本"

        if p_value is not None and p_value < exp.significance_level:
            winner = exp.engine_a if rate_a > rate_b else exp.engine_b
            # 置信级别根据p值
            if p_value < 0.01:
                confidence = "high"
            elif p_value < 0.03:
                confidence = "medium"
            else:
                confidence = "low"
            recommendation = f"建议使用胜出引擎 {winner}"
        elif n_a >= exp.sample_size and n_b >= exp.sample_size:
            # 样本够但不显著
            recommendation = "无显著差异，可任选（建议选延迟低的）"
            winner = exp.engine_a  # 平手时默认A

        # 计算平均延迟
        avg_latency_a = (sum(r["latency_ms"] for r in exp.results_a) / n_a) if n_a else 0
        avg_latency_b = (sum(r["latency_ms"] for r in exp.results_b) / n_b) if n_b else 0

        return {
            "winner": winner,
            "p_value": round(p_value, 6) if p_value is not None else None,
            "effect_size": round(effect_size, 4),
            "confidence": confidence,
            "recommendation": recommendation,
            "engine_a": {
                "name": exp.engine_a,
                "success_rate": round(rate_a, 4),
                "avg_latency_ms": round(avg_latency_a, 2),
                "samples": n_a,
            },
            "engine_b": {
                "name": exp.engine_b,
                "success_rate": round(rate_b, 4),
                "avg_latency_ms": round(avg_latency_b, 2),
                "samples": n_b,
            },
        }

    def _z_test_proportions(self, n1: int, s1: int, n2: int, s2: int) -> Tuple[float, Optional[float]]:
        """双样本比例z检验。

        H0: p1 = p2（两引擎成功率无差异）
        H1: p1 != p2（双尾检验）

        返回 (z_stat, p_value)。若条件不满足（如某个比例是0或1），返回 (0, 1.0)。
        """
        if n1 == 0 or n2 == 0:
            return (0.0, 1.0)

        p1 = s1 / n1
        p2 = s2 / n2
        p_pool = (s1 + s2) / (n1 + n2)

        # 池化比例的标准误
        se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))

        if se == 0:
            return (0.0, 1.0)  # 两个比例完全相同或样本太少

        z_stat = (p1 - p2) / se

        # 双尾p值（用正态分布近似）
        p_value = 2 * (1 - self._normal_cdf(abs(z_stat)))

        return (round(z_stat, 4), round(p_value, 6))

    def _normal_cdf(self, x: float) -> float:
        """标准正态分布CDF的近似（Abramowitz & Stegun近似）。"""
        # 参考：https://en.wikipedia.org/wiki/Normal_distribution#Numerical_approximations
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911

        sign = 1.0 if x >= 0 else -1.0
        x = abs(x) / math.sqrt(2.0)

        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)

        return 0.5 * (1.0 + sign * y)

    def integrate_to_causal_model(self, experiment: Experiment) -> None:
        """把实验结果写入CausalModel，替换原有observational数据。

        实验数据是interventional（do-calculus级别），优先级高于observational。
        这是因果之梯第二层的核心：do(X)的数据替换P(Y|X)的数据。
        """
        if self._model is None:
            return

        analysis = self.analyze(experiment.experiment_id)

        # 计算实验级的因果效应
        n_a = len(experiment.results_a)
        n_b = len(experiment.results_b)
        if n_a == 0 or n_b == 0:
            return

        rate_a = sum(1 for r in experiment.results_a if r["success"]) / n_a
        rate_b = sum(1 for r in experiment.results_b if r["success"]) / n_b

        # 准备interventional数据
        intervention_data = {
            "type": "interventional",  # 标记为do-calculus级别数据
            "experiment_id": experiment.experiment_id,
            "capability": experiment.capability,
            "engine_a": experiment.engine_a,
            "engine_b": experiment.engine_b,
            "effect_size": abs(rate_a - rate_b),
            "p_value": analysis.get("p_value"),
            "winner": analysis.get("winner"),
            "samples_a": n_a,
            "samples_b": n_b,
            "timestamp": time.time(),
        }

        # 写入CausalModel
        try:
            self._model.record_intervention(
                capability=experiment.capability,
                data=intervention_data,
            )
        except Exception:
            pass  # CausalModel不支持intervention时静默跳过

        # 持久化实验数据到distiller
        if self._distiller is not None:
            try:
                self._distiller.record(
                    category="causal_experiment",
                    data=experiment.to_dict(),
                )
            except Exception:
                pass

    def get_active_experiment(self, capability: str) -> Optional[Experiment]:
        """获取某能力的活跃实验。"""
        with self._lock:
            exp_id = self._active_experiments.get(capability)
            if exp_id:
                return self._experiments.get(exp_id)
        return None

    def cancel_experiment(self, experiment_id: str) -> None:
        """取消实验。"""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp and exp.status == "running":
                exp.status = "cancelled"
                exp.completed_at = time.time()
                # 清理活跃实验映射
                if self._active_experiments.get(exp.capability) == experiment_id:
                    del self._active_experiments[exp.capability]

    def list_experiments(self, status: str = None) -> List[Dict[str, Any]]:
        """列出所有实验。"""
        with self._lock:
            experiments = list(self._experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]

        return [e.to_dict() for e in experiments]

    def _finalize_experiment(self, experiment_id: str) -> None:
        """自动结束实验（样本充足时）。"""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None or exp.status != "running":
                return

            exp.status = "completed"
            exp.completed_at = time.time()

            # 分析结果
            analysis = self.analyze(experiment_id)
            exp.winner = analysis.get("winner")
            exp.p_value = analysis.get("p_value")
            exp.effect_size = analysis.get("effect_size")

            # 清理活跃实验映射
            if self._active_experiments.get(exp.capability) == experiment_id:
                del self._active_experiments[exp.capability]

        # 集成到CausalModel
        self.integrate_to_causal_model(exp)

    def _get_ci_width(self, engine_stats: Dict[str, Any]) -> float:
        """计算引擎统计的置信区间宽度。"""
        count = engine_stats.get("count", 0)
        if count < 2:
            return 1.0  # 样本太少，视为极宽

        success_rate = engine_stats.get("success_rate", 0.5)
        # Wilson score interval的近似宽度
        z = 1.96  # 95%置信水平
        se = math.sqrt(success_rate * (1 - success_rate) / count)
        return 2 * z * se

    def _min_samples_for_significance(self) -> int:
        """达到统计显著性所需的最小样本量。"""
        # 简化估计：检测0.2效应量，power=0.8，alpha=0.05
        return 20  # 约20个样本/组
