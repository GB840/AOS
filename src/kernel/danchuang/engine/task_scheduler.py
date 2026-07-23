from __future__ import annotations

"""任务调度器。

负责日工单的排班、状态管理、逾期重分配和进度统计。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

from .goal_decomposer import DailyWorkItem, TaskStatus, OPCRole

logger = logging.getLogger(__name__)


@dataclass
class ScheduleEntry:
    """排班条目。"""

    item_id: str
    scheduled_date: datetime
    tenant_id: str


class TaskScheduler:
    """任务调度器。

    管理日工单的排班、状态流转和进度跟踪。
    """

    def __init__(self) -> None:
        """初始化任务调度器。"""
        logger.info("初始化任务调度器")
        self._work_items: Dict[str, DailyWorkItem] = {}
        self._schedule: Dict[str, List[str]] = defaultdict(list)
        self._tenant_items: Dict[str, List[str]] = defaultdict(list)

    def schedule_work_items(self, tenant_id: str, work_items: List[DailyWorkItem]) -> List[DailyWorkItem]:
        """排班日工单。

        Args:
            tenant_id: 租户ID
            work_items: 待排班的日工单列表

        Returns:
            排班后的日工单列表
        """
        logger.info(f"为租户 {tenant_id} 排班 {len(work_items)} 个日工单")

        scheduled_items: List[DailyWorkItem] = []
        current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        items_by_role: Dict[str, List[DailyWorkItem]] = defaultdict(list)
        for item in work_items:
            items_by_role[item.assigned_role].append(item)

        daily_capacity = {
            OPCRole.PRODUCT_RD.value: 8.0,
            OPCRole.MARKET_RESEARCH.value: 8.0,
            OPCRole.CONTENT_MARKETING.value: 8.0,
            OPCRole.CUSTOMER_SERVICE.value: 8.0,
            OPCRole.FINANCE.value: 4.0,
        }

        role_workload: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        scheduled_count = 0

        for role, items in items_by_role.items():
            date_offset = 0
            for item in items:
                scheduled = False
                max_attempts = 30
                attempts = 0

                while not scheduled and attempts < max_attempts:
                    schedule_date = current_date + timedelta(days=date_offset)
                    date_key = schedule_date.strftime("%Y-%m-%d")
                    current_load = role_workload[role][date_key]
                    capacity = daily_capacity.get(role, 8.0)

                    if current_load + item.estimated_hours <= capacity:
                        item.scheduled_date = schedule_date
                        role_workload[role][date_key] += item.estimated_hours
                        scheduled = True
                        scheduled_count += 1
                    else:
                        date_offset += 1
                        attempts += 1

                if not scheduled:
                    schedule_date = current_date + timedelta(days=date_offset)
                    item.scheduled_date = schedule_date
                    role_workload[role][schedule_date.strftime("%Y-%m-%d")] += item.estimated_hours
                    scheduled_count += 1

                self._work_items[item.item_id] = item
                self._tenant_items[tenant_id].append(item.item_id)
                date_key = item.scheduled_date.strftime("%Y-%m-%d") if item.scheduled_date else ""
                schedule_key = f"{tenant_id}:{date_key}"
                self._schedule[schedule_key].append(item.item_id)
                scheduled_items.append(item)

        logger.info(f"排班完成，共安排 {scheduled_count} 个工单")
        return scheduled_items

    def get_daily_queue(self, tenant_id: str, date: Optional[datetime] = None) -> List[DailyWorkItem]:
        """获取某日待办队列。

        Args:
            tenant_id: 租户ID
            date: 查询日期，默认为今天

        Returns:
            当日待办工单列表
        """
        if date is None:
            date = datetime.now()

        date_key = date.strftime("%Y-%m-%d")
        schedule_key = f"{tenant_id}:{date_key}"

        item_ids = self._schedule.get(schedule_key, [])
        items = [self._work_items[item_id] for item_id in item_ids if item_id in self._work_items]

        items.sort(key=lambda x: (
            0 if x.status == TaskStatus.IN_PROGRESS else 1,
            x.estimated_hours,
        ))

        logger.info(f"获取租户 {tenant_id} 在 {date_key} 的待办队列，共 {len(items)} 个工单")
        return items

    def update_status(self, item_id: str, status: str, result: Optional[str] = None) -> bool:
        """更新任务状态。

        Args:
            item_id: 工单ID
            status: 新状态
            result: 执行结果（可选）

        Returns:
            是否更新成功
        """
        if item_id not in self._work_items:
            logger.warning(f"工单 {item_id} 不存在")
            return False

        item = self._work_items[item_id]
        old_status = item.status

        if not self._validate_status_transition(old_status, status):
            logger.warning(f"非法状态流转: {old_status} -> {status}")
            return False

        item.status = status
        if result is not None:
            item.result = result

        logger.info(f"工单 {item_id} 状态更新: {old_status} -> {status}")
        return True

    def _validate_status_transition(self, old_status: str, new_status: str) -> bool:
        """验证状态流转是否合法。

        状态流转: pending → in_progress → completed / failed → reviewed

        Args:
            old_status: 原状态
            new_status: 新状态

        Returns:
            是否合法
        """
        valid_transitions = {
            TaskStatus.PENDING.value: [TaskStatus.IN_PROGRESS.value],
            TaskStatus.IN_PROGRESS.value: [
                TaskStatus.COMPLETED.value,
                TaskStatus.FAILED.value,
                TaskStatus.PENDING.value,
            ],
            TaskStatus.COMPLETED.value: [TaskStatus.REVIEWED.value],
            TaskStatus.FAILED.value: [TaskStatus.REVIEWED.value, TaskStatus.PENDING.value],
            TaskStatus.REVIEWED.value: [],
        }

        return new_status in valid_transitions.get(old_status, [])

    def reassign_overdue(self, tenant_id: str) -> int:
        """自动重分配逾期任务。

        Args:
            tenant_id: 租户ID

        Returns:
            重分配的任务数量
        """
        logger.info(f"检查租户 {tenant_id} 的逾期任务")

        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        reassigned_count = 0

        item_ids = self._tenant_items.get(tenant_id, [])
        overdue_items: List[DailyWorkItem] = []

        for item_id in item_ids:
            item = self._work_items.get(item_id)
            if item is None:
                continue

            if item.status in [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]:
                if item.scheduled_date and item.scheduled_date < today:
                    overdue_items.append(item)

        if not overdue_items:
            logger.info(f"租户 {tenant_id} 没有逾期任务")
            return 0

        items_by_role: Dict[str, List[DailyWorkItem]] = defaultdict(list)
        for item in overdue_items:
            items_by_role[item.assigned_role].append(item)

        role_backup = {
            OPCRole.PRODUCT_RD.value: OPCRole.PRODUCT_RD.value,
            OPCRole.MARKET_RESEARCH.value: OPCRole.CONTENT_MARKETING.value,
            OPCRole.CONTENT_MARKETING.value: OPCRole.MARKET_RESEARCH.value,
            OPCRole.CUSTOMER_SERVICE.value: OPCRole.CUSTOMER_SERVICE.value,
            OPCRole.FINANCE.value: OPCRole.FINANCE.value,
        }

        for role, items in items_by_role.items():
            backup_role = role_backup.get(role, role)
            for item in items:
                if item.scheduled_date:
                    days_overdue = (today - item.scheduled_date).days
                    if days_overdue >= 3 and backup_role != role:
                        old_role = item.assigned_role
                        item.assigned_role = backup_role
                        item.scheduled_date = today
                        reassigned_count += 1
                        logger.info(
                            f"逾期任务 {item.item_id} 从 {old_role} 重分配到 {backup_role}，"
                            f"逾期 {days_overdue} 天"
                        )
                    else:
                        item.scheduled_date = today
                        reassigned_count += 1

        if reassigned_count > 0:
            self._reschedule_all(tenant_id)

        logger.info(f"共重分配 {reassigned_count} 个逾期任务")
        return reassigned_count

    def _reschedule_all(self, tenant_id: str) -> None:
        """重新排班组下所有任务。

        Args:
            tenant_id: 租户ID
        """
        item_ids = self._tenant_items.get(tenant_id, [])
        items = [self._work_items[item_id] for item_id in item_ids if item_id in self._work_items]

        for key in list(self._schedule.keys()):
            if key.startswith(f"{tenant_id}:"):
                del self._schedule[key]

        for item in items:
            if item.scheduled_date:
                date_key = item.scheduled_date.strftime("%Y-%m-%d")
                schedule_key = f"{tenant_id}:{date_key}"
                self._schedule[schedule_key].append(item.item_id)

    def get_progress(self, tenant_id: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """获取进度统计。

        Args:
            tenant_id: 租户ID
            project_id: 项目ID（可选），不传则统计所有项目

        Returns:
            进度统计字典
        """
        logger.info(f"获取租户 {tenant_id} 的进度统计" + (f"，项目: {project_id}" if project_id else ""))

        item_ids = self._tenant_items.get(tenant_id, [])
        items = [self._work_items[item_id] for item_id in item_ids if item_id in self._work_items]

        status_counts: Dict[str, int] = defaultdict(int)
        total_hours = 0.0
        completed_hours = 0.0

        for item in items:
            status_counts[item.status] += 1
            total_hours += item.estimated_hours
            if item.status in [TaskStatus.COMPLETED.value, TaskStatus.REVIEWED.value]:
                completed_hours += item.estimated_hours

        total_items = len(items)
        completed_items = status_counts.get(TaskStatus.COMPLETED.value, 0) + status_counts.get(
            TaskStatus.REVIEWED.value, 0
        )
        pending_items = status_counts.get(TaskStatus.PENDING.value, 0)
        in_progress_items = status_counts.get(TaskStatus.IN_PROGRESS.value, 0)
        failed_items = status_counts.get(TaskStatus.FAILED.value, 0)
        reviewed_items = status_counts.get(TaskStatus.REVIEWED.value, 0)

        completion_rate = (completed_items / total_items * 100) if total_items > 0 else 0.0
        hours_completion_rate = (completed_hours / total_hours * 100) if total_hours > 0 else 0.0

        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        overdue_count = 0
        for item in items:
            if item.status in [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]:
                if item.scheduled_date and item.scheduled_date < today:
                    overdue_count += 1

        progress = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "total_items": total_items,
            "pending_items": pending_items,
            "in_progress_items": in_progress_items,
            "completed_items": completed_items,
            "failed_items": failed_items,
            "reviewed_items": reviewed_items,
            "overdue_count": overdue_count,
            "completion_rate": round(completion_rate, 2),
            "total_estimated_hours": round(total_hours, 1),
            "completed_hours": round(completed_hours, 1),
            "hours_completion_rate": round(hours_completion_rate, 2),
            "status_breakdown": dict(status_counts),
            "calculated_at": now.isoformat(),
        }

        logger.info(
            f"进度统计: 完成率 {completion_rate:.1f}%, "
            f"总工时 {total_hours:.1f}h, 已完成 {completed_hours:.1f}h, 逾期 {overdue_count} 个"
        )
        return progress

    def get_work_item(self, item_id: str) -> Optional[DailyWorkItem]:
        """获取工单详情。

        Args:
            item_id: 工单ID

        Returns:
            工单对象（如果存在）
        """
        return self._work_items.get(item_id)

    def get_tenant_items(self, tenant_id: str) -> List[DailyWorkItem]:
        """获取租户下所有工单。

        Args:
            tenant_id: 租户ID

        Returns:
            工单列表
        """
        item_ids = self._tenant_items.get(tenant_id, [])
        return [self._work_items[item_id] for item_id in item_ids if item_id in self._work_items]

    def get_role_queue(
        self, tenant_id: str, role: str, date: Optional[datetime] = None
    ) -> List[DailyWorkItem]:
        """获取指定角色的工单队列。

        Args:
            tenant_id: 租户ID
            role: 角色
            date: 查询日期（可选）

        Returns:
            工单列表
        """
        if date:
            items = self.get_daily_queue(tenant_id, date)
        else:
            items = self.get_tenant_items(tenant_id)

        return [item for item in items if item.assigned_role == role]
