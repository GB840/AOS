from __future__ import annotations

"""创业调度引擎（总入口）。

整合目标拆解 + 任务调度 + OPC岗位协作，提供创业全流程管理能力。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict

from .goal_decomposer import (
    GoalDecomposer,
    GoalDecompositionResult,
    TaskStatus,
    OPCRole,
    DailyWorkItem,
    Project,
    Milestone,
    WeeklyTask,
)
from .task_scheduler import TaskScheduler

logger = logging.getLogger(__name__)


@dataclass
class TenantState:
    """租户状态。"""

    tenant_id: str
    goal_result: Optional[GoalDecompositionResult] = None
    scheduler: TaskScheduler = field(default_factory=TaskScheduler)
    daily_logs: List[Dict[str, Any]] = field(default_factory=list)
    review_records: List[Dict[str, Any]] = field(default_factory=list)
    strategy_adjustments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_run_date: Optional[datetime] = None


class StartupEngine:
    """创业调度引擎。

    整合目标拆解、任务调度、OPC岗位协作，提供创业全流程管理。

    工作流程：
    1. 接收总目标 → 拆解为项目/里程碑/周任务/日工单
    2. 每日调度：分配当日工单给对应岗位智能体
    3. 执行：各智能体通过 FabricHub 调用能力完成任务
    4. 监控：进度跟踪、异常告警、自动重分配
    5. 复盘：每周/每月自动复盘，优化策略
    """

    def __init__(self) -> None:
        """初始化创业调度引擎。"""
        logger.info("初始化创业调度引擎")
        self._decomposer = GoalDecomposer()
        self._tenants: Dict[str, TenantState] = {}

    def set_goal(self, tenant_id: str, goal: str, industry: str = "general") -> Dict[str, Any]:
        """设定创业目标。

        Args:
            tenant_id: 租户ID
            goal: 创业目标描述
            industry: 行业类型

        Returns:
            目标设定结果
        """
        logger.info(f"为租户 {tenant_id} 设定创业目标: {goal[:50]}...")

        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantState(tenant_id=tenant_id)

        tenant_state = self._tenants[tenant_id]

        goal_result = self._decomposer.decompose(goal, industry)
        tenant_state.goal_result = goal_result

        scheduled_items = tenant_state.scheduler.schedule_work_items(
            tenant_id, goal_result.daily_work_items
        )

        result = {
            "tenant_id": tenant_id,
            "goal": goal_result.goal.to_dict(),
            "summary": {
                "project_count": len(goal_result.projects),
                "milestone_count": len(goal_result.milestones),
                "weekly_task_count": len(goal_result.weekly_tasks),
                "daily_work_item_count": len(goal_result.daily_work_items),
                "scheduled_item_count": len(scheduled_items),
            },
            "projects": [p.to_dict() for p in goal_result.projects],
            "set_at": datetime.now().isoformat(),
        }

        logger.info(
            f"租户 {tenant_id} 目标设定完成: "
            f"{len(goal_result.projects)}个项目, "
            f"{len(goal_result.daily_work_items)}个日工单"
        )
        return result

    def run_daily(self, tenant_id: str) -> Dict[str, Any]:
        """每日运行：执行当日工单、更新进度、生成复盘。

        Args:
            tenant_id: 租户ID

        Returns:
            每日运行结果
        """
        logger.info(f"执行租户 {tenant_id} 的每日运行")

        if tenant_id not in self._tenants:
            logger.warning(f"租户 {tenant_id} 不存在")
            return {"error": f"租户 {tenant_id} 不存在，请先设定目标"}

        tenant_state = self._tenants[tenant_id]

        if tenant_state.goal_result is None:
            logger.warning(f"租户 {tenant_id} 未设定目标")
            return {"error": "未设定创业目标，请先调用 set_goal"}

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        overdue_count = tenant_state.scheduler.reassign_overdue(tenant_id)

        daily_queue = tenant_state.scheduler.get_daily_queue(tenant_id, today)

        completed_today = 0
        failed_today = 0
        in_progress_today = 0
        results: List[Dict[str, Any]] = []

        for item in daily_queue:
            if item.status == TaskStatus.PENDING.value:
                tenant_state.scheduler.update_status(
                    item.item_id, TaskStatus.IN_PROGRESS.value
                )
                in_progress_today += 1
            elif item.status == TaskStatus.IN_PROGRESS.value:
                in_progress_today += 1

            execution_result = self._execute_work_item(tenant_id, item)
            results.append(execution_result)

            if execution_result["status"] == "completed":
                tenant_state.scheduler.update_status(
                    item.item_id,
                    TaskStatus.COMPLETED.value,
                    result=execution_result.get("output"),
                )
                completed_today += 1
            elif execution_result["status"] == "failed":
                tenant_state.scheduler.update_status(
                    item.item_id,
                    TaskStatus.FAILED.value,
                    result=execution_result.get("error"),
                )
                failed_today += 1

        progress = tenant_state.scheduler.get_progress(tenant_id)

        daily_log = {
            "date": today.isoformat(),
            "total_items": len(daily_queue),
            "completed_count": completed_today,
            "failed_count": failed_today,
            "in_progress_count": in_progress_today,
            "overdue_reassigned": overdue_count,
            "progress": progress,
            "results": results,
        }

        tenant_state.daily_logs.append(daily_log)
        tenant_state.last_run_date = today

        logger.info(
            f"租户 {tenant_id} 每日运行完成: "
            f"完成 {completed_today} 个, 失败 {failed_today} 个, "
            f"进行中 {in_progress_today} 个, 重分配逾期 {overdue_count} 个"
        )
        return daily_log

    def _execute_work_item(self, tenant_id: str, item: DailyWorkItem) -> Dict[str, Any]:
        """执行单个工单——经 FabricHub 真实路由调用对应岗位能力。"""
        logger.debug(f"执行工单 {item.item_id}: {item.title}")
        from api.startup_api import snapshot_output_dirs, scan_new_artifacts
        before = snapshot_output_dirs()

        role = item.assigned_role
        # 岗位→能力映射：每个岗位调用最匹配的FabricHub能力
        capability_map = {
            "product_rd": "action.code_exec",
            "market_research": "web.search",
            "content_marketing": "media.video",
            "customer_service": "inference.llm",
            "finance": "finance.report",
        }
        capability = capability_map.get(role, "inference.llm")

        # 构造任务payload
        payload = {
            "task": item.title,
            "description": item.description,
            "role": role,
            "context": {
                "tenant_id": tenant_id,
                "item_id": item.item_id,
                "deliverables": item.deliverables if hasattr(item, 'deliverables') else [],
            },
        }

        # 尝试通过 FabricHub 真实路由
        try:
            from kernel.plugins.fabric_hub import get_fabric_hub
            hub = get_fabric_hub()
            if hub is not None:
                result = hub.route(capability, payload)
                if hasattr(result, 'ok') and result.ok:
                    output = result.data
                    if isinstance(output, dict):
                        output = output.get("content") or output.get("text") or output.get("summary") or str(output)
                    artifacts = scan_new_artifacts(before)
                    engine_id = getattr(result, "engine_id", None)
                    result = {
                        "item_id": item.item_id,
                        "title": item.title,
                        "status": "completed",
                        "role": role,
                        "capability": capability,
                        "engine": engine_id,
                        "output": str(output)[:500] if output else f"已完成: {item.title}",
                        "artifacts": artifacts,
                    }
                    return result
                else:
                    error_msg = getattr(result, "error", "未知错误")
                    return {
                        "item_id": item.item_id,
                        "title": item.title,
                        "status": "failed",
                        "role": role,
                        "capability": capability,
                        "error": f"FabricHub路由失败: {error_msg}",
                    }
        except Exception as e:
            logger.warning(f"FabricHub不可用，降级到本地执行: {e}")

        # 降级：FabricHub不可用时使用本地LLM生成
        try:
            from kernel.plugins.zhipu_chat import zhipu_chat
            prompt = f"你是{role}岗位的AI助手。请完成以下任务：{item.title}\n\n任务描述：{item.description}" if hasattr(item, 'description') else f"你是{role}岗位的AI助手。请完成以下任务：{item.title}"
            messages = [{"role": "user", "content": prompt}]
            response = zhipu_chat(messages, max_tokens=512)
            if response:
                artifacts = scan_new_artifacts(before)
                result = {
                    "item_id": item.item_id,
                    "title": item.title,
                    "status": "completed",
                    "role": role,
                    "capability": capability,
                    "engine": "zhipu-local",
                    "output": str(response)[:500],
                    "artifacts": artifacts,
                }
                return result
        except Exception as e:
            logger.warning(f"本地LLM降级也失败: {e}")

        # 最终降级：返回明确的失败信息
        return {
            "item_id": item.item_id,
            "title": item.title,
            "status": "failed",
            "role": role,
            "capability": capability,
            "error": f"执行失败: 无可用引擎（FabricHub和本地LLM均不可用）",
        }

    def get_status(self, tenant_id: str) -> Dict[str, Any]:
        """获取当前创业状态总览。

        Args:
            tenant_id: 租户ID

        Returns:
            创业状态总览
        """
        logger.info(f"获取租户 {tenant_id} 的创业状态")

        if tenant_id not in self._tenants:
            logger.warning(f"租户 {tenant_id} 不存在")
            return {"error": f"租户 {tenant_id} 不存在"}

        tenant_state = self._tenants[tenant_id]

        if tenant_state.goal_result is None:
            return {
                "tenant_id": tenant_id,
                "has_goal": False,
                "message": "尚未设定创业目标",
            }

        goal_result = tenant_state.goal_result
        progress = tenant_state.scheduler.get_progress(tenant_id)

        project_statuses = []
        for project in goal_result.projects:
            project_milestones = [
                m for m in goal_result.milestones if m.project_id == project.project_id
            ]
            completed_milestones = sum(
                1 for m in project_milestones if m.status == TaskStatus.COMPLETED.value
            )
            project_statuses.append({
                "project_id": project.project_id,
                "name": project.name,
                "status": project.status,
                "milestone_count": len(project_milestones),
                "completed_milestones": completed_milestones,
                "start_date": project.start_date.isoformat(),
                "end_date": project.end_date.isoformat(),
            })

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_queue = tenant_state.scheduler.get_daily_queue(tenant_id, today)

        role_workload = defaultdict(int)
        for item in today_queue:
            role_workload[item.assigned_role] += 1

        status = {
            "tenant_id": tenant_id,
            "has_goal": True,
            "goal": goal_result.goal.to_dict(),
            "progress": progress,
            "projects": project_statuses,
            "today_summary": {
                "date": today.isoformat(),
                "total_tasks": len(today_queue),
                "role_workload": dict(role_workload),
                "pending_count": sum(
                    1 for i in today_queue if i.status == TaskStatus.PENDING.value
                ),
                "in_progress_count": sum(
                    1 for i in today_queue if i.status == TaskStatus.IN_PROGRESS.value
                ),
                "completed_count": sum(
                    1 for i in today_queue if i.status == TaskStatus.COMPLETED.value
                ),
            },
            "last_run_date": tenant_state.last_run_date.isoformat()
            if tenant_state.last_run_date
            else None,
            "daily_log_count": len(tenant_state.daily_logs),
            "review_count": len(tenant_state.review_records),
            "adjustment_count": len(tenant_state.strategy_adjustments),
        }

        logger.info(f"租户 {tenant_id} 状态获取完成，完成率: {progress['completion_rate']}%")
        return status

    def review_iteration(self, tenant_id: str, iteration: str = "weekly") -> Dict[str, Any]:
        """迭代复盘。

        Args:
            tenant_id: 租户ID
            iteration: 迭代类型 (weekly/monthly)

        Returns:
            复盘结果
        """
        logger.info(f"执行租户 {tenant_id} 的{iteration}复盘")

        if tenant_id not in self._tenants:
            logger.warning(f"租户 {tenant_id} 不存在")
            return {"error": f"租户 {tenant_id} 不存在"}

        tenant_state = self._tenants[tenant_id]

        if tenant_state.goal_result is None:
            return {"error": "未设定创业目标"}

        progress = tenant_state.scheduler.get_progress(tenant_id)

        now = datetime.now()
        if iteration == "weekly":
            start_date = now - timedelta(days=7)
        elif iteration == "monthly":
            start_date = now - timedelta(days=30)
        else:
            start_date = now - timedelta(days=7)
            iteration = "weekly"

        period_logs = [
            log for log in tenant_state.daily_logs
            if datetime.fromisoformat(log["date"]) >= start_date
        ]

        total_completed = sum(log["completed_count"] for log in period_logs)
        total_failed = sum(log["failed_count"] for log in period_logs)
        total_items = sum(log["total_items"] for log in period_logs)

        completion_rate = (total_completed / total_items * 100) if total_items > 0 else 0
        success_rate = (total_completed / (total_completed + total_failed) * 100) if (
            total_completed + total_failed
        ) > 0 else 0

        strengths = self._analyze_strengths(progress, period_logs)
        weaknesses = self._analyze_weaknesses(progress, period_logs)
        opportunities = self._analyze_opportunities(tenant_state)
        action_items = self._generate_action_items(weaknesses, opportunities)

        review_result = {
            "tenant_id": tenant_id,
            "iteration": iteration,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
            },
            "summary": {
                "total_items": total_items,
                "completed_count": total_completed,
                "failed_count": total_failed,
                "completion_rate": round(completion_rate, 2),
                "success_rate": round(success_rate, 2),
            },
            "overall_progress": progress,
            "analysis": {
                "strengths": strengths,
                "weaknesses": weaknesses,
                "opportunities": opportunities,
            },
            "action_items": action_items,
            "reviewed_at": now.isoformat(),
        }

        tenant_state.review_records.append(review_result)

        logger.info(
            f"{iteration}复盘完成: 完成率 {completion_rate:.1f}%, "
            f"成功率 {success_rate:.1f}%, "
            f"{len(action_items)} 个行动计划"
        )
        return review_result

    def _analyze_strengths(
        self, progress: Dict[str, Any], period_logs: List[Dict[str, Any]]
    ) -> List[str]:
        """分析优势。

        Args:
            progress: 进度数据
            period_logs: 周期内日志

        Returns:
            优势列表
        """
        strengths: List[str] = []

        if progress["completion_rate"] >= 70:
            strengths.append("整体项目推进顺利，任务完成率较高")

        if progress["hours_completion_rate"] >= progress["completion_rate"]:
            strengths.append("高价值任务优先完成，工时利用率良好")

        if progress["overdue_count"] == 0:
            strengths.append("无逾期任务，时间管理能力优秀")

        if len(period_logs) >= 5:
            daily_completion = [
                log["completed_count"] / max(log["total_items"], 1) for log in period_logs
            ]
            if all(rate >= 0.6 for rate in daily_completion):
                strengths.append("每日任务交付稳定，执行力强")

        if not strengths:
            strengths.append("项目正在稳步推进中")

        return strengths

    def _analyze_weaknesses(
        self, progress: Dict[str, Any], period_logs: List[Dict[str, Any]]
    ) -> List[str]:
        """分析劣势。

        Args:
            progress: 进度数据
            period_logs: 周期内日志

        Returns:
            劣势列表
        """
        weaknesses: List[str] = []

        if progress["completion_rate"] < 50:
            weaknesses.append("整体进度偏慢，需要加快执行节奏")

        if progress["failed_items"] > 0 if "failed_items" in progress else progress.get(
            "failed_items", 0
        ) > 0:
            failed_count = progress.get("failed_items", 0)
            if failed_count > 3:
                weaknesses.append("失败任务较多，需要排查根因并优化流程")

        if progress["overdue_count"] > 0:
            weaknesses.append(f"存在 {progress['overdue_count']} 个逾期任务，需要加强时间管理")

        total_failed = sum(log["failed_count"] for log in period_logs)
        if total_failed > 5:
            weaknesses.append("本周期失败任务较多，需要关注执行质量")

        if not weaknesses:
            weaknesses.append("暂未发现明显劣势，继续保持")

        return weaknesses

    def _analyze_opportunities(self, tenant_state: TenantState) -> List[str]:
        """分析机会点。

        Args:
            tenant_state: 租户状态

        Returns:
            机会点列表
        """
        opportunities: List[str] = []

        if tenant_state.goal_result:
            pending_projects = [
                p for p in tenant_state.goal_result.projects
                if p.status == TaskStatus.PENDING.value
            ]
            if pending_projects:
                opportunities.append(
                    f"有 {len(pending_projects)} 个待启动项目，可以提前规划资源"
                )

        if len(tenant_state.review_records) >= 2:
            opportunities.append("已积累多轮复盘经验，可以沉淀方法论")

        if not opportunities:
            opportunities.append("继续按计划推进，关注市场变化")

        return opportunities

    def _generate_action_items(
        self, weaknesses: List[str], opportunities: List[str]
    ) -> List[Dict[str, Any]]:
        """生成行动计划。

        Args:
            weaknesses: 劣势列表
            opportunities: 机会点列表

        Returns:
            行动计划列表
        """
        action_items: List[Dict[str, Any]] = []

        if any("进度偏慢" in w for w in weaknesses):
            action_items.append({
                "priority": "high",
                "action": "加快执行节奏",
                "description": "增加每日任务量，设置更严格的deadline",
                "responsible_role": OPCRole.PRODUCT_RD.value,
            })

        if any("逾期任务" in w for w in weaknesses):
            action_items.append({
                "priority": "high",
                "action": "清理逾期任务",
                "description": "优先处理逾期任务，重新评估时间预估",
                "responsible_role": OPCRole.PRODUCT_RD.value,
            })

        if any("失败任务较多" in w for w in weaknesses):
            action_items.append({
                "priority": "medium",
                "action": "优化执行流程",
                "description": "分析失败原因，改进方法和工具",
                "responsible_role": OPCRole.MARKET_RESEARCH.value,
            })

        if any("待启动项目" in o for o in opportunities):
            action_items.append({
                "priority": "medium",
                "action": "提前规划后续项目",
                "description": "为待启动项目做预研和资源准备",
                "responsible_role": OPCRole.MARKET_RESEARCH.value,
            })

        if not action_items:
            action_items.append({
                "priority": "low",
                "action": "保持现有节奏",
                "description": "继续按计划推进，定期监控进度",
                "responsible_role": OPCRole.PRODUCT_RD.value,
            })

        return action_items

    def adjust_strategy(self, tenant_id: str, feedback: str) -> Dict[str, Any]:
        """根据反馈调整策略。

        Args:
            tenant_id: 租户ID
            feedback: 反馈内容

        Returns:
            调整结果
        """
        logger.info(f"根据反馈调整租户 {tenant_id} 的策略: {feedback[:50]}...")

        if tenant_id not in self._tenants:
            logger.warning(f"租户 {tenant_id} 不存在")
            return {"error": f"租户 {tenant_id} 不存在"}

        tenant_state = self._tenants[tenant_id]

        if tenant_state.goal_result is None:
            return {"error": "未设定创业目标"}

        adjustments = self._analyze_feedback(feedback, tenant_state)

        adjustment_record = {
            "tenant_id": tenant_id,
            "feedback": feedback,
            "adjustments": adjustments,
            "adjusted_at": datetime.now().isoformat(),
        }

        tenant_state.strategy_adjustments.append(adjustment_record)

        logger.info(f"策略调整完成，共 {len(adjustments)} 项调整")
        return adjustment_record

    def _analyze_feedback(
        self, feedback: str, tenant_state: TenantState
    ) -> List[Dict[str, Any]]:
        """分析反馈并生成调整建议。

        Args:
            feedback: 反馈内容
            tenant_state: 租户状态

        Returns:
            调整建议列表
        """
        adjustments: List[Dict[str, Any]] = []
        feedback_lower = feedback.lower()

        if "加快" in feedback or "加速" in feedback or "faster" in feedback_lower:
            adjustments.append({
                "type": "schedule",
                "action": "加快进度",
                "description": "压缩任务周期，增加并行任务数量",
                "impact": "medium",
            })

        if "放缓" in feedback or "慢一点" in feedback or "slow" in feedback_lower:
            adjustments.append({
                "type": "schedule",
                "action": "放缓进度",
                "description": "延长任务周期，确保质量优先",
                "impact": "medium",
            })

        if "质量" in feedback or "quality" in feedback_lower:
            adjustments.append({
                "type": "process",
                "action": "提升质量",
                "description": "增加测试环节，加强质量检查",
                "impact": "high",
            })

        if "成本" in feedback or "预算" in feedback or "cost" in feedback_lower:
            adjustments.append({
                "type": "finance",
                "action": "控制成本",
                "description": "优化资源配置，优先高ROI任务",
                "impact": "high",
            })

        if "方向" in feedback or "转型" in feedback or "pivot" in feedback_lower:
            adjustments.append({
                "type": "strategy",
                "action": "调整方向",
                "description": "重新评估目标，调整产品/市场方向",
                "impact": "high",
            })

        if "用户" in feedback or "客户" in feedback or "customer" in feedback_lower:
            adjustments.append({
                "type": "focus",
                "action": "关注用户",
                "description": "加强用户研究，提升用户体验",
                "impact": "medium",
            })

        if not adjustments:
            adjustments.append({
                "type": "general",
                "action": "持续优化",
                "description": "根据反馈持续改进产品和服务",
                "impact": "low",
            })

        return adjustments

    def get_decomposer(self) -> GoalDecomposer:
        """获取目标拆解器实例。

        Returns:
            目标拆解器
        """
        return self._decomposer

    def get_scheduler(self, tenant_id: str) -> Optional[TaskScheduler]:
        """获取租户的任务调度器。

        Args:
            tenant_id: 租户ID

        Returns:
            任务调度器（如果存在）
        """
        tenant_state = self._tenants.get(tenant_id)
        return tenant_state.scheduler if tenant_state else None
