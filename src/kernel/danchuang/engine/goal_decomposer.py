from __future__ import annotations

"""目标拆解引擎。

将一句创业目标自动拆解为：长期项目、月度里程碑、周度任务、每日工单。
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class OPCRole(str, Enum):
    """OPC岗位枚举。"""

    PRODUCT_RD = "product_rd"
    MARKET_RESEARCH = "market_research"
    CONTENT_MARKETING = "content_marketing"
    CUSTOMER_SERVICE = "customer_service"
    FINANCE = "finance"


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEWED = "reviewed"


class IndustryType(str, Enum):
    """行业类型枚举。"""

    GENERAL = "general"
    HARDWARE = "hardware"
    ECOMMERCE = "ecommerce"
    CONTENT = "content"
    SERVICE = "service"


@dataclass
class EntrepreneurialGoal:
    """创业总目标。"""

    description: str
    industry: str
    time_horizon: str
    key_metrics: List[str] = field(default_factory=list)
    goal_id: str = field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "industry": self.industry,
            "time_horizon": self.time_horizon,
            "key_metrics": self.key_metrics,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Project:
    """项目级目标。"""

    name: str
    description: str
    start_date: datetime
    end_date: datetime
    status: str = TaskStatus.PENDING
    assigned_role: str = OPCRole.PRODUCT_RD
    project_id: str = field(default_factory=lambda: f"proj_{uuid.uuid4().hex[:8]}")
    goal_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "project_id": self.project_id,
            "goal_id": self.goal_id,
            "name": self.name,
            "description": self.description,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "status": self.status,
            "assigned_role": self.assigned_role,
        }


@dataclass
class Milestone:
    """里程碑级目标。"""

    project_id: str
    title: str
    deadline: datetime
    deliverables: List[str] = field(default_factory=list)
    status: str = TaskStatus.PENDING
    milestone_id: str = field(default_factory=lambda: f"mile_{uuid.uuid4().hex[:8]}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "milestone_id": self.milestone_id,
            "project_id": self.project_id,
            "title": self.title,
            "deadline": self.deadline.isoformat(),
            "deliverables": self.deliverables,
            "status": self.status,
        }


@dataclass
class WeeklyTask:
    """周度任务。"""

    milestone_id: str
    title: str
    description: str
    priority: int = 3
    assigned_role: str = OPCRole.PRODUCT_RD
    status: str = TaskStatus.PENDING
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    week_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "task_id": self.task_id,
            "milestone_id": self.milestone_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "assigned_role": self.assigned_role,
            "status": self.status,
            "week_number": self.week_number,
        }


@dataclass
class DailyWorkItem:
    """每日工单。"""

    task_id: str
    title: str
    description: str
    estimated_hours: float = 2.0
    assigned_role: str = OPCRole.PRODUCT_RD
    status: str = TaskStatus.PENDING
    item_id: str = field(default_factory=lambda: f"item_{uuid.uuid4().hex[:8]}")
    scheduled_date: Optional[datetime] = None
    result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "item_id": self.item_id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "estimated_hours": self.estimated_hours,
            "assigned_role": self.assigned_role,
            "status": self.status,
            "scheduled_date": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "result": self.result,
        }


@dataclass
class GoalDecompositionResult:
    """目标拆解结果。"""

    goal: EntrepreneurialGoal
    projects: List[Project] = field(default_factory=list)
    milestones: List[Milestone] = field(default_factory=list)
    weekly_tasks: List[WeeklyTask] = field(default_factory=list)
    daily_work_items: List[DailyWorkItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "goal": self.goal.to_dict(),
            "projects": [p.to_dict() for p in self.projects],
            "milestones": [m.to_dict() for m in self.milestones],
            "weekly_tasks": [t.to_dict() for t in self.weekly_tasks],
            "daily_work_items": [w.to_dict() for w in self.daily_work_items],
        }


class GoalDecomposer:
    """目标拆解引擎。

    将创业目标拆解为项目、里程碑、周任务和日工单四个层级。
    """

    def __init__(self) -> None:
        """初始化目标拆解引擎。"""
        logger.info("初始化目标拆解引擎")

    def decompose(self, goal: str, industry: str = "general") -> GoalDecompositionResult:
        """拆解创业目标。

        Args:
            goal: 创业目标描述
            industry: 行业类型 (general/hardware/ecommerce/content/service)

        Returns:
            目标拆解结果，包含项目、里程碑、周任务和日工单
        """
        logger.info(f"开始拆解目标: {goal[:50]}..., 行业: {industry}")

        industry = industry.lower()
        if industry not in [e.value for e in IndustryType]:
            logger.warning(f"未知行业类型: {industry}，使用通用模板")
            industry = IndustryType.GENERAL.value

        time_horizon = self._extract_time_horizon(goal)
        key_metrics = self._extract_key_metrics(goal, industry)

        entrepreneurial_goal = EntrepreneurialGoal(
            description=goal,
            industry=industry,
            time_horizon=time_horizon,
            key_metrics=key_metrics,
        )

        projects = self._generate_projects(entrepreneurial_goal, industry)
        milestones: List[Milestone] = []
        weekly_tasks: List[WeeklyTask] = []
        daily_work_items: List[DailyWorkItem] = []

        for project in projects:
            project_milestones = self._generate_milestones(project, industry)
            milestones.extend(project_milestones)

            for milestone in project_milestones:
                milestone_tasks = self._generate_weekly_tasks(milestone, industry)
                weekly_tasks.extend(milestone_tasks)

                for task in milestone_tasks:
                    task_items = self._generate_daily_work_items(task, industry)
                    daily_work_items.extend(task_items)

        result = GoalDecompositionResult(
            goal=entrepreneurial_goal,
            projects=projects,
            milestones=milestones,
            weekly_tasks=weekly_tasks,
            daily_work_items=daily_work_items,
        )

        logger.info(
            f"目标拆解完成: {len(projects)}个项目, {len(milestones)}个里程碑, "
            f"{len(weekly_tasks)}个周任务, {len(daily_work_items)}个日工单"
        )
        return result

    def _extract_time_horizon(self, goal: str) -> str:
        """从目标描述中提取时间周期。

        Args:
            goal: 目标描述

        Returns:
            时间周期描述
        """
        goal_lower = goal.lower()
        if "一年" in goal or "1年" in goal or "annual" in goal_lower:
            return "1年"
        elif "半年" in goal or "6个月" in goal or "half year" in goal_lower:
            return "6个月"
        elif "三个月" in goal or "3个月" in goal or "quarter" in goal_lower:
            return "3个月"
        elif "一个月" in goal or "1个月" in goal or "month" in goal_lower:
            return "1个月"
        else:
            return "6个月"

    def _extract_key_metrics(self, goal: str, industry: str) -> List[str]:
        """从目标描述中提取关键指标。

        Args:
            goal: 目标描述
            industry: 行业类型

        Returns:
            关键指标列表
        """
        metrics: List[str] = []

        if "营收" in goal or "收入" in goal or "revenue" in goal.lower():
            metrics.append("营收目标")
        if "用户" in goal or "customer" in goal.lower() or "user" in goal.lower():
            metrics.append("用户增长")
        if "利润" in goal or "profit" in goal.lower():
            metrics.append("利润率")
        if "市场份额" in goal or "market share" in goal.lower():
            metrics.append("市场份额")
        if "产品" in goal or "product" in goal.lower():
            metrics.append("产品上线")

        if not metrics:
            default_metrics = {
                IndustryType.HARDWARE.value: ["产品上市", "销量目标", "供应链稳定性"],
                IndustryType.ECOMMERCE.value: ["GMV目标", "用户增长", "复购率"],
                IndustryType.CONTENT.value: ["内容产出量", "用户增长", "变现收入"],
                IndustryType.SERVICE.value: ["客户数量", "服务满意度", "复购率"],
                IndustryType.GENERAL.value: ["营收目标", "用户增长", "产品交付"],
            }
            metrics = default_metrics.get(industry, ["营收目标", "用户增长"])

        return metrics

    def _generate_projects(self, goal: EntrepreneurialGoal, industry: str) -> List[Project]:
        """生成项目列表。

        Args:
            goal: 创业总目标
            industry: 行业类型

        Returns:
            项目列表
        """
        now = datetime.now()
        months = self._parse_time_horizon_months(goal.time_horizon)
        end_date = now + timedelta(days=months * 30)

        project_templates = self._get_project_templates(industry)
        projects: List[Project] = []

        for idx, template in enumerate(project_templates):
            project_start = now + timedelta(days=idx * 30)
            project_end = min(project_start + timedelta(days=60), end_date)
            if project_start >= end_date:
                break

            project = Project(
                name=template["name"],
                description=template["description"],
                start_date=project_start,
                end_date=project_end,
                assigned_role=template["role"],
                goal_id=goal.goal_id,
            )
            projects.append(project)

        return projects

    def _get_project_templates(self, industry: str) -> List[Dict[str, Any]]:
        """获取行业项目模板。

        Args:
            industry: 行业类型

        Returns:
            项目模板列表
        """
        templates = {
            IndustryType.HARDWARE.value: [
                {
                    "name": "产品定义与原型设计",
                    "description": "市场调研、需求分析、产品原型设计",
                    "role": OPCRole.PRODUCT_RD.value,
                },
                {
                    "name": "供应链与生产准备",
                    "description": "供应商选择、模具开发、小批量试产",
                    "role": OPCRole.PRODUCT_RD.value,
                },
                {
                    "name": "品牌建设与营销推广",
                    "description": "品牌定位、渠道建设、营销推广",
                    "role": OPCRole.MARKET_RESEARCH.value,
                },
                {
                    "name": "销售与客户服务体系",
                    "description": "销售渠道搭建、客服体系建立",
                    "role": OPCRole.CUSTOMER_SERVICE.value,
                },
            ],
            IndustryType.ECOMMERCE.value: [
                {
                    "name": "选品与供应链搭建",
                    "description": "市场分析、选品策略、供应商对接",
                    "role": OPCRole.MARKET_RESEARCH.value,
                },
                {
                    "name": "电商平台搭建",
                    "description": "店铺装修、产品上架、支付物流配置",
                    "role": OPCRole.PRODUCT_RD.value,
                },
                {
                    "name": "流量获取与运营",
                    "description": "推广策略、内容营销、用户运营",
                    "role": OPCRole.CONTENT_MARKETING.value,
                },
                {
                    "name": "客服与售后体系",
                    "description": "客服团队、退换货流程、用户反馈处理",
                    "role": OPCRole.CUSTOMER_SERVICE.value,
                },
            ],
            IndustryType.CONTENT.value: [
                {
                    "name": "内容定位与策略",
                    "description": "赛道分析、用户画像、内容策略制定",
                    "role": OPCRole.CONTENT_MARKETING.value,
                },
                {
                    "name": "内容生产体系搭建",
                    "description": "选题规划、创作流程、质量标准",
                    "role": OPCRole.CONTENT_MARKETING.value,
                },
                {
                    "name": "渠道运营与增长",
                    "description": "多平台分发、用户增长、互动运营",
                    "role": OPCRole.MARKET_RESEARCH.value,
                },
                {
                    "name": "商业化变现",
                    "description": "变现模式、广告合作、付费产品",
                    "role": OPCRole.FINANCE.value,
                },
            ],
            IndustryType.SERVICE.value: [
                {
                    "name": "服务产品设计",
                    "description": "服务定义、流程设计、定价策略",
                    "role": OPCRole.PRODUCT_RD.value,
                },
                {
                    "name": "市场拓展与获客",
                    "description": "目标客户分析、渠道建设、销售转化",
                    "role": OPCRole.MARKET_RESEARCH.value,
                },
                {
                    "name": "服务交付体系",
                    "description": "服务流程标准化、质量管控、客户成功",
                    "role": OPCRole.CUSTOMER_SERVICE.value,
                },
                {
                    "name": "财务与运营优化",
                    "description": "成本控制、现金流管理、效率提升",
                    "role": OPCRole.FINANCE.value,
                },
            ],
            IndustryType.GENERAL.value: [
                {
                    "name": "市场调研与产品规划",
                    "description": "市场分析、竞品调研、产品规划",
                    "role": OPCRole.MARKET_RESEARCH.value,
                },
                {
                    "name": "产品研发与落地",
                    "description": "产品开发、测试迭代、上线发布",
                    "role": OPCRole.PRODUCT_RD.value,
                },
                {
                    "name": "营销推广与用户增长",
                    "description": "品牌建设、渠道推广、用户获取",
                    "role": OPCRole.CONTENT_MARKETING.value,
                },
                {
                    "name": "运营优化与商业变现",
                    "description": "用户运营、收入增长、财务优化",
                    "role": OPCRole.FINANCE.value,
                },
            ],
        }

        return templates.get(industry, templates[IndustryType.GENERAL.value])

    def _generate_milestones(self, project: Project, industry: str) -> List[Milestone]:
        """生成项目里程碑。

        Args:
            project: 项目
            industry: 行业类型

        Returns:
            里程碑列表
        """
        milestones: List[Milestone] = []
        project_duration = (project.end_date - project.start_date).days
        milestone_count = max(2, min(4, project_duration // 30))

        milestone_templates = self._get_milestone_templates(project.name, industry)

        for i in range(min(milestone_count, len(milestone_templates))):
            template = milestone_templates[i]
            milestone_day = int(project_duration * (i + 1) / milestone_count)
            deadline = project.start_date + timedelta(days=milestone_day)

            milestone = Milestone(
                project_id=project.project_id,
                title=template["title"],
                deadline=deadline,
                deliverables=template["deliverables"],
            )
            milestones.append(milestone)

        return milestones

    def _get_milestone_templates(self, project_name: str, industry: str) -> List[Dict[str, Any]]:
        """获取里程碑模板。

        Args:
            project_name: 项目名称
            industry: 行业类型

        Returns:
            里程碑模板列表
        """
        return [
            {
                "title": f"{project_name} - 第一阶段：调研与规划",
                "deliverables": ["调研报告", "详细规划方案", "资源清单"],
            },
            {
                "title": f"{project_name} - 第二阶段：核心落地",
                "deliverables": ["核心产出物", "阶段性成果", "质量检测报告"],
            },
            {
                "title": f"{project_name} - 第三阶段：测试与优化",
                "deliverables": ["测试报告", "优化方案", "最终版本"],
            },
            {
                "title": f"{project_name} - 第四阶段：交付与复盘",
                "deliverables": ["最终交付物", "项目总结", "经验沉淀"],
            },
        ]

    def _generate_weekly_tasks(self, milestone: Milestone, industry: str) -> List[WeeklyTask]:
        """生成周度任务。

        Args:
            milestone: 里程碑
            industry: 行业类型

        Returns:
            周任务列表
        """
        tasks: List[WeeklyTask] = []
        task_templates = self._get_weekly_task_templates(milestone.title, industry)

        for week_num, template in enumerate(task_templates, start=1):
            task = WeeklyTask(
                milestone_id=milestone.milestone_id,
                title=template["title"],
                description=template["description"],
                priority=template["priority"],
                assigned_role=template["role"],
                week_number=week_num,
            )
            tasks.append(task)

        return tasks

    def _get_weekly_task_templates(self, milestone_title: str, industry: str) -> List[Dict[str, Any]]:
        """获取周任务模板。

        Args:
            milestone_title: 里程碑标题
            industry: 行业类型

        Returns:
            周任务模板列表
        """
        base_role = OPCRole.PRODUCT_RD.value
        if "调研" in milestone_title or "市场" in milestone_title:
            base_role = OPCRole.MARKET_RESEARCH.value
        elif "内容" in milestone_title or "营销" in milestone_title:
            base_role = OPCRole.CONTENT_MARKETING.value
        elif "客服" in milestone_title or "服务" in milestone_title:
            base_role = OPCRole.CUSTOMER_SERVICE.value
        elif "财务" in milestone_title or "变现" in milestone_title:
            base_role = OPCRole.FINANCE.value

        return [
            {
                "title": f"{milestone_title} - 第1周：需求分析与方案设计",
                "description": "详细需求分析、方案设计、资源协调",
                "priority": 1,
                "role": base_role,
            },
            {
                "title": f"{milestone_title} - 第2周：核心工作执行",
                "description": "核心任务执行、关键产出物制作",
                "priority": 1,
                "role": base_role,
            },
            {
                "title": f"{milestone_title} - 第3周：集成与测试",
                "description": "成果集成、测试验证、问题修复",
                "priority": 2,
                "role": base_role,
            },
            {
                "title": f"{milestone_title} - 第4周：优化与交付",
                "description": "优化调整、文档编写、成果交付",
                "priority": 2,
                "role": base_role,
            },
        ]

    def _generate_daily_work_items(self, task: WeeklyTask, industry: str) -> List[DailyWorkItem]:
        """生成每日工单。

        Args:
            task: 周任务
            industry: 行业类型

        Returns:
            日工单列表
        """
        items: List[DailyWorkItem] = []
        item_templates = self._get_daily_work_item_templates(task.title, task.assigned_role)

        for template in item_templates:
            item = DailyWorkItem(
                task_id=task.task_id,
                title=template["title"],
                description=template["description"],
                estimated_hours=template["hours"],
                assigned_role=task.assigned_role,
            )
            items.append(item)

        return items

    def _get_daily_work_item_templates(self, task_title: str, role: str) -> List[Dict[str, Any]]:
        """获取日工单模板。

        Args:
            task_title: 任务标题
            role: 分配角色

        Returns:
            日工单模板列表
        """
        return [
            {
                "title": f"{task_title} - 上午：规划与准备",
                "description": "当日工作计划、资源准备、环境搭建",
                "hours": 2.0,
            },
            {
                "title": f"{task_title} - 下午：核心工作",
                "description": "核心任务执行、关键产出物开发",
                "hours": 3.0,
            },
            {
                "title": f"{task_title} - 晚间：复盘与文档",
                "description": "当日成果复盘、文档记录、问题整理",
                "hours": 1.0,
            },
        ]

    def _parse_time_horizon_months(self, time_horizon: str) -> int:
        """解析时间周期为月数。

        Args:
            time_horizon: 时间周期描述

        Returns:
            月数
        """
        if "1年" in time_horizon or "一年" in time_horizon:
            return 12
        elif "6个月" in time_horizon or "半年" in time_horizon:
            return 6
        elif "3个月" in time_horizon or "三个月" in time_horizon:
            return 3
        elif "1个月" in time_horizon or "一个月" in time_horizon:
            return 1
        else:
            return 6
