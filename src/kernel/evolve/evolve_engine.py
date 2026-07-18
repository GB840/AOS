"""Evolve —— 智能体自动进化引擎。

基于使用数据和用户反馈，自动优化智能体的：
- 提示词（多版本 A/B 测试）
- 工作流结构（步骤顺序、重试策略）
- 模型选择（简单任务用小模型，复杂任务用大模型）

设计原则：
- 数据驱动：所有优化都基于 Pulse 的真实数据，不拍脑袋
- 灰度发布：先给少数用户测，效果好再全量
- 可回滚：效果不好随时退回去
- 自动读取：直接从 Pulse 读数据，不用手动喂
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


def _default_pulse():
    """懒加载 PulseCollector（避免循环 import）。"""
    try:
        from kernel.pulse.pulse_collector import get_pulse_collector
        return get_pulse_collector()
    except Exception:
        return None


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


@dataclass
class OptimizationProposal:
    """一个可执行的优化提案。

    从 Evolve 分析结果生成，可以一键应用到工作流或内容策略。
    包含变更细节、风险等级、预期收益，支持回滚。
    """
    id: str = ""
    workflow_id: str = ""  # 目标工作流（如果是产品飞轮）
    proposal_type: str = ""  # step_retry / step_timeout / add_fallback /
                             # prompt_tune / content_keyword / content_tone / ...
    title: str = ""
    description: str = ""
    risk_level: str = "low"  # low / medium / high
    expected_benefit: str = ""  # 预期收益描述
    auto_applicable: bool = False  # 是否可以自动应用（低风险）
    applied: bool = False
    applied_at: str = ""
    rollback_snapshot: Dict[str, Any] = field(default_factory=dict)  # 应用前的快照，用于回滚
    change: Dict[str, Any] = field(default_factory=dict)  # 具体变更内容
    created_at: str = ""
    source: str = "evolve"  # evolve / autoskill / content_feedback / ...
    # ── HITL（人机协作审批）──
    approved: bool = False
    approved_at: str = ""
    rejected: bool = False
    reject_reason: str = ""


class EvolveEngine:
    """自动进化引擎。"""

    def __init__(self, pulse=None):
        self._pulse = pulse or _default_pulse()
        self._ab_tests: Dict[str, ABTest] = {}
        self._load_tests()

    def set_pulse(self, pulse) -> None:
        self._pulse = pulse

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

    # ── 自动优化建议（从 Pulse 读数据） ──

    def analyze_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """从 Pulse 读数据，分析一个工作流的健康状况并给出优化建议。

        这是 Evolve 的核心入口——直接用真实数据说话。
        """
        if not self._pulse:
            return {
                "ok": False,
                "error": "Pulse 不可用，无法分析",
                "suggestions": [],
            }

        # 从 Pulse 拉数据
        metrics = self._pulse.get_agent_metrics(workflow_id)
        failure_analysis = self._pulse.get_failure_analysis(workflow_id)

        if not metrics or metrics.get("total_runs", 0) == 0:
            return {
                "ok": True,
                "workflow_id": workflow_id,
                "total_runs": 0,
                "message": "数据不足，暂无建议（至少运行 1 次后有分析）",
                "suggestions": [],
            }

        # 生成优化建议
        suggestions = self._generate_suggestions(metrics, failure_analysis)

        # 失败步骤诊断
        step_diagnosis = self._diagnose_failure_steps(failure_analysis)

        return {
            "ok": True,
            "workflow_id": workflow_id,
            "metrics": metrics,
            "failure_analysis": failure_analysis,
            "suggestions": suggestions,
            "step_diagnosis": step_diagnosis,
            "overall_health": self._health_score(metrics),
        }

    def suggest_optimizations(self, workflow_id: str, metrics: Dict = None) -> List[Dict[str, Any]]:
        """生成优化建议。

        两种调用方式：
        1. suggest_optimizations(workflow_id) —— 从 Pulse 读取数据生成建议
        2. suggest_optimizations(workflow_id, metrics_dict) —— 基于给定的 metrics 生成建议

        Args:
            workflow_id: 工作流 ID
            metrics: 可选，直接传入 metrics 字典（含 success_rate, avg_duration 等）

        Returns:
            优化建议列表
        """
        if metrics is not None:
            # 直接用传入的 metrics 生成建议（兼容旧接口）
            failure_analysis = self._pulse.get_failure_analysis(workflow_id) if self._pulse else {}
            return self._generate_suggestions(metrics, failure_analysis)

        # 从 Pulse 读数据
        result = self.analyze_workflow(workflow_id)
        return result.get("suggestions", [])

    # ── 优化提案系统（闭环写回）──

    def generate_proposals(self, workflow_id: str,
                            workflow_store=None) -> List[OptimizationProposal]:
        """为工作流生成可执行的优化提案。

        从 Pulse 数据分析结果出发，生成一组可以一键应用的提案。
        低风险提案标 auto_applicable=True，可以自动应用；
        中高风险需要人工确认。

        Args:
            workflow_id: 工作流 ID
            workflow_store: 可选的 WorkflowStore 实例（不传则用全局单例）

        Returns:
            OptimizationProposal 列表，按优先级排序
        """
        import uuid
        proposals: List[OptimizationProposal] = []
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        # 从 Pulse 读数据
        analysis = self.analyze_workflow(workflow_id)
        if not analysis.get("ok"):
            return proposals

        metrics = analysis.get("metrics", {})
        failure_analysis = analysis.get("failure_analysis", {})
        failure_steps = failure_analysis.get("step_failures", {})
        success_rate = metrics.get("success_rate", 0) / 100.0  # success_rate 是百分比
        avg_duration = metrics.get("avg_duration", 0)
        total_runs = metrics.get("total_runs", 0)

        # 数据量不够就不生成提案
        if total_runs < 5:
            return proposals

        # 提案 1：成功率低 → 给失败步骤加重试
        if success_rate < 0.7 and failure_steps:
            for step_name, fail_count in list(failure_steps.items())[:3]:
                prop = OptimizationProposal(
                    id=uuid.uuid4().hex[:8],
                    workflow_id=workflow_id,
                    proposal_type="step_retry",
                    title=f"给失败步骤「{step_name}」加重试",
                    description=f"该步骤失败 {fail_count} 次，建议增加重试次数提高成功率",
                    risk_level="low",
                    expected_benefit="预计成功率提升 10-20%",
                    auto_applicable=True,
                    change={
                        "action": "update_step",
                        "step_name": step_name,
                        "field": "retry",
                        "value": 2,
                        "old_value": 0,
                    },
                    created_at=now,
                    source="evolve",
                )
                proposals.append(prop)

        # 提案 2：速度慢 → 调整超时和并发
        if avg_duration > 30000:  # >30秒
            prop = OptimizationProposal(
                id=uuid.uuid4().hex[:8],
                workflow_id=workflow_id,
                proposal_type="optimize_duration",
                title="优化执行速度",
                description=f"平均耗时 {avg_duration/1000:.1f} 秒，建议检查是否可以并行化或精简步骤",
                risk_level="medium",
                expected_benefit="预计耗时降低 20-40%",
                auto_applicable=False,
                change={
                    "action": "review_steps",
                    "suggestion": "检查步骤依赖关系，可并行的放入 parallel_group",
                },
                created_at=now,
                source="evolve",
            )
            proposals.append(prop)

        # 提案 3：成功率高但用户评分低 → 优化提示词
        if success_rate >= 0.8 and metrics.get("avg_rating", 5) < 3.5:
            prop = OptimizationProposal(
                id=uuid.uuid4().hex[:8],
                workflow_id=workflow_id,
                proposal_type="prompt_tune",
                title="优化提示词提升用户满意度",
                description=f"技术成功率 {success_rate*100:.0f}% 但用户评分偏低，建议调整提示词",
                risk_level="medium",
                expected_benefit="预计用户评分提升 0.5-1 星",
                auto_applicable=False,
                change={
                    "action": "ab_test_suggestion",
                    "suggestion": "创建 A/B 测试，对比新旧提示词效果",
                },
                created_at=now,
                source="evolve",
            )
            proposals.append(prop)

        # 提案 4：Token 成本过高 → 优化 max_tokens / 切小模型（Task 1: Cost Observability）
        cost_proposals = self._generate_cost_proposals(
            metrics, workflow_id, now, workflow_store,
        )
        proposals.extend(cost_proposals)

        # 按风险等级排序：低风险在前（可以自动应用）
        risk_order = {"low": 0, "medium": 1, "high": 2}
        proposals.sort(key=lambda p: risk_order.get(p.risk_level, 3))

        # 持久化提案
        self._save_proposal(workflow_id, proposals)

        return proposals

    def _generate_cost_proposals(self, metrics: Dict[str, Any],
                                  workflow_id: str, now: str,
                                  workflow_store=None) -> List[OptimizationProposal]:
        """基于成本数据生成成本优化提案（Task 1: Cost Observability 闭环）。

        3 类成本提案：
        1. 单次平均 token 高 → 降低 max_tokens（低风险，可自动应用）
        2. 总成本高 + 用了云端模型 → 切换本地模型（中风险，需确认）
        3. 成本告警触发 → 提示人工排查（高风险）

        Args:
            metrics: Pulse metrics 字典
            workflow_id: 工作流 ID
            now: 当前时间字符串
            workflow_store: 可选的 WorkflowStore（不传则用全局单例）
        """
        import uuid
        proposals: List[OptimizationProposal] = []
        total_cost = metrics.get("total_cost_usd", 0)
        total_tokens = metrics.get("total_tokens", 0)
        total_runs = metrics.get("total_runs", 0)

        if total_runs < 5:
            return proposals

        # 平均每次运行的 token 数
        avg_tokens_per_run = total_tokens / total_runs if total_runs > 0 else 0

        # 尝试找该工作流里第一个 LLM 类步骤的真实 name（用于精确 apply）
        llm_step_name = self._find_llm_step_name(workflow_id, workflow_store)

        # 提案 1：单次 token 量高 → 建议降低 max_tokens（低风险，自动应用）
        # 阈值：平均每次运行 > 4000 tokens（GPT-4o 单次 4K token 已经够多数对话）
        if avg_tokens_per_run > 4000 and llm_step_name:
            prop = OptimizationProposal(
                id=uuid.uuid4().hex[:8],
                workflow_id=workflow_id,
                proposal_type="cost_optimization",
                title="降低 max_tokens 控制成本",
                description=(
                    f"平均每次运行消耗 {int(avg_tokens_per_run)} tokens，"
                    f"建议把 LLM 步骤「{llm_step_name}」的 max_tokens 限制在 2048（多数任务足够）"
                ),
                risk_level="low",
                expected_benefit=f"预计 Token 成本降低 30-50%（${total_cost*0.4:.4f}/月）",
                auto_applicable=True,
                change={
                    "action": "update_step",
                    "step_name": llm_step_name,  # 用真实 step_name 让 apply_proposal 能精确匹配
                    "field": "max_tokens",
                    "value": 2048,
                    "old_value": "unlimited",
                    "suggestion": f"对步骤「{llm_step_name}」限制 max_tokens=2048",
                },
                created_at=now,
                source="cost_observability",
            )
            proposals.append(prop)

        # 提案 2：总成本 > $1 且用了云端模型 → 建议切换本地（中风险）
        if total_cost > 1.0:
            prop = OptimizationProposal(
                id=uuid.uuid4().hex[:8],
                workflow_id=workflow_id,
                proposal_type="model_switch",
                title="切换到本地模型降低成本",
                description=(
                    f"该工作流累计成本 ${total_cost:.4f}，"
                    f"建议把简单步骤切换到本地 ollama/qwen2.5:7b（零成本）"
                ),
                risk_level="medium",
                expected_benefit=f"预计月度成本降低 60-90%（节省 ${total_cost*0.7:.4f}/月）",
                auto_applicable=False,
                change={
                    "action": "switch_to_local_model",
                    "target_engine": "ollama",
                    "target_model": "qwen2.5:7b",
                    "suggestion": "对简单任务（搜索总结、关键词提取）切换到本地 ollama，复杂任务保留云端",
                },
                created_at=now,
                source="cost_observability",
            )
            proposals.append(prop)

        # 提案 3：从 Pulse 拉成本告警 → 高风险提案，提示人工处理
        try:
            if self._pulse is not None and hasattr(self._pulse, "check_cost_alerts"):
                triggered = self._pulse.check_cost_alerts()
                for alert in triggered:
                    # 同一告警同一工作流只生成一条提案
                    if any(p.change.get("alert_id") == alert.get("alert_id")
                           for p in proposals):
                        continue
                    prop = OptimizationProposal(
                        id=uuid.uuid4().hex[:8],
                        workflow_id=workflow_id,
                        proposal_type="cost_alert",
                        title=f"成本告警触发：{alert.get('alert_name', '')}",
                        description=(
                            f"告警 {alert.get('alert_name')} 触发，"
                            f"实际成本 ${alert.get('actual_cost', 0):.4f} "
                            f"超过阈值 ${alert.get('threshold_usd', 0):.4f}"
                        ),
                        risk_level="high",
                        expected_benefit="人工排查异常 token 用量，避免成本失控",
                        auto_applicable=False,
                        change={
                            "action": "manual_investigation",
                            "alert_id": alert.get("alert_id"),
                            "suggestion": "检查最近运行的步骤，定位 token 消耗异常的源头",
                        },
                        created_at=now,
                        source="cost_alert",
                    )
                    proposals.append(prop)
        except Exception as e:
            logger.debug("成本告警提案生成失败: %s", e)

        return proposals

    def _find_llm_step_name(self, workflow_id: str, workflow_store=None) -> str:
        """懒加载 WorkflowStore，找该工作流里第一个 LLM 类步骤的 name。

        Args:
            workflow_id: 工作流 ID
            workflow_store: 可选的 WorkflowStore（不传则用全局单例）

        Returns:
            step.name 或 step.id（找不到返回空字符串）
        """
        try:
            if workflow_store is None:
                from kernel.studio.workflow_store import get_workflow_store
                workflow_store = get_workflow_store()
            wf = workflow_store.get(workflow_id)
            if wf is None:
                return ""
            for step in wf.steps:
                cap = (step.capability or "").lower()
                if "llm" in cap or "chat" in cap or "inference" in cap:
                    return step.name or step.id or ""
            return ""
        except Exception as e:
            logger.debug("查找 LLM 步骤失败: %s", e)
            return ""

    def apply_proposal(self, proposal_id: str, workflow_store=None) -> Dict[str, Any]:
        """应用一个优化提案到工作流。

        低风险提案可以直接自动应用；中高风险建议先人工确认。
        应用前保存回滚快照，失败自动回滚。

        Args:
            proposal_id: 提案 ID
            workflow_store: WorkflowStore 实例（为空用全局单例）

        Returns:
            {ok, proposal_id, applied, old_value, new_value, rollback_available}
        """
        if workflow_store is None:
            from kernel.studio.workflow_store import get_workflow_store
            workflow_store = get_workflow_store()

        # 找提案
        proposal = self._find_proposal(proposal_id)
        if proposal is None:
            return {"ok": False, "error": f"提案不存在: {proposal_id}"}

        if proposal.applied:
            return {"ok": False, "error": "该提案已经应用过了"}

        try:
            # 获取工作流
            wf = workflow_store.get(proposal.workflow_id)
            if wf is None:
                return {"ok": False, "error": f"工作流不存在: {proposal.workflow_id}"}

            # 保存回滚快照
            proposal.rollback_snapshot = {
                "workflow_id": wf.id,
                "version": wf.version,
                "steps_json": json.dumps([asdict(s) for s in wf.steps]),
            }

            # 根据提案类型执行变更
            change = proposal.change
            action = change.get("action", "")

            if action == "update_step":
                # 更新某个步骤的字段（如 retry、timeout）
                step_name = change.get("step_name", "")
                field = change.get("field", "")
                new_value = change.get("value")

                target_step = None
                for step in wf.steps:
                    if step.name == step_name or step.id == step_name:
                        target_step = step
                        break

                if target_step is None:
                    return {"ok": False, "error": f"步骤不存在: {step_name}"}

                old_value = getattr(target_step, field, None)
                setattr(target_step, field, new_value)
                change["old_value"] = old_value

                # 保存工作流
                wf.version = self._bump_version(wf.version)
                workflow_store.save(wf)

                proposal.applied = True
                proposal.applied_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._update_proposal(proposal)

                return {
                    "ok": True,
                    "proposal_id": proposal.id,
                    "applied": True,
                    "step": step_name,
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "rollback_available": True,
                }

            elif action == "add_step":
                # 新增步骤（如加 fallback 步骤）
                from kernel.studio.workflow_models import WorkflowStep
                step_data = change.get("step_data", {})
                new_step = WorkflowStep(**step_data)

                # 保存回滚用的原始 steps
                proposal.rollback_snapshot["steps_count"] = len(wf.steps)

                position = change.get("position", len(wf.steps))
                wf.steps.insert(position, new_step)

                wf.version = self._bump_version(wf.version)
                workflow_store.save(wf)

                proposal.applied = True
                proposal.applied_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._update_proposal(proposal)

                return {
                    "ok": True,
                    "proposal_id": proposal.id,
                    "applied": True,
                    "new_step_id": new_step.id,
                    "position": position,
                    "rollback_available": True,
                }

            else:
                return {
                    "ok": False,
                    "error": f"不支持的变更类型: {action}，需要人工处理",
                    "suggestion": change.get("suggestion", ""),
                    "rollback_available": False,
                }

        except Exception as e:
            logger.warning("应用提案失败: %s", e)
            return {"ok": False, "error": str(e)}

    def rollback_proposal(self, proposal_id: str, workflow_store=None) -> Dict[str, Any]:
        """回滚一个已应用的提案。

        Args:
            proposal_id: 提案 ID
            workflow_store: WorkflowStore 实例

        Returns:
            {ok, proposal_id, rolled_back}
        """
        if workflow_store is None:
            from kernel.studio.workflow_store import get_workflow_store
            workflow_store = get_workflow_store()

        proposal = self._find_proposal(proposal_id)
        if proposal is None:
            return {"ok": False, "error": f"提案不存在: {proposal_id}"}
        if not proposal.applied:
            return {"ok": False, "error": "该提案还没应用，不能回滚"}

        try:
            snapshot = proposal.rollback_snapshot
            wf = workflow_store.get(snapshot.get("workflow_id", ""))
            if wf is None:
                return {"ok": False, "error": "工作流不存在"}

            # 恢复 steps
            steps_data = json.loads(snapshot.get("steps_json", "[]"))
            from kernel.studio.workflow_models import WorkflowStep
            wf.steps = [WorkflowStep(**d) for d in steps_data]

            wf.version = self._bump_version(wf.version)
            workflow_store.save(wf)

            proposal.applied = False
            proposal.applied_at = ""
            self._update_proposal(proposal)

            return {"ok": True, "proposal_id": proposal.id, "rolled_back": True}

        except Exception as e:
            logger.warning("回滚提案失败: %s", e)
            return {"ok": False, "error": str(e)}

    def auto_apply_low_risk(self, workflow_id: str, workflow_store=None) -> List[Dict[str, Any]]:
        """自动应用低风险提案。

        只应用 risk_level=low 且 auto_applicable=True 的提案。
        这是产品飞轮闭环的核心——低风险优化全自动，高风险人工确认。

        Args:
            workflow_id: 工作流 ID
            workflow_store: WorkflowStore 实例

        Returns:
            应用结果列表
        """
        proposals = self.generate_proposals(workflow_id)
        results = []

        for prop in proposals:
            if prop.risk_level == "low" and prop.auto_applicable and not prop.applied:
                result = self.apply_proposal(prop.id, workflow_store)
                results.append(result)

        return results

    def list_proposals(self, workflow_id: str = "") -> List[OptimizationProposal]:
        """列出优化提案。"""
        return self._load_proposals(workflow_id)

    # ── HITL（人机协作审批）──

    def list_pending_approvals(self, workflow_id: str = "") -> List[OptimizationProposal]:
        """列出待人工确认的高/中风险提案（未应用、未拒绝）。

        低风险提案由 workflow_runner 自动应用（见 _maybe_evolve），
        中高风险才进入人工审批队列——这就是「人在环中」的边界。
        """
        pending = []
        for p in self._load_proposals(workflow_id):
            if not p.applied and not p.rejected and p.risk_level in ("medium", "high"):
                pending.append(p)
        # 按风险等级排序：high 优先
        risk_order = {"high": 0, "medium": 1}
        pending.sort(key=lambda p: risk_order.get(p.risk_level, 9))
        return pending

    def approve_proposal(self, proposal_id: str,
                        workflow_store=None) -> Dict[str, Any]:
        """人工确认并通过一个提案 → 应用它。

        高风险提案经此入口确认后才真正改写工作流/内容策略；
        应用前自动保存回滚快照（apply_proposal 内部已做），可经 /proposals/{id}/rollback 回退。
        """
        proposal = self._find_proposal(proposal_id)
        if proposal is None:
            return {"ok": False, "error": f"提案不存在: {proposal_id}"}
        if proposal.rejected:
            return {"ok": False, "error": "该提案已被拒绝，无法确认"}
        if proposal.applied:
            return {"ok": False, "error": "该提案已应用"}
        proposal.approved = True
        proposal.approved_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._update_proposal(proposal)
        # 应用（内部会再次 _update_proposal 写 applied=True）
        result = self.apply_proposal(proposal_id, workflow_store)
        result["approved_at"] = proposal.approved_at
        return result

    def reject_proposal(self, proposal_id: str, reason: str = "") -> Dict[str, Any]:
        """人工拒绝一个提案（不应用，仅标记，便于审计）。"""
        proposal = self._find_proposal(proposal_id)
        if proposal is None:
            return {"ok": False, "error": f"提案不存在: {proposal_id}"}
        if proposal.applied:
            return {"ok": False, "error": "该提案已应用，无法拒绝"}
        proposal.rejected = True
        proposal.reject_reason = reason
        self._update_proposal(proposal)
        return {"ok": True, "proposal_id": proposal_id, "rejected": True,
                "reject_reason": reason}

    # ── 提案持久化 ──

    def _proposals_path(self, workflow_id: str = "") -> str:
        base = _evolve_dir()
        if workflow_id:
            return os.path.join(base, f"proposals_{workflow_id}.jsonl")
        return os.path.join(base, "proposals_all.jsonl")

    def _save_proposal(self, workflow_id: str, proposals: List[OptimizationProposal]) -> None:
        """保存提案到 JSONL。"""
        path = self._proposals_path(workflow_id)
        try:
            with open(path, "a", encoding="utf-8") as f:
                for p in proposals:
                    f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("保存提案失败: %s", e)

    def _load_proposals(self, workflow_id: str = "") -> List[OptimizationProposal]:
        """加载提案。"""
        path = self._proposals_path(workflow_id)
        proposals = []
        if not os.path.exists(path):
            return proposals
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        proposals.append(OptimizationProposal(**data))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.debug("加载提案失败: %s", e)
        return proposals

    def _find_proposal(self, proposal_id: str) -> Optional[OptimizationProposal]:
        """按 ID 找提案。"""
        # 扫所有工作流的提案文件
        base = _evolve_dir()
        if not os.path.exists(base):
            return None
        for fname in os.listdir(base):
            if fname.startswith("proposals_") and fname.endswith(".jsonl"):
                path = os.path.join(base, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                if data.get("id") == proposal_id:
                                    return OptimizationProposal(**data)
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    continue
        return None

    def _update_proposal(self, proposal: OptimizationProposal) -> None:
        """更新提案状态（重写整个文件）。"""
        if not proposal.workflow_id:
            return
        path = self._proposals_path(proposal.workflow_id)
        all_props = self._load_proposals(proposal.workflow_id)

        # 替换同 ID 的
        updated = []
        for p in all_props:
            if p.id == proposal.id:
                updated.append(proposal)
            else:
                updated.append(p)

        # 如果是新的就追加
        if not any(p.id == proposal.id for p in all_props):
            updated.append(proposal)

        try:
            with open(path, "w", encoding="utf-8") as f:
                for p in updated:
                    f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("更新提案失败: %s", e)

    @staticmethod
    def _bump_version(version: str) -> str:
        """小版本号 +1。"""
        parts = version.split(".")
        if len(parts) == 3:
            try:
                parts[2] = str(int(parts[2]) + 1)
                return ".".join(parts)
            except ValueError:
                pass
        return version + "-1"

    def _generate_suggestions(self, metrics: Dict, failure_analysis: Dict) -> List[Dict]:
        """基于 Pulse 数据生成可执行的优化建议。"""
        suggestions = []
        success_rate = metrics.get("success_rate", 0)
        avg_duration = metrics.get("avg_duration", 0)
        total_runs = metrics.get("total_runs", 0)
        step_stats = metrics.get("step_stats", {})
        step_failures = failure_analysis.get("step_failures", {})
        failure_reasons = failure_analysis.get("failure_reasons", {})

        # 建议 1：成功率低？
        if success_rate < 70 and total_runs >= 3:
            suggestions.append({
                "type": "success_rate",
                "priority": "high",
                "suggestion": "成功率偏低，建议增加失败重试和故障转移",
                "detail": f"当前成功率 {success_rate:.1f}%（{total_runs} 次运行），目标建议 > 80%",
                "action": "在工作流关键步骤增加 retry=2，并配置备用引擎",
            })

        # 建议 2：太慢？
        if avg_duration > 30 and total_runs >= 3:
            # 找最慢的步骤
            slowest_step = ""
            slowest_time = 0
            for step_name, stat in step_stats.items():
                avg = stat.get("avg_duration", 0) if isinstance(stat, dict) else 0
                if avg > slowest_time:
                    slowest_time = avg
                    slowest_step = step_name

            suggestions.append({
                "type": "performance",
                "priority": "medium" if avg_duration < 60 else "high",
                "suggestion": f"平均耗时较长（{avg_duration:.1f}s），建议优化慢步骤",
                "detail": f"最慢步骤: {slowest_step or '未知'}（约 {slowest_time:.1f}s）",
                "action": "考虑用更快的模型/引擎，或者优化提示词减少 tokens",
            })

        # 建议 3：有失败步骤？
        if step_failures:
            worst_step = max(step_failures.items(), key=lambda x: x[1])
            suggestions.append({
                "type": "step_failure",
                "priority": "high",
                "suggestion": f"步骤「{worst_step[0]}」失败 {worst_step[1]} 次，建议排查",
                "detail": f"失败原因分布: {list(failure_reasons.keys())[:5]}",
                "action": "检查该步骤的提示词、参数配置、引擎健康状态",
            })

        # 建议 4：A/B 测试找最优提示词
        if total_runs >= 5 and success_rate >= 50:
            suggestions.append({
                "type": "prompt_ab_test",
                "priority": "medium",
                "suggestion": "数据量够了，可以创建提示词 A/B 测试找最优版本",
                "detail": f"已有 {total_runs} 次运行作为基线，可以开始 A/B 测试",
                "action": "用 create_ab_test() 创建两个变体的提示词对比测试",
            })

        # 建议 5：模型选择优化
        if success_rate >= 80 and avg_duration > 10:
            suggestions.append({
                "type": "model_optimization",
                "priority": "low",
                "suggestion": "成功率达标但偏慢，考虑按任务复杂度自动选模型",
                "detail": "简单任务用小模型（省钱快），复杂任务用大模型（效果好）",
                "action": "配置模型路由策略：根据输入长度/复杂度动态选择",
            })

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: priority_order.get(s.get("priority", "low"), 2))
        return suggestions

    def _diagnose_failure_steps(self, failure_analysis: Dict) -> List[Dict]:
        """诊断失败步骤，给出可能的根因。"""
        diagnosis = []
        step_failures = failure_analysis.get("step_failures", {})
        failure_reasons = failure_analysis.get("failure_reasons", {})

        for step, count in sorted(step_failures.items(), key=lambda x: -x[1]):
            possible_causes = []
            for reason, rc in failure_reasons.items():
                reason_lower = str(reason).lower()
                if "timeout" in reason_lower or "超时" in reason_lower:
                    possible_causes.append("超时：引擎响应慢或任务太重")
                if "error" in reason_lower or "失败" in reason_lower:
                    possible_causes.append("引擎错误：可能是配置问题或依赖缺失")
                if "rate" in reason_lower or "限流" in reason_lower:
                    possible_causes.append("限流：请求太频繁，需要加退避")

            if not possible_causes:
                possible_causes.append("未知原因，需要查看详细日志")

            diagnosis.append({
                "step": step,
                "failure_count": count,
                "possible_causes": list(set(possible_causes)),
            })

        return diagnosis

    @staticmethod
    def _health_score(metrics: Dict) -> str:
        """给工作流打一个健康度分：excellent / good / fair / poor。"""
        success_rate = metrics.get("success_rate", 0)
        total_runs = metrics.get("total_runs", 0)

        if total_runs < 3:
            return "insufficient_data"
        if success_rate >= 90:
            return "excellent"
        if success_rate >= 70:
            return "good"
        if success_rate >= 50:
            return "fair"
        return "poor"

    # ── 批量分析 ──

    def analyze_all(self, limit: int = 20) -> List[Dict]:
        """分析所有有数据的工作流，返回健康度排行。"""
        if not self._pulse:
            return []

        all_metrics = self._pulse.get_all_metrics(limit=limit)
        results = []
        for m in all_metrics:
            wf_id = m.get("workflow_id", m.get("id", ""))
            analysis = self.analyze_workflow(wf_id)
            if analysis.get("ok"):
                results.append(analysis)

        # 按健康度排序
        health_order = {"excellent": 0, "good": 1, "fair": 2, "poor": 3, "insufficient_data": 4}
        results.sort(key=lambda r: health_order.get(r.get("overall_health", "poor"), 3))
        return results

    # ── 内容飞轮数据分析 ──

    def analyze_content_feedback(self, keyword: str = "") -> Dict[str, Any]:
        """分析内容飞轮的反馈数据，给出内容优化建议。

        从 Pulse 中读取 Echo 采集的全网反馈，分析情感分布、热点关键词、
        用户需求，生成内容优化建议。

        Args:
            keyword: 内容关键词（为空则返回所有内容反馈的汇总）

        Returns:
            {ok, keyword, total_count, sentiment_distribution, top_keywords,
             user_needs, suggestions, data_source}
        """
        if not self._pulse:
            return {
                "ok": False,
                "error": "Pulse 不可用，无法分析内容反馈",
                "suggestions": [],
            }

        try:
            # 从 Pulse 读取内容反馈数据
            content_feedbacks_raw = self._pulse.get_feedbacks(
                feedback_type="content_feedback",
                limit=100,
            )

            # 解析出实际的内容数据（feedback 字段里）
            content_feedbacks = []
            for raw in content_feedbacks_raw:
                fb = raw.get("feedback", {})
                if fb.get("type") == "content_feedback":
                    if not keyword or keyword in fb.get("keyword", ""):
                        content_feedbacks.append(fb)

            if not content_feedbacks:
                return {
                    "ok": False,
                    "error": "未找到相关内容反馈数据",
                    "suggestions": [],
                }

            # 聚合统计
            total_count = sum(f.get("total_count", 0) for f in content_feedbacks)
            positive_count = sum(f.get("positive_count", 0) for f in content_feedbacks)
            negative_count = sum(f.get("negative_count", 0) for f in content_feedbacks)
            neutral_count = sum(f.get("neutral_count", 0) for f in content_feedbacks)

            # 聚合关键词
            keyword_freq: Dict[str, int] = {}
            all_needs: List[str] = []
            for f in content_feedbacks:
                for kw in f.get("top_keywords", []):
                    keyword_freq[kw] = keyword_freq.get(kw, 0) + 1
                all_needs.extend(f.get("needs", []))

            sorted_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
            top_keywords = [k for k, _ in sorted_keywords[:10]]
            unique_needs = list(dict.fromkeys(all_needs))[:10]

            # 情感分布
            sentiment_distribution = {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": neutral_count,
                "positive_rate": round(positive_count / total_count * 100, 1) if total_count > 0 else 0,
                "negative_rate": round(negative_count / total_count * 100, 1) if total_count > 0 else 0,
            }

            # 生成优化建议
            suggestions = self._generate_content_suggestions(
                sentiment_distribution=sentiment_distribution,
                top_keywords=top_keywords,
                user_needs=unique_needs,
            )

            return {
                "ok": True,
                "keyword": keyword or "all",
                "total_feedback_items": total_count,
                "data_points": len(content_feedbacks),
                "sentiment_distribution": sentiment_distribution,
                "top_keywords": top_keywords,
                "user_needs": unique_needs,
                "suggestions": suggestions,
                "data_source": "pulse_echo",
            }

        except Exception as e:
            logger.warning("分析内容反馈失败: %s", e)
            return {
                "ok": False,
                "error": f"分析失败: {e}",
                "suggestions": [],
            }

    def _generate_content_suggestions(
        self,
        sentiment_distribution: Dict[str, Any],
        top_keywords: List[str],
        user_needs: List[str],
    ) -> List[Dict[str, Any]]:
        """基于内容反馈数据生成优化建议。"""
        suggestions = []
        pos_rate = sentiment_distribution.get("positive_rate", 0)
        neg_rate = sentiment_distribution.get("negative_rate", 0)

        # 情感相关建议
        if neg_rate > 30:
            suggestions.append({
                "type": "sentiment",
                "priority": "high",
                "title": "负面反馈偏高，建议关注",
                "description": f"负面反馈占比 {neg_rate}%，高于 30% 阈值，建议排查用户不满的主要原因",
                "action": "深入分析负面评论关键词，定位核心痛点",
            })
        elif pos_rate > 70:
            suggestions.append({
                "type": "sentiment",
                "priority": "low",
                "title": "口碑良好，保持当前方向",
                "description": f"正面反馈占比 {pos_rate}%，用户满意度较高",
                "action": "继续保持当前内容策略，可尝试放大成功要素",
            })

        # 关键词相关建议
        if top_keywords:
            suggestions.append({
                "type": "content",
                "priority": "medium",
                "title": "热点关键词洞察",
                "description": f"用户讨论最多的关键词: {', '.join(top_keywords[:5])}",
                "action": "围绕高频关键词创作更多相关内容，强化用户心智",
            })

        # 需求相关建议
        if user_needs:
            suggestions.append({
                "type": "product",
                "priority": "high",
                "title": "用户需求挖掘",
                "description": f"用户提到的潜在需求: {', '.join(user_needs[:5])}",
                "action": "评估这些需求的可行性，优先满足高频需求",
            })

        # 数据不足建议
        if sentiment_distribution.get("positive", 0) + sentiment_distribution.get("negative", 0) < 10:
            suggestions.append({
                "type": "data",
                "priority": "low",
                "title": "反馈数据量不足",
                "description": "当前样本量较小，建议持续采集更多反馈数据",
                "action": "扩大采集范围，增加数据源，提高分析的可信度",
            })

        return suggestions

    # ── 内容飞轮闭环：内容优化提案 ──

    def generate_content_proposals(self, keyword: str = "") -> List[OptimizationProposal]:
        """从内容反馈数据生成内容优化提案（内容飞轮闭环）。

        分析 Echo 采集的全网反馈，生成可执行的内容策略调整提案。
        低风险提案可以自动应用，高风险需要内容总监确认。

        Args:
            keyword: 内容关键词（为空分析所有）

        Returns:
            OptimizationProposal 列表
        """
        import uuid
        proposals: List[OptimizationProposal] = []
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        analysis = self.analyze_content_feedback(keyword)
        if not analysis.get("ok"):
            return proposals

        sentiment = analysis.get("sentiment_distribution", {})
        top_kw = analysis.get("top_keywords", [])
        needs = analysis.get("user_needs", [])
        data_points = analysis.get("data_points", 0)

        # 数据量不够就不生成提案
        if data_points < 3:
            return proposals

        neg_rate = sentiment.get("negative_rate", 0)

        # 提案 1：负面反馈高 → 调整内容方向（低风险：增加正面关键词权重）
        if neg_rate > 20 and top_kw:
            positive_kws = [k for k in top_kw[:5] if k not in ("问题", "不好", "差", "慢", "贵")]
            if positive_kws:
                prop = OptimizationProposal(
                    id=uuid.uuid4().hex[:8],
                    workflow_id=f"content:{keyword}",
                    proposal_type="content_keyword_adjust",
                    title=f"调整关键词权重，强化「{positive_kws[0]}」等正面话题",
                    description=f"当前负面反馈占比 {neg_rate}%，建议增加正面关键词的内容比重",
                    risk_level="low",
                    expected_benefit="预计正面反馈提升 5-10%",
                    auto_applicable=True,
                    change={
                        "action": "adjust_keywords",
                        "add_keywords": positive_kws[:3],
                        "reduce_topics": ["负面相关话题"],
                        "target_keyword": keyword,
                    },
                    created_at=now,
                    source="content_feedback",
                )
                proposals.append(prop)

        # 提案 2：用户需求 → 新内容选题（中风险：需要编辑判断）
        if needs:
            prop = OptimizationProposal(
                id=uuid.uuid4().hex[:8],
                workflow_id=f"content:{keyword}",
                proposal_type="content_topic_suggestion",
                title=f"新内容选题建议：{needs[0]}",
                description=f"用户提到的潜在需求有 {len(needs)} 个，建议围绕 Top 需求创作新内容",
                risk_level="medium",
                expected_benefit="预计用户需求匹配度提升 15-25%",
                auto_applicable=False,
                change={
                    "action": "suggest_topics",
                    "topics": needs[:5],
                    "target_keyword": keyword,
                },
                created_at=now,
                source="content_feedback",
            )
            proposals.append(prop)

        # 按风险等级排序
        risk_order = {"low": 0, "medium": 1, "high": 2}
        proposals.sort(key=lambda p: risk_order.get(p.risk_level, 3))

        # 持久化
        self._save_proposal(f"content_{keyword}", proposals)

        return proposals

    def auto_apply_content_proposals(self, keyword: str,
                                    strategy_store=None) -> List[Dict[str, Any]]:
        """自动应用内容侧低风险的优化提案到内容策略存储（内容飞轮闭环 writeback）。

        这是「双飞轮互相增强」内容侧的自动反哺落地点：
        Echo 反馈 → Pulse → generate_content_proposals（读 Pulse 内容数据）
        → 低风险提案（content_keyword_adjust / content_topic_suggestion）
        → 写回 ContentStrategyStore → 内容生成阶段读取策略偏好。

        中高风险提案不在此自动应用，进入 /api/approvals 人工审批队列。

        Returns:
            已应用的提案摘要列表
        """
        proposals = self.generate_content_proposals(keyword)
        if strategy_store is None:
            try:
                from kernel.plugins.content_strategy import get_content_strategy
                strategy_store = get_content_strategy()
            except Exception as e:  # noqa: BLE001
                logger.debug("内容策略存储不可用: %s", e)
                strategy_store = None

        applied: List[Dict[str, Any]] = []
        for p in proposals:
            if not p.auto_applicable or p.risk_level != "low":
                continue
            change = p.change
            action = change.get("action", "")
            result = None
            if action == "adjust_keywords" and strategy_store is not None:
                result = strategy_store.adjust_keywords(
                    keyword,
                    change.get("add_keywords", []),
                    change.get("reduce_topics", []),
                )
            elif action == "suggest_topics" and strategy_store is not None:
                result = strategy_store.suggest_topics(keyword, change.get("topics", []))
            else:
                continue
            p.applied = True
            p.applied_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._update_proposal(p)
            applied.append({
                "proposal_id": p.id,
                "proposal_type": p.proposal_type,
                "action": action,
                "result": result,
            })
        return applied

    # ── 双飞轮互驱桥接 ──

    def cross_flywheel_bridge(self, *, direction: str = "both",
                              workflow_store=None, hub_store=None) -> Dict[str, Any]:
        """双飞轮互驱桥接——产品飞轮 ⇄ 内容飞轮互相增强。

        两个方向：
        1. content→product（内容驱动产品）：内容热点 → 自动生成工作流模板，发布到 Hub
        2. product→content（产品驱动内容）：高表现工作流 → 自动生成内容选题，给内容飞轮

        Args:
            direction: content_to_product / product_to_content / both
            workflow_store: WorkflowStore 实例
            hub_store: HubStore 实例

        Returns:
            {content_to_product: [...], product_to_content: [...]}
        """
        results = {
            "content_to_product": [],
            "product_to_content": [],
        }

        if workflow_store is None:
            try:
                from kernel.studio.workflow_store import get_workflow_store
                workflow_store = get_workflow_store()
            except Exception:
                workflow_store = None

        if direction in ("content_to_product", "both"):
            results["content_to_product"] = self._content_to_product(workflow_store, hub_store)

        if direction in ("product_to_content", "both"):
            results["product_to_content"] = self._product_to_content()

        return results

    def _content_to_product(self, workflow_store, hub_store) -> List[Dict[str, Any]]:
        """内容 → 产品：从内容热点自动生成工作流模板。

        逻辑：
        1. 从 Pulse 读最近的内容反馈数据
        2. 提取高频关键词和用户需求
        3. 自动生成对应的工作流模板（如果不存在的话）
        4. 发布到 Hub

        这是双飞轮互驱的核心：内容火什么，产品就做什么工具。
        """
        results = []
        if not self._pulse or workflow_store is None:
            return results

        try:
            # 从 Pulse 读内容反馈
            feedbacks = self._pulse.get_feedbacks(
                feedback_type="content_feedback",
                limit=20,
            )
            if not feedbacks:
                return results

            # 聚合所有关键词
            kw_freq: Dict[str, int] = {}
            all_needs: List[str] = []
            for fb in feedbacks:
                fb_data = fb.get("feedback", {})
                for kw in fb_data.get("top_keywords", []):
                    kw_freq[kw] = kw_freq.get(kw, 0) + 1
                all_needs.extend(fb_data.get("needs", []))

            sorted_kws = sorted(kw_freq.items(), key=lambda x: x[1], reverse=True)
            top_keywords = [k for k, _ in sorted_kws[:3]]
            unique_needs = list(dict.fromkeys(all_needs))[:3]

            if not top_keywords and not unique_needs:
                return results

            # 检查工作流是否已存在（避免重复创建）
            existing = workflow_store.list(limit=50)
            existing_names = {wf.get("name", "") for wf in existing}

            # 生成 1-3 个工作流模板
            templates_to_create = []
            for kw in top_keywords[:2]:
                wf_name = f"{kw}调研助手"
                if wf_name not in existing_names:
                    templates_to_create.append({
                        "name": wf_name,
                        "description": f"自动生成：围绕「{kw}」的全网调研与分析工作流",
                        "category": "research",
                        "tags": [kw, "自动生成", "内容驱动"],
                        "steps": [
                            {"capability": "web.search", "name": "全网搜索", "prompt": f"最新 {kw} 相关动态"},
                            {"capability": "content.marketing", "name": "内容分析", "prompt": "分析热点趋势"},
                        ],
                    })

            # 创建工作流模板
            for tmpl in templates_to_create:
                try:
                    from kernel.studio.workflow_models import Workflow
                    wf = Workflow.create(
                        name=tmpl["name"],
                        description=tmpl["description"],
                        author="auto-evolve",
                    )
                    wf.category = tmpl["category"]
                    wf.tags = tmpl["tags"]
                    wf.is_template = True

                    for step_data in tmpl["steps"]:
                        wf.add_step(**step_data)

                    workflow_store.save(wf)

                    # 发布到 Hub（如果有 hub_store）
                    if hub_store is not None:
                        try:
                            hub_store.publish(wf.id)
                        except Exception:
                            pass

                    results.append({
                        "ok": True,
                        "workflow_id": wf.id,
                        "name": wf.name,
                        "source": "content_to_product",
                        "reason": f"内容热点驱动: {top_keywords[0]}",
                    })
                except Exception as e:
                    results.append({"ok": False, "error": str(e), "name": tmpl["name"]})

            return results

        except Exception as e:
            logger.warning("内容→产品 互驱失败: %s", e)
            return results

    def _product_to_content(self) -> List[Dict[str, Any]]:
        """产品 → 内容：从高表现工作流自动生成内容选题。

        逻辑：
        1. 从 Pulse 读最近的工作流运行数据
        2. 找成功率高、使用频繁的工作流
        3. 自动生成对应的内容选题建议（给内容飞轮）

        这是双飞轮互驱的另一半：产品里什么工具火，内容就写什么选题。
        """
        results = []
        if not self._pulse:
            return results

        try:
            # 从 Pulse 读所有 agent metrics
            all_metrics = self._pulse.get_all_metrics(limit=50)
            if not all_metrics:
                return results

            # 找表现最好的工作流
            top_workflows = []
            for item in all_metrics[:20]:
                if not isinstance(item, dict):
                    continue
                wf_id = item.get("workflow_id", "")
                total = item.get("total_runs", 0)
                sr = item.get("success_rate", 0) / 100.0  # 百分比转小数
                if total >= 3 and sr >= 0.7:
                    top_workflows.append((wf_id, total, sr))

            # 按使用量排序
            top_workflows.sort(key=lambda x: x[1], reverse=True)

            if not top_workflows:
                return results

            # 生成内容选题建议
            for wf_id, total, sr in top_workflows[:3]:
                topic = f"如何用 {wf_id} 提高效率"
                results.append({
                    "ok": True,
                    "workflow_id": wf_id,
                    "topic": topic,
                    "total_runs": total,
                    "success_rate": sr,
                    "suggested_angle": f"实操教程：用 AOS 的 {wf_id} 工作流自动化你的工作",
                    "source": "product_to_content",
                })

            return results

        except Exception as e:
            logger.warning("产品→内容 互驱失败: %s", e)
            return results

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
