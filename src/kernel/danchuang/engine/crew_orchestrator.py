"""Crew 编排引擎 —— CrewAI 风格的多智能体协作框架。

提供基于角色+任务+流程的多智能体协作编排，支持三种流程类型：
- SEQUENTIAL：顺序执行，任务按依赖关系依次执行
- PARALLEL：并行执行，无依赖的任务同时执行
- HIERARCHICAL：层级执行，由管理者智能体协调分配任务

与 OPC 数字组织内核的 5 大岗位体系深度集成。
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..opc.roles import OPCRole, OPCAgentRole, create_agent

logger = logging.getLogger(__name__)


class ProcessType(str, Enum):
    """Crew 流程类型枚举。"""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CrewAgent:
    """Crew 智能体数据类。

    封装智能体的身份信息、角色配置和系统提示词。
    """

    agent_id: str = field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    name: str = ""
    role: str = ""
    opc_role: Optional[OPCRole] = None
    system_prompt: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    is_manager: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的智能体信息
        """
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "opc_role": self.opc_role.value if self.opc_role else None,
            "system_prompt": self.system_prompt,
            "description": self.description,
            "capabilities": self.capabilities.copy(),
            "tools": self.tools.copy(),
            "is_manager": self.is_manager,
        }


@dataclass
class CrewTask:
    """Crew 任务数据类。

    封装任务的描述、预期输出、分配角色和依赖关系。
    """

    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    expected_output: str = ""
    agent_role: str = ""
    opc_role: Optional[OPCRole] = None
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的任务信息
        """
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "expected_output": self.expected_output,
            "agent_role": self.agent_role,
            "opc_role": self.opc_role.value if self.opc_role else None,
            "dependencies": self.dependencies.copy(),
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "assigned_agent_id": self.assigned_agent_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "context": self.context.copy(),
        }


@dataclass
class CrewResult:
    """Crew 执行结果数据类。

    封装整个 Crew 执行的最终结果和统计信息。
    """

    success: bool = False
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    tasks: List[CrewTask] = field(default_factory=list)
    final_output: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的执行结果
        """
        return {
            "success": self.success,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "skipped_tasks": self.skipped_tasks,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "tasks": [t.to_dict() for t in self.tasks],
            "final_output": self.final_output,
            "errors": self.errors.copy(),
        }


class TaskExecutor:
    """任务执行器。

    模拟执行任务，生成模拟结果。在实际生产环境中可替换为真实的 LLM 调用。
    """

    def __init__(self, verbose: bool = False) -> None:
        """初始化任务执行器。

        Args:
            verbose: 是否输出详细日志
        """
        self._verbose = verbose
        logger.debug("任务执行器初始化完成，verbose=%s", verbose)

    def execute(
        self,
        task: CrewTask,
        agent: CrewAgent,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """执行任务（模拟）。

        Args:
            task: 待执行的任务
            agent: 执行任务的智能体
            context: 执行上下文

        Returns:
            任务执行结果字符串

        Raises:
            RuntimeError: 任务执行失败时抛出
        """
        if self._verbose:
            logger.info(
                "[%s] 执行任务 '%s' (角色: %s)",
                agent.name,
                task.name,
                agent.role,
            )

        time.sleep(0.1)

        result_parts = [
            f"任务：{task.name}",
            f"执行者：{agent.name}（{agent.role}）",
            f"描述：{task.description}",
        ]

        if task.expected_output:
            result_parts.append(f"预期产出：{task.expected_output}")

        if context:
            context_summary = ", ".join(f"{k}={v}" for k, v in list(context.items())[:3])
            result_parts.append(f"上下文：{context_summary}")

        result_parts.append("")
        result_parts.append("【执行结果】")
        result_parts.append(self._generate_mock_result(task, agent))

        result = "\n".join(result_parts)

        if self._verbose:
            logger.info("[%s] 任务 '%s' 执行完成", agent.name, task.name)

        return result

    def _generate_mock_result(self, task: CrewTask, agent: CrewAgent) -> str:
        """生成模拟执行结果。

        Args:
            task: 任务对象
            agent: 智能体对象

        Returns:
            模拟结果文本
        """
        task_keywords = [
            "调研", "分析", "设计", "开发", "测试", "部署",
            "报告", "方案", "计划", "总结", "评估", "优化",
        ]

        matched_keywords = [kw for kw in task_keywords if kw in task.name or kw in task.description]
        action = matched_keywords[0] if matched_keywords else "处理"

        result_templates = {
            "调研": (
                f"本次{action}覆盖了主要市场竞品和用户反馈渠道，\n"
                f"共收集有效样本 {len(task.description) // 10 + 5} 份，\n"
                f"形成了 3 个核心发现和 5 条行动建议。\n"
                f"详细数据和分析图表见附录。"
            ),
            "分析": (
                f"完成深度{action}，识别出 {len(task.dependencies) + 2} 个关键影响因素，\n"
                f"构建了因果关系模型，输出优先级排序清单。\n"
                f"建议重点关注前 2 项高影响因素。"
            ),
            "设计": (
                f"完成{action}方案，包含整体架构图和详细模块设计，\n"
                f"满足 {task.expected_output or '所有功能需求'}。\n"
                f"方案经过可行性评估，技术风险可控。"
            ),
            "开发": (
                f"完成核心功能{action}，代码经过单元测试，\n"
                f"覆盖率达到 85% 以上。\n"
                f"已提交至代码仓库，等待集成测试。"
            ),
            "测试": (
                f"完成全面{action}，共执行测试用例 {len(task.description) // 8 + 10} 个，\n"
                f"通过率 98%，遗留问题均已记录并安排修复。\n"
                f"整体质量达到上线标准。"
            ),
            "部署": (
                f"成功完成生产环境{action}，服务已正常启动，\n"
                f"健康检查通过，监控指标正常。\n"
                f"回滚方案已准备就绪。"
            ),
            "报告": (
                f"生成完整{action}，包含背景、方法、发现、建议四大部分，\n"
                f"共 {len(task.description) // 20 + 8} 页内容，\n"
                f"附数据支撑材料和参考文献。"
            ),
            "方案": (
                f"制定了详细的{action}，涵盖目标、路径、资源、风险四个维度，\n"
                f"设置了 3 个阶段里程碑和关键验收标准。\n"
                f"预估总工期约 4 周。"
            ),
            "计划": (
                f"制定了详细的执行{action}，分解为 {len(task.dependencies) + 3} 个子任务，\n"
                f"明确了责任人、时间节点和交付物。\n"
                f"关键路径已识别，资源需求已评估。"
            ),
            "总结": (
                f"完成阶段性{action}，回顾了关键进展和成果，\n"
                f"提炼了 3 条成功经验和 2 个待改进项。\n"
                f"下一阶段工作计划已初步形成。"
            ),
            "评估": (
                f"完成全面{action}，从效果、效率、成本三个维度进行了量化分析，\n"
                f"整体评分 8.5/10。\n"
                f"提出了 4 条优化建议，预估可提升 15% 效率。"
            ),
            "优化": (
                f"完成针对性{action}，解决了核心瓶颈问题，\n"
                f"性能提升约 {len(task.description) // 15 + 20}%，\n"
                f"用户体验指标明显改善。\n"
                f"后续将持续监控效果。"
            ),
        }

        for keyword, template in result_templates.items():
            if keyword in task.name or keyword in task.description:
                return template

        return (
            f"任务已顺利完成，达到预期目标。\n"
            f"产出物符合质量标准，可进入下一环节。\n"
            f"执行过程记录完整，经验已沉淀。"
        )


class CrewOrchestrator:
    """Crew 编排引擎。

    管理智能体团队、任务队列和执行流程，支持三种流程类型。

    回调函数签名：
    - on_task_start(task: CrewTask, agent: CrewAgent) -> None
    - on_task_complete(task: CrewTask, agent: CrewAgent, result: str) -> None
    - on_task_fail(task: CrewTask, agent: CrewAgent, error: Exception) -> None
    - on_crew_complete(result: CrewResult) -> None
    """

    def __init__(
        self,
        process_type: ProcessType = ProcessType.SEQUENTIAL,
        verbose: bool = False,
    ) -> None:
        """初始化 Crew 编排引擎。

        Args:
            process_type: 流程类型，默认为顺序执行
            verbose: 是否输出详细日志
        """
        self._process_type = process_type
        self._verbose = verbose
        self._agents: Dict[str, CrewAgent] = {}
        self._tasks: Dict[str, CrewTask] = {}
        self._executor = TaskExecutor(verbose=verbose)

        self._on_task_start: Optional[Callable[[CrewTask, CrewAgent], None]] = None
        self._on_task_complete: Optional[Callable[[CrewTask, CrewAgent, str], None]] = None
        self._on_task_fail: Optional[Callable[[CrewTask, CrewAgent, Exception], None]] = None
        self._on_crew_complete: Optional[Callable[[CrewResult], None]] = None

        logger.info(
            "Crew 编排引擎初始化完成，process_type=%s, verbose=%s",
            process_type.value,
            verbose,
        )

    def set_callbacks(
        self,
        on_task_start: Optional[Callable[[CrewTask, CrewAgent], None]] = None,
        on_task_complete: Optional[Callable[[CrewTask, CrewAgent, str], None]] = None,
        on_task_fail: Optional[Callable[[CrewTask, CrewAgent, Exception], None]] = None,
        on_crew_complete: Optional[Callable[[CrewResult], None]] = None,
    ) -> None:
        """设置回调函数。

        Args:
            on_task_start: 任务开始回调
            on_task_complete: 任务完成回调
            on_task_fail: 任务失败回调
            on_crew_complete: Crew 完成回调
        """
        if on_task_start is not None:
            self._on_task_start = on_task_start
        if on_task_complete is not None:
            self._on_task_complete = on_task_complete
        if on_task_fail is not None:
            self._on_task_fail = on_task_fail
        if on_crew_complete is not None:
            self._on_crew_complete = on_crew_complete

    def add_agent(self, agent: CrewAgent) -> str:
        """添加智能体。

        Args:
            agent: 智能体对象

        Returns:
            智能体 ID
        """
        self._agents[agent.agent_id] = agent
        logger.debug("添加智能体: %s (%s)", agent.name, agent.agent_id)
        return agent.agent_id

    def add_agents_from_opc(self, role: OPCRole, count: int = 1) -> List[str]:
        """从 OPC 岗位体系添加智能体。

        Args:
            role: OPC 岗位类型
            count: 添加数量，默认为 1

        Returns:
            添加的智能体 ID 列表
        """
        agent_ids: List[str] = []
        opc_agent = create_agent(role)

        for i in range(count):
            suffix = f"_{i + 1}" if count > 1 else ""
            agent = CrewAgent(
                name=f"{opc_agent.name}{suffix}",
                role=opc_agent.name,
                opc_role=role,
                system_prompt=self._build_system_prompt(opc_agent),
                description=opc_agent.description,
                capabilities=opc_agent.capabilities.copy(),
                tools=opc_agent.tools.copy(),
            )
            agent_id = self.add_agent(agent)
            agent_ids.append(agent_id)

        if self._verbose:
            logger.info("从 OPC 岗位 %s 添加了 %d 个智能体", role.value, count)

        return agent_ids

    def _build_system_prompt(self, opc_agent: OPCAgentRole) -> str:
        """基于 OPC 岗位智能体构建系统提示词。

        Args:
            opc_agent: OPC 岗位智能体

        Returns:
            系统提示词
        """
        prompt_parts = [
            f"你是一名{opc_agent.name}。",
            f"{opc_agent.description}",
            "",
            "你的核心能力包括：",
        ]
        for cap in opc_agent.capabilities:
            prompt_parts.append(f"- {cap}")
        prompt_parts.append("")
        prompt_parts.append("请基于以上定位和能力，专业高效地完成分配给你的任务。")

        return "\n".join(prompt_parts)

    def add_task(self, task: CrewTask) -> str:
        """添加任务。

        Args:
            task: 任务对象

        Returns:
            任务 ID
        """
        self._tasks[task.task_id] = task
        logger.debug("添加任务: %s (%s)", task.name, task.task_id)
        return task.task_id

    def list_agents(self) -> List[CrewAgent]:
        """列出所有智能体。

        Returns:
            智能体列表
        """
        return list(self._agents.values())

    def list_tasks(self) -> List[CrewTask]:
        """列出所有任务。

        Returns:
            任务列表
        """
        return list(self._tasks.values())

    def get_agent(self, agent_id: str) -> Optional[CrewAgent]:
        """获取智能体。

        Args:
            agent_id: 智能体 ID

        Returns:
            智能体对象，不存在则返回 None
        """
        return self._agents.get(agent_id)

    def get_task(self, task_id: str) -> Optional[CrewTask]:
        """获取任务。

        Args:
            task_id: 任务 ID

        Returns:
            任务对象，不存在则返回 None
        """
        return self._tasks.get(task_id)

    def kickoff(self) -> CrewResult:
        """启动 Crew 执行。

        根据配置的流程类型执行所有任务。

        Returns:
            Crew 执行结果
        """
        if not self._tasks:
            logger.warning("没有任务可供执行")
            return CrewResult(success=True, total_tasks=0)

        if not self._agents:
            logger.warning("没有可用智能体，尝试自动添加 OPC 智能体")
            self._auto_add_agents()

        logger.info(
            "Crew 启动执行: process_type=%s, agents=%d, tasks=%d",
            self._process_type.value,
            len(self._agents),
            len(self._tasks),
        )

        result = CrewResult(
            total_tasks=len(self._tasks),
            started_at=datetime.now(),
        )

        try:
            if self._process_type == ProcessType.SEQUENTIAL:
                self._execute_sequential(result)
            elif self._process_type == ProcessType.PARALLEL:
                self._execute_parallel(result)
            elif self._process_type == ProcessType.HIERARCHICAL:
                self._execute_hierarchical(result)
            else:
                raise ValueError(f"不支持的流程类型: {self._process_type}")

            result.success = result.failed_tasks == 0

        except Exception as e:
            logger.exception("Crew 执行异常: %s", e)
            result.success = False
            result.errors.append(str(e))

        result.completed_at = datetime.now()
        if result.started_at and result.completed_at:
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()

        result.tasks = list(self._tasks.values())
        result.completed_tasks = sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED
        )
        result.failed_tasks = sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.FAILED
        )
        result.skipped_tasks = sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.SKIPPED
        )

        result.final_output = self._build_final_output(result)

        if self._on_crew_complete:
            try:
                self._on_crew_complete(result)
            except Exception:
                logger.exception("on_crew_complete 回调执行异常")

        logger.info(
            "Crew 执行完成: success=%s, completed=%d/%d, failed=%d, duration=%.2fs",
            result.success,
            result.completed_tasks,
            result.total_tasks,
            result.failed_tasks,
            result.duration_seconds,
        )

        return result

    def _auto_add_agents(self) -> None:
        """根据任务需要自动添加 OPC 智能体。"""
        required_roles: set = set()
        for task in self._tasks.values():
            if task.opc_role:
                required_roles.add(task.opc_role)

        if not required_roles:
            for role in OPCRole:
                self.add_agents_from_opc(role, count=1)
            return

        for role in required_roles:
            self.add_agents_from_opc(role, count=1)

    def _execute_sequential(self, result: CrewResult) -> None:
        """顺序执行任务。

        按依赖关系拓扑排序后依次执行任务。

        Args:
            result: 执行结果对象（更新用）
        """
        sorted_tasks = self._topological_sort()
        if self._verbose:
            logger.info("顺序执行模式，任务执行顺序: %s", [t.name for t in sorted_tasks])

        for task in sorted_tasks:
            if self._should_skip_task(task):
                task.status = TaskStatus.SKIPPED
                if self._verbose:
                    logger.info("跳过任务 '%s'（依赖任务失败）", task.name)
                continue

            self._execute_single_task(task, result)

    def _execute_parallel(self, result: CrewResult) -> None:
        """并行执行任务（模拟）。

        无依赖关系的任务按批次执行，模拟并行效果。

        Args:
            result: 执行结果对象（更新用）
        """
        task_levels = self._get_task_levels()
        if self._verbose:
            logger.info("并行执行模式，共 %d 个执行批次", len(task_levels))

        for level_idx, level_tasks in enumerate(task_levels, start=1):
            if self._verbose:
                logger.info(
                    "执行第 %d/%d 批，共 %d 个任务",
                    level_idx,
                    len(task_levels),
                    len(level_tasks),
                )

            for task in level_tasks:
                if self._should_skip_task(task):
                    task.status = TaskStatus.SKIPPED
                    if self._verbose:
                        logger.info("跳过任务 '%s'（依赖任务失败）", task.name)
                    continue

                self._execute_single_task(task, result)

    def _execute_hierarchical(self, result: CrewResult) -> None:
        """层级执行任务。

        由管理者智能体协调，按优先级和依赖关系分配任务。

        Args:
            result: 执行结果对象（更新用）
        """
        manager_agent = self._get_or_create_manager()
        if self._verbose:
            logger.info("层级执行模式，管理者: %s", manager_agent.name)

        sorted_tasks = self._topological_sort()

        for task in sorted_tasks:
            if self._should_skip_task(task):
                task.status = TaskStatus.SKIPPED
                if self._verbose:
                    logger.info("跳过任务 '%s'（依赖任务失败）", task.name)
                continue

            assigned_agent = self._assign_task_by_manager(task, manager_agent)
            task.assigned_agent_id = assigned_agent.agent_id
            self._execute_single_task(task, result, assigned_agent)

    def _get_or_create_manager(self) -> CrewAgent:
        """获取或创建管理者智能体。

        Returns:
            管理者智能体
        """
        for agent in self._agents.values():
            if agent.is_manager:
                return agent

        manager = CrewAgent(
            name="项目经理",
            role="项目管理",
            system_prompt=(
                "你是一名经验丰富的项目经理，擅长协调团队资源、"
                "把控项目进度、确保高质量交付。你需要合理分配任务给团队成员，"
                "并监督执行过程。"
            ),
            description="负责项目整体协调和任务分配",
            is_manager=True,
        )
        self.add_agent(manager)
        return manager

    def _assign_task_by_manager(
        self, task: CrewTask, manager: CrewAgent
    ) -> CrewAgent:
        """由管理者分配任务给最合适的智能体。

        Args:
            task: 待分配的任务
            manager: 管理者智能体

        Returns:
            被分配的智能体
        """
        candidates = [a for a in self._agents.values() if not a.is_manager]

        if not candidates:
            return manager

        if task.opc_role:
            for agent in candidates:
                if agent.opc_role == task.opc_role:
                    return agent

        if task.agent_role:
            for agent in candidates:
                if task.agent_role in agent.role or task.agent_role in agent.name:
                    return agent

        return candidates[0]

    def _execute_single_task(
        self,
        task: CrewTask,
        result: CrewResult,
        assigned_agent: Optional[CrewAgent] = None,
    ) -> None:
        """执行单个任务。

        Args:
            task: 任务对象
            result: 执行结果对象
            assigned_agent: 指定的执行智能体，None 则自动分配
        """
        agent = assigned_agent or self._find_agent_for_task(task)

        if agent is None:
            task.status = TaskStatus.FAILED
            task.error = "未找到合适的执行智能体"
            result.errors.append(f"任务 '{task.name}': {task.error}")
            logger.warning("任务 '%s' 找不到合适的执行智能体", task.name)
            return

        task.assigned_agent_id = agent.agent_id
        task.started_at = datetime.now()
        task.status = TaskStatus.IN_PROGRESS

        if self._on_task_start:
            try:
                self._on_task_start(task, agent)
            except Exception:
                logger.exception("on_task_start 回调执行异常")

        try:
            context = self._build_task_context(task)
            task_result = self._executor.execute(task, agent, context)
            task.result = task_result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()

            if self._on_task_complete:
                try:
                    self._on_task_complete(task, agent, task_result)
                except Exception:
                    logger.exception("on_task_complete 回调执行异常")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            result.errors.append(f"任务 '{task.name}': {e}")

            if self._on_task_fail:
                try:
                    self._on_task_fail(task, agent, e)
                except Exception:
                    logger.exception("on_task_fail 回调执行异常")

            logger.exception("任务 '%s' 执行失败", task.name)

    def _find_agent_for_task(self, task: CrewTask) -> Optional[CrewAgent]:
        """为任务寻找合适的智能体。

        Args:
            task: 任务对象

        Returns:
            合适的智能体，找不到则返回 None
        """
        if task.assigned_agent_id:
            return self._agents.get(task.assigned_agent_id)

        if task.opc_role:
            for agent in self._agents.values():
                if agent.opc_role == task.opc_role:
                    return agent

        if task.agent_role:
            for agent in self._agents.values():
                if task.agent_role in agent.role or task.agent_role in agent.name:
                    return agent

        available = [a for a in self._agents.values() if not a.is_manager]
        return available[0] if available else None

    def _build_task_context(self, task: CrewTask) -> Dict[str, Any]:
        """构建任务执行上下文。

        Args:
            task: 任务对象

        Returns:
            上下文字典
        """
        context: Dict[str, Any] = task.context.copy()

        for dep_id in task.dependencies:
            dep_task = self._tasks.get(dep_id)
            if dep_task and dep_task.result:
                context[f"result_{dep_task.name[:20]}"] = dep_task.result[:200]

        return context

    def _should_skip_task(self, task: CrewTask) -> bool:
        """判断是否应该跳过任务。

        当任一依赖任务失败时，跳过该任务。

        Args:
            task: 任务对象

        Returns:
            是否应该跳过
        """
        for dep_id in task.dependencies:
            dep_task = self._tasks.get(dep_id)
            if dep_task and dep_task.status == TaskStatus.FAILED:
                return True
        return False

    def _topological_sort(self) -> List[CrewTask]:
        """对任务进行拓扑排序。

        Returns:
            按依赖关系排序的任务列表

        Raises:
            ValueError: 当任务依赖存在环时抛出
        """
        in_degree: Dict[str, int] = {tid: 0 for tid in self._tasks}
        adjacency: Dict[str, List[str]] = {tid: [] for tid in self._tasks}

        for task_id, task in self._tasks.items():
            for dep_id in task.dependencies:
                if dep_id in self._tasks:
                    adjacency[dep_id].append(task_id)
                    in_degree[task_id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        result: List[str] = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self._tasks):
            raise ValueError("任务依赖关系存在循环，无法排序")

        return [self._tasks[tid] for tid in result]

    def _get_task_levels(self) -> List[List[CrewTask]]:
        """获取任务的层级分组（用于并行执行）。

        同一层级的任务无依赖关系，可并行执行。

        Returns:
            按层级分组的任务列表
        """
        levels: List[List[CrewTask]] = []
        completed: set = set()
        remaining = set(self._tasks.keys())

        while remaining:
            current_level: List[str] = []

            for task_id in list(remaining):
                task = self._tasks[task_id]
                deps_met = all(
                    dep in completed or dep not in self._tasks
                    for dep in task.dependencies
                )
                if deps_met:
                    current_level.append(task_id)

            if not current_level:
                raise ValueError("任务依赖关系存在循环，无法分层")

            levels.append([self._tasks[tid] for tid in current_level])
            completed.update(current_level)
            remaining -= set(current_level)

        return levels

    def _build_final_output(self, result: CrewResult) -> str:
        """构建最终输出摘要。

        Args:
            result: 执行结果对象

        Returns:
            最终输出摘要文本
        """
        lines = [
            "=" * 50,
            "Crew 执行报告",
            "=" * 50,
            f"流程类型: {self._process_type.value}",
            f"总任务数: {result.total_tasks}",
            f"已完成: {result.completed_tasks}",
            f"失败: {result.failed_tasks}",
            f"跳过: {result.skipped_tasks}",
            f"执行状态: {'成功' if result.success else '失败'}",
            f"总耗时: {result.duration_seconds:.2f} 秒",
            "",
            "任务明细:",
            "-" * 50,
        ]

        for task in result.tasks:
            status_icon = {
                TaskStatus.COMPLETED: "✓",
                TaskStatus.FAILED: "✗",
                TaskStatus.SKIPPED: "→",
                TaskStatus.PENDING: "○",
                TaskStatus.IN_PROGRESS: "…",
            }.get(task.status, "?")

            agent_name = ""
            if task.assigned_agent_id:
                agent = self._agents.get(task.assigned_agent_id)
                agent_name = agent.name if agent else task.assigned_agent_id

            lines.append(f"  {status_icon} {task.name} [{task.status.value}] - {agent_name}")

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)
