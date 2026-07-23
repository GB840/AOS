from __future__ import annotations

"""Playbook 工作流模板库与状态检查点管理器。

借鉴 The Agency 的 playbook 理念与 LangGraph 的 checkpoint 机制，
提供行业标准化工作流模板与可回滚的工作流状态管理能力。

核心组件：
- PlaybookTemplate：行业工作流模板定义
- PlaybookStep：单步工作流节点
- PlaybookLibrary：模板库管理
- WorkflowStatus：工作流状态枚举
- WorkflowStateManager：工作流状态与检查点管理
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..opc.roles import OPCRole

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """工作流状态枚举。"""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """步骤状态枚举。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlaybookStep:
    """Playbook 单步定义。

    Attributes:
        step_id: 步骤唯一标识
        name: 步骤名称
        description: 步骤详细描述
        opc_role: 负责执行的 OPC 岗位
        assigned_role: 具体分配角色（可为细分专业角色）
        deliverables: 交付物清单
        dependencies: 依赖的前置步骤 ID 列表
        tools: 执行此步骤所需工具
    """

    step_id: str
    name: str
    description: str
    opc_role: OPCRole = OPCRole.PRODUCT_RD
    assigned_role: str = ""
    deliverables: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的步骤数据
        """
        data = asdict(self)
        data["opc_role"] = self.opc_role.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaybookStep":
        """从字典创建实例。

        Args:
            data: 字典数据

        Returns:
            PlaybookStep 实例
        """
        data = dict(data)
        if "opc_role" in data:
            data["opc_role"] = OPCRole(data["opc_role"])
        return cls(**data)


@dataclass
class PlaybookTemplate:
    """Playbook 工作流模板。

    定义一个完整的行业工作流模板，包含多个有序步骤。

    Attributes:
        template_id: 模板唯一标识
        name: 模板名称
        description: 模板详细描述
        industry: 适用行业
        tags: 标签列表
        steps: 步骤列表
        estimated_duration: 预估工期（天）
    """

    template_id: str
    name: str
    description: str
    industry: str = "general"
    tags: List[str] = field(default_factory=list)
    steps: List[PlaybookStep] = field(default_factory=list)
    estimated_duration: int = 30

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的模板数据
        """
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "industry": self.industry,
            "tags": self.tags,
            "steps": [step.to_dict() for step in self.steps],
            "estimated_duration": self.estimated_duration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaybookTemplate":
        """从字典创建实例。

        Args:
            data: 字典数据

        Returns:
            PlaybookTemplate 实例
        """
        steps_data = data.get("steps", [])
        steps = [PlaybookStep.from_dict(s) for s in steps_data]
        return cls(
            template_id=data["template_id"],
            name=data["name"],
            description=data["description"],
            industry=data.get("industry", "general"),
            tags=data.get("tags", []),
            steps=steps,
            estimated_duration=data.get("estimated_duration", 30),
        )

    def get_step_by_id(self, step_id: str) -> Optional[PlaybookStep]:
        """根据步骤 ID 获取步骤。

        Args:
            step_id: 步骤 ID

        Returns:
            找到的步骤，未找到返回 None
        """
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None


@dataclass
class WorkflowCheckpoint:
    """工作流检查点。

    LangGraph 风格的状态快照，支持时间旅行调试。

    Attributes:
        checkpoint_id: 检查点唯一标识
        workflow_id: 所属工作流 ID
        step_id: 当前执行到的步骤 ID
        state_snapshot: 状态快照（完整工作流状态）
        created_at: 创建时间戳
        description: 检查点描述
    """

    checkpoint_id: str
    workflow_id: str
    step_id: str
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的检查点数据
        """
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "state_snapshot": self.state_snapshot,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowCheckpoint":
        """从字典创建实例。

        Args:
            data: 字典数据

        Returns:
            WorkflowCheckpoint 实例
        """
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now()
        return cls(
            checkpoint_id=data["checkpoint_id"],
            workflow_id=data["workflow_id"],
            step_id=data["step_id"],
            state_snapshot=data.get("state_snapshot", {}),
            created_at=created_at,
            description=data.get("description", ""),
        )


@dataclass
class WorkflowInstance:
    """工作流实例。

    基于模板创建的实际运行中的工作流。

    Attributes:
        workflow_id: 工作流唯一标识
        template_id: 关联的模板 ID
        name: 工作流名称
        status: 整体状态
        step_states: 各步骤状态映射
        created_at: 创建时间
        updated_at: 更新时间
        metadata: 附加元数据
    """

    workflow_id: str
    template_id: str
    name: str
    status: WorkflowStatus = WorkflowStatus.NOT_STARTED
    step_states: Dict[str, StepStatus] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Returns:
            字典形式的工作流实例数据
        """
        return {
            "workflow_id": self.workflow_id,
            "template_id": self.template_id,
            "name": self.name,
            "status": self.status.value,
            "step_states": {k: v.value for k, v in self.step_states.items()},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowInstance":
        """从字典创建实例。

        Args:
            data: 字典数据

        Returns:
            WorkflowInstance 实例
        """
        step_states_data = data.get("step_states", {})
        step_states = {k: StepStatus(v) for k, v in step_states_data.items()}

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        else:
            updated_at = datetime.now()

        return cls(
            workflow_id=data["workflow_id"],
            template_id=data["template_id"],
            name=data["name"],
            status=WorkflowStatus(data.get("status", WorkflowStatus.NOT_STARTED.value)),
            step_states=step_states,
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get("metadata", {}),
        )


class PlaybookLibrary:
    """Playbook 模板库。

    管理所有内置和自定义的工作流模板，
    支持模板列表查询、详情获取、智能推荐。

    Attributes:
        _templates: 内部模板存储映射
    """

    def __init__(self) -> None:
        """初始化模板库，加载内置行业模板。"""
        self._templates: Dict[str, PlaybookTemplate] = {}
        self._load_builtin_templates()

    def _load_builtin_templates(self) -> None:
        """加载内置行业模板。"""
        self._templates = {
            t.template_id: t
            for t in [
                _build_startup_mvp_template(),
                _build_hardware_dev_template(),
                _build_content_marketing_template(),
                _build_e_commerce_store_template(),
                _build_market_research_template(),
            ]
        }
        logger.info("已加载 %d 个内置 Playbook 模板", len(self._templates))

    def list_templates(
        self,
        industry: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[PlaybookTemplate]:
        """列出模板，支持按行业和标签过滤。

        Args:
            industry: 行业过滤，为 None 则不过滤
            tag: 标签过滤，为 None 则不过滤

        Returns:
            符合条件的模板列表
        """
        templates = list(self._templates.values())

        if industry:
            templates = [t for t in templates if t.industry == industry]

        if tag:
            templates = [t for t in templates if tag in t.tags]

        return templates

    def get_template(self, template_id: str) -> Optional[PlaybookTemplate]:
        """根据模板 ID 获取模板详情。

        Args:
            template_id: 模板 ID

        Returns:
            找到的模板，未找到返回 None
        """
        return self._templates.get(template_id)

    def suggest_template(
        self,
        industry: str = "general",
        keywords: Optional[List[str]] = None,
    ) -> List[PlaybookTemplate]:
        """根据行业和关键词智能推荐模板。

        基于行业匹配度和关键词相关性进行排序推荐。

        Args:
            industry: 目标行业
            keywords: 关键词列表

        Returns:
            按推荐度排序的模板列表
        """
        templates = list(self._templates.values())
        scored: List[tuple] = []

        for tpl in templates:
            score = 0.0

            if tpl.industry == industry:
                score += 10.0
            elif tpl.industry == "general":
                score += 3.0

            if keywords:
                keyword_text = " ".join(keywords).lower()
                template_text = " ".join([tpl.name, tpl.description] + tpl.tags).lower()
                for kw in keywords:
                    if kw.lower() in template_text:
                        score += 2.0

            scored.append((score, tpl))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [tpl for score, tpl in scored if score > 0] or templates

    def add_template(self, template: PlaybookTemplate) -> None:
        """添加自定义模板。

        Args:
            template: 要添加的模板
        """
        self._templates[template.template_id] = template
        logger.info("已添加自定义模板: %s (%s)", template.name, template.template_id)

    def remove_template(self, template_id: str) -> bool:
        """移除模板。

        Args:
            template_id: 要移除的模板 ID

        Returns:
            是否成功移除
        """
        if template_id in self._templates:
            del self._templates[template_id]
            logger.info("已移除模板: %s", template_id)
            return True
        return False


class WorkflowStateManager:
    """工作流状态管理器。

    提供工作流实例的创建、状态跟踪、步骤推进，
    以及 LangGraph 风格的检查点（checkpoint）机制，
    支持状态快照与时间旅行回滚。

    使用 JSON 文件进行持久化存储。

    Attributes:
        _data_dir: 数据存储目录
        _workflows_dir: 工作流实例存储目录
        _checkpoints_dir: 检查点存储目录
    """

    def __init__(self, data_dir: str = None) -> None:
        """初始化状态管理器。

        Args:
            data_dir: 数据存储目录，为 None 则使用默认路径
        """
        if data_dir is None:
            data_dir = str(Path(__file__).resolve().parents[3] / "data" / "danchuang" / "workflows")

        self._data_dir = Path(data_dir)
        self._workflows_dir = self._data_dir / "instances"
        self._checkpoints_dir = self._data_dir / "checkpoints"

        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints_dir.mkdir(parents=True, exist_ok=True)

        logger.info("工作流状态管理器初始化完成，数据目录: %s", self._data_dir)

    def _workflow_path(self, workflow_id: str) -> Path:
        """获取工作流实例文件路径。

        Args:
            workflow_id: 工作流 ID

        Returns:
            文件路径
        """
        return self._workflows_dir / f"{workflow_id}.json"

    def _checkpoints_path(self, workflow_id: str) -> Path:
        """获取工作流的检查点索引文件路径。

        Args:
            workflow_id: 工作流 ID

        Returns:
            文件路径
        """
        return self._checkpoints_dir / f"{workflow_id}_index.json"

    def _checkpoint_data_path(self, checkpoint_id: str) -> Path:
        """获取检查点数据文件路径。

        Args:
            checkpoint_id: 检查点 ID

        Returns:
            文件路径
        """
        return self._checkpoints_dir / f"{checkpoint_id}.json"

    def create_workflow(
        self,
        template: PlaybookTemplate,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkflowInstance:
        """基于模板创建工作流实例。

        Args:
            template: Playbook 模板
            name: 工作流名称，为 None 则使用模板名称
            metadata: 附加元数据

        Returns:
            创建的工作流实例
        """
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        workflow_name = name or template.name

        step_states: Dict[str, StepStatus] = {
            step.step_id: StepStatus.PENDING
            for step in template.steps
        }

        workflow = WorkflowInstance(
            workflow_id=workflow_id,
            template_id=template.template_id,
            name=workflow_name,
            status=WorkflowStatus.NOT_STARTED,
            step_states=step_states,
            metadata=metadata or {},
        )

        self._save_workflow(workflow)
        logger.info("已创建工作流: %s (%s)", workflow_name, workflow_id)

        return workflow

    def _save_workflow(self, workflow: WorkflowInstance) -> None:
        """保存工作流实例到文件。

        Args:
            workflow: 工作流实例
        """
        workflow.updated_at = datetime.now()
        path = self._workflow_path(workflow.workflow_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(workflow.to_dict(), f, ensure_ascii=False, indent=2)

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowInstance]:
        """获取工作流实例详情。

        Args:
            workflow_id: 工作流 ID

        Returns:
            工作流实例，未找到返回 None
        """
        path = self._workflow_path(workflow_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return WorkflowInstance.from_dict(data)

    def list_workflows(
        self,
        status: Optional[WorkflowStatus] = None,
        template_id: Optional[str] = None,
    ) -> List[WorkflowInstance]:
        """列出工作流实例。

        Args:
            status: 按状态过滤，为 None 则不过滤
            template_id: 按模板 ID 过滤，为 None 则不过滤

        Returns:
            符合条件的工作流列表
        """
        workflows: List[WorkflowInstance] = []

        for file_path in self._workflows_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                wf = WorkflowInstance.from_dict(data)

                if status and wf.status != status:
                    continue
                if template_id and wf.template_id != template_id:
                    continue

                workflows.append(wf)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("跳过损坏的工作流文件 %s: %s", file_path.name, e)

        workflows.sort(key=lambda w: w.created_at, reverse=True)
        return workflows

    def start_step(self, workflow_id: str, step_id: str) -> WorkflowInstance:
        """开始执行某个步骤。

        Args:
            workflow_id: 工作流 ID
            step_id: 步骤 ID

        Returns:
            更新后的工作流实例

        Raises:
            ValueError: 工作流不存在或步骤 ID 无效
        """
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")

        if step_id not in workflow.step_states:
            raise ValueError(f"步骤不存在: {step_id}")

        if workflow.status == WorkflowStatus.NOT_STARTED:
            workflow.status = WorkflowStatus.IN_PROGRESS

        workflow.step_states[step_id] = StepStatus.IN_PROGRESS
        self._save_workflow(workflow)

        logger.info("工作流 %s 开始步骤 %s", workflow_id, step_id)
        return workflow

    def complete_step(
        self,
        workflow_id: str,
        step_id: str,
        success: bool = True,
        output: Optional[Dict[str, Any]] = None,
    ) -> WorkflowInstance:
        """完成某个步骤。

        Args:
            workflow_id: 工作流 ID
            step_id: 步骤 ID
            success: 是否成功完成
            output: 步骤输出数据

        Returns:
            更新后的工作流实例

        Raises:
            ValueError: 工作流不存在或步骤 ID 无效
        """
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")

        if step_id not in workflow.step_states:
            raise ValueError(f"步骤不存在: {step_id}")

        workflow.step_states[step_id] = StepStatus.COMPLETED if success else StepStatus.FAILED

        if output:
            if "step_outputs" not in workflow.metadata:
                workflow.metadata["step_outputs"] = {}
            workflow.metadata["step_outputs"][step_id] = output

        all_completed = all(
            s in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in workflow.step_states.values()
        )
        any_failed = any(s == StepStatus.FAILED for s in workflow.step_states.values())

        if all_completed:
            workflow.status = WorkflowStatus.COMPLETED
        elif any_failed:
            workflow.status = WorkflowStatus.FAILED

        self._save_workflow(workflow)

        logger.info(
            "工作流 %s 步骤 %s %s",
            workflow_id,
            step_id,
            "完成" if success else "失败",
        )
        return workflow

    def get_progress(self, workflow_id: str) -> Dict[str, Any]:
        """获取工作流进度。

        Args:
            workflow_id: 工作流 ID

        Returns:
            进度信息字典，包含：
            - total_steps: 总步骤数
            - completed_steps: 已完成步骤数
            - in_progress_steps: 进行中步骤数
            - pending_steps: 待执行步骤数
            - progress_percent: 进度百分比
            - status: 整体状态
            - step_details: 各步骤详情
        """
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")

        total = len(workflow.step_states)
        completed = sum(1 for s in workflow.step_states.values() if s == StepStatus.COMPLETED)
        in_progress = sum(1 for s in workflow.step_states.values() if s == StepStatus.IN_PROGRESS)
        pending = sum(1 for s in workflow.step_states.values() if s == StepStatus.PENDING)
        failed = sum(1 for s in workflow.step_states.values() if s == StepStatus.FAILED)
        skipped = sum(1 for s in workflow.step_states.values() if s == StepStatus.SKIPPED)

        progress_percent = (completed / total * 100) if total > 0 else 0.0

        return {
            "workflow_id": workflow_id,
            "name": workflow.name,
            "status": workflow.status.value,
            "total_steps": total,
            "completed_steps": completed,
            "in_progress_steps": in_progress,
            "pending_steps": pending,
            "failed_steps": failed,
            "skipped_steps": skipped,
            "progress_percent": round(progress_percent, 2),
            "step_details": {k: v.value for k, v in workflow.step_states.items()},
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
        }

    def create_checkpoint(
        self,
        workflow_id: str,
        step_id: str,
        description: str = "",
        extra_state: Optional[Dict[str, Any]] = None,
    ) -> WorkflowCheckpoint:
        """创建工作流检查点（状态快照）。

        LangGraph 风格的检查点机制，保存完整工作流状态，
        支持后续回滚到任意检查点。

        Args:
            workflow_id: 工作流 ID
            step_id: 当前步骤 ID
            description: 检查点描述
            extra_state: 附加状态数据

        Returns:
            创建的检查点

        Raises:
            ValueError: 工作流不存在
        """
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")

        checkpoint_id = f"cp_{uuid.uuid4().hex[:12]}"

        state_snapshot = {
            "workflow": workflow.to_dict(),
            "extra": extra_state or {},
        }

        checkpoint = WorkflowCheckpoint(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            step_id=step_id,
            state_snapshot=state_snapshot,
            description=description,
        )

        cp_path = self._checkpoint_data_path(checkpoint_id)
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)

        index_path = self._checkpoints_path(workflow_id)
        index_data: List[Dict[str, Any]] = []
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)

        index_data.append({
            "checkpoint_id": checkpoint_id,
            "step_id": step_id,
            "created_at": checkpoint.created_at.isoformat(),
            "description": description,
        })

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

        logger.info(
            "已创建检查点 %s (工作流 %s, 步骤 %s)",
            checkpoint_id,
            workflow_id,
            step_id,
        )
        return checkpoint

    def rollback_to_checkpoint(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> WorkflowInstance:
        """回滚工作流到指定检查点。

        将工作流状态恢复到检查点保存时的状态。

        Args:
            workflow_id: 工作流 ID
            checkpoint_id: 检查点 ID

        Returns:
            回滚后的工作流实例

        Raises:
            ValueError: 工作流或检查点不存在
        """
        cp_path = self._checkpoint_data_path(checkpoint_id)
        if not cp_path.exists():
            raise ValueError(f"检查点不存在: {checkpoint_id}")

        with open(cp_path, "r", encoding="utf-8") as f:
            cp_data = json.load(f)

        checkpoint = WorkflowCheckpoint.from_dict(cp_data)

        if checkpoint.workflow_id != workflow_id:
            raise ValueError(
                f"检查点 {checkpoint_id} 不属于工作流 {workflow_id}"
            )

        workflow_data = checkpoint.state_snapshot.get("workflow", {})
        if not workflow_data:
            raise ValueError(f"检查点 {checkpoint_id} 中无工作流状态数据")

        workflow = WorkflowInstance.from_dict(workflow_data)
        workflow.workflow_id = workflow_id
        workflow.updated_at = datetime.now()
        workflow.metadata["rolled_back_from"] = checkpoint_id
        workflow.metadata["rolled_back_at"] = datetime.now().isoformat()

        self._save_workflow(workflow)

        logger.info(
            "工作流 %s 已回滚到检查点 %s",
            workflow_id,
            checkpoint_id,
        )
        return workflow

    def list_checkpoints(self, workflow_id: str) -> List[Dict[str, Any]]:
        """列出工作流的所有检查点。

        Args:
            workflow_id: 工作流 ID

        Returns:
            检查点摘要列表（按时间倒序）
        """
        index_path = self._checkpoints_path(workflow_id)
        if not index_path.exists():
            return []

        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        index_data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return index_data

    def get_checkpoint(self, checkpoint_id: str) -> Optional[WorkflowCheckpoint]:
        """获取检查点详情。

        Args:
            checkpoint_id: 检查点 ID

        Returns:
            检查点实例，未找到返回 None
        """
        cp_path = self._checkpoint_data_path(checkpoint_id)
        if not cp_path.exists():
            return None

        with open(cp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return WorkflowCheckpoint.from_dict(data)


def _build_startup_mvp_template() -> PlaybookTemplate:
    """构建创业 MVP 模板（8步）。

    Returns:
        创业 MVP PlaybookTemplate
    """
    steps = [
        PlaybookStep(
            step_id="s1_idea_validation",
            name="创意验证与市场分析",
            description="对创业想法进行初步验证，分析市场机会与竞争格局",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="市场分析师",
            deliverables=[
                "市场需求分析报告",
                "竞品分析矩阵",
                "目标用户画像",
                "SWOT分析",
            ],
            dependencies=[],
            tools=["web.search", "web.fetch", "data.query"],
        ),
        PlaybookStep(
            step_id="s2_user_research",
            name="用户痛点调研",
            description="深度访谈目标用户，挖掘真实痛点与需求",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="用户研究员",
            deliverables=[
                "用户访谈记录",
                "痛点优先级矩阵",
                "用户旅程地图",
            ],
            dependencies=["s1_idea_validation"],
            tools=["web.search", "data.query"],
        ),
        PlaybookStep(
            step_id="s3_product_definition",
            name="产品定义与PRD",
            description="定义MVP功能范围，输出产品需求文档",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="产品经理",
            deliverables=[
                "产品愿景文档",
                "MVP功能清单",
                "产品需求文档(PRD)",
                "用户故事地图",
            ],
            dependencies=["s2_user_research"],
            tools=[],
        ),
        PlaybookStep(
            step_id="s4_ux_design",
            name="原型设计与交互",
            description="设计产品原型与交互流程",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="UX设计师",
            deliverables=[
                "信息架构图",
                "低保真原型",
                "交互设计说明",
                "高保真设计稿",
            ],
            dependencies=["s3_product_definition"],
            tools=["media.image"],
        ),
        PlaybookStep(
            step_id="s5_tech_architecture",
            name="技术选型与架构",
            description="进行技术选型，设计系统架构",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="技术架构师",
            deliverables=[
                "技术选型报告",
                "系统架构图",
                "数据库设计",
                "API接口设计",
            ],
            dependencies=["s4_ux_design"],
            tools=["code.understanding"],
        ),
        PlaybookStep(
            step_id="s6_mvp_dev",
            name="MVP开发实现",
            description="开发MVP核心功能，确保可运行演示",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="全栈工程师",
            deliverables=[
                "可运行的MVP代码库",
                "核心功能模块",
                "单元测试",
                "部署文档",
            ],
            dependencies=["s5_tech_architecture"],
            tools=["code.generate", "action.code_exec"],
        ),
        PlaybookStep(
            step_id="s7_test_validation",
            name="测试与用户验证",
            description="进行功能测试，并邀请种子用户验证",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="测试工程师",
            deliverables=[
                "测试用例",
                "Bug修复记录",
                "用户反馈报告",
                "MVP验证报告",
            ],
            dependencies=["s6_mvp_dev"],
            tools=["action.code_exec"],
        ),
        PlaybookStep(
            step_id="s8_launch_plan",
            name="上线筹备与发布",
            description="制定上线计划，准备市场发布材料",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="增长负责人",
            deliverables=[
                "上线计划时间表",
                "产品介绍文案",
                "宣发素材",
                "种子用户招募方案",
            ],
            dependencies=["s7_test_validation"],
            tools=["media.image", "content.produce"],
        ),
    ]

    return PlaybookTemplate(
        template_id="startup_mvp",
        name="创业MVP开发",
        description="从创意到MVP上线的8步标准化创业流程，覆盖市场验证、产品定义、开发测试全链路",
        industry="general",
        tags=["创业", "MVP", "产品开发", "从0到1", "精益创业"],
        steps=steps,
        estimated_duration=60,
    )


def _build_hardware_dev_template() -> PlaybookTemplate:
    """构建硬件开发模板（含护眼眼镜专属流程，10步）。

    Returns:
        硬件开发 PlaybookTemplate
    """
    steps = [
        PlaybookStep(
            step_id="h1_market_analysis",
            name="硬件市场调研",
            description="分析硬件市场趋势、竞品格局与用户需求",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="硬件市场分析师",
            deliverables=[
                "硬件市场趋势报告",
                "竞品拆解分析",
                "用户需求调研",
                "市场规模测算",
            ],
            dependencies=[],
            tools=["web.search", "web.fetch", "data.query"],
        ),
        PlaybookStep(
            step_id="h2_product_spec",
            name="产品规格定义",
            description="定义硬件产品功能规格、参数指标与护眼特性",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="硬件产品经理",
            deliverables=[
                "产品规格书",
                "功能需求清单",
                "护眼技术指标",
                "BOM成本估算",
            ],
            dependencies=["h1_market_analysis"],
            tools=[],
        ),
        PlaybookStep(
            step_id="h3_optical_design",
            name="光学与护眼设计",
            description="设计光学系统与护眼技术方案（防蓝光、防眩光、护眼模式）",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="光学工程师",
            deliverables=[
                "光学设计方案",
                "防蓝光技术方案",
                "光照传感器方案",
                "护眼模式算法",
            ],
            dependencies=["h2_product_spec"],
            tools=[],
        ),
        PlaybookStep(
            step_id="h4_hardware_arch",
            name="硬件架构设计",
            description="设计硬件电路架构、元器件选型与PCB方案",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="硬件工程师",
            deliverables=[
                "硬件架构图",
                "电路原理图",
                "元器件选型清单",
                "PCB设计方案",
            ],
            dependencies=["h3_optical_design"],
            tools=[],
        ),
        PlaybookStep(
            step_id="h5_firmware_design",
            name="固件与嵌入式开发",
            description="开发嵌入式固件、驱动程序与护眼算法实现",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="嵌入式工程师",
            deliverables=[
                "固件代码",
                "驱动程序",
                "护眼算法实现",
                "蓝牙/WiFi连接模块",
            ],
            dependencies=["h4_hardware_arch"],
            tools=["code.generate", "action.code_exec"],
        ),
        PlaybookStep(
            step_id="h6_app_design",
            name="配套APP设计开发",
            description="设计开发配套手机APP，实现数据同步与护眼设置",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="移动端开发工程师",
            deliverables=[
                "APP原型设计",
                "iOS/Android应用",
                "数据同步功能",
                "用眼数据统计",
            ],
            dependencies=["h5_firmware_design"],
            tools=["code.generate", "media.image"],
        ),
        PlaybookStep(
            step_id="h7_prototype_make",
            name="手板与原型制作",
            description="制作手板样机，进行外观与结构验证",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="结构工程师",
            deliverables=[
                "结构设计图",
                "3D打印手板",
                "外观验证报告",
                "装配工艺评估",
            ],
            dependencies=["h4_hardware_arch"],
            tools=[],
        ),
        PlaybookStep(
            step_id="h8_eye_care_test",
            name="护眼效果测试",
            description="进行护眼功能专业测试与认证",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="测试工程师",
            deliverables=[
                "防蓝光测试报告",
                "眩光测试数据",
                "频闪测试结果",
                "护眼效果评估",
            ],
            dependencies=["h7_prototype_make", "h5_firmware_design"],
            tools=["action.code_exec"],
        ),
        PlaybookStep(
            step_id="h9_certification",
            name="认证与合规",
            description="办理产品认证与合规手续（3C、CE、FCC等）",
            opc_role=OPCRole.FINANCE,
            assigned_role="合规专员",
            deliverables=[
                "认证计划",
                "检测报告",
                "3C认证",
                "合规文档",
            ],
            dependencies=["h8_eye_care_test"],
            tools=[],
        ),
        PlaybookStep(
            step_id="h10_manufacturing",
            name="量产准备与供应链",
            description="对接供应链，准备量产与品控",
            opc_role=OPCRole.FINANCE,
            assigned_role="供应链经理",
            deliverables=[
                "供应商选型",
                "量产计划",
                "品控标准",
                "供应链协议",
            ],
            dependencies=["h9_certification"],
            tools=["data.query"],
        ),
    ]

    return PlaybookTemplate(
        template_id="hardware_dev",
        name="硬件产品开发（护眼眼镜）",
        description="10步硬件产品开发流程，包含护眼眼镜专属光学设计与护眼效果验证环节",
        industry="hardware",
        tags=["硬件", "智能硬件", "护眼", "眼镜", "可穿戴", "量产"],
        steps=steps,
        estimated_duration=120,
    )


def _build_content_marketing_template() -> PlaybookTemplate:
    """构建内容营销模板（7步）。

    Returns:
        内容营销 PlaybookTemplate
    """
    steps = [
        PlaybookStep(
            step_id="c1_strategy",
            name="内容策略制定",
            description="制定内容营销策略、定位与目标",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="内容策略师",
            deliverables=[
                "内容营销战略",
                "目标受众画像",
                "内容定位与调性",
                "KPI指标体系",
            ],
            dependencies=[],
            tools=["data.query"],
        ),
        PlaybookStep(
            step_id="c2_audience_research",
            name="受众与竞品分析",
            description="深入分析目标受众、内容偏好与竞品内容策略",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="市场分析师",
            deliverables=[
                "受众画像报告",
                "内容偏好分析",
                "竞品内容分析",
                "内容机会点",
            ],
            dependencies=["c1_strategy"],
            tools=["web.search", "web.fetch", "data.query"],
        ),
        PlaybookStep(
            step_id="c3_content_planning",
            name="内容选题与规划",
            description="进行内容选题策划，制定内容日历",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="内容策划",
            deliverables=[
                "选题清单",
                "内容日历",
                "内容矩阵规划",
                "发布节奏表",
            ],
            dependencies=["c2_audience_research"],
            tools=["web.search"],
        ),
        PlaybookStep(
            step_id="c4_content_creation",
            name="内容创作生产",
            description="创作文章、视频、海报等各类内容",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="内容创作者",
            deliverables=[
                "文案稿件",
                "视频脚本",
                "海报设计稿",
                "内容素材库",
            ],
            dependencies=["c3_content_planning"],
            tools=["media.image", "media.video", "content.produce"],
        ),
        PlaybookStep(
            step_id="c5_content_optimization",
            name="内容优化打磨",
            description="对内容进行优化、SEO处理与审核",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="内容编辑",
            deliverables=[
                "优化后的内容",
                "SEO优化报告",
                "标题优化方案",
                "审核校对记录",
            ],
            dependencies=["c4_content_creation"],
            tools=["content.produce"],
        ),
        PlaybookStep(
            step_id="c6_distribution",
            name="多渠道分发",
            description="将内容分发到各平台，进行矩阵式发布",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="新媒体运营",
            deliverables=[
                "平台适配内容",
                "发布执行记录",
                "互动维护记录",
                "分发效果初报",
            ],
            dependencies=["c5_content_optimization"],
            tools=["media.image"],
        ),
        PlaybookStep(
            step_id="c7_analysis",
            name="数据分析与复盘",
            description="分析内容数据效果，总结经验优化策略",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="数据分析师",
            deliverables=[
                "数据周报/月报",
                "效果评估报告",
                "爆款内容分析",
                "策略优化建议",
            ],
            dependencies=["c6_distribution"],
            tools=["data.query"],
        ),
    ]

    return PlaybookTemplate(
        template_id="content_marketing",
        name="内容营销全流程",
        description="7步内容营销标准流程，从策略制定到数据复盘的完整内容运营闭环",
        industry="content",
        tags=["内容营销", "新媒体", "社媒运营", "内容创作", "增长"],
        steps=steps,
        estimated_duration=30,
    )


def _build_e_commerce_store_template() -> PlaybookTemplate:
    """构建电商开店模板（8步）。

    Returns:
        电商开店 PlaybookTemplate
    """
    steps = [
        PlaybookStep(
            step_id="e1_market_research",
            name="电商市场调研",
            description="调研电商平台、类目竞争与市场需求",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="电商分析师",
            deliverables=[
                "类目分析报告",
                "竞品店铺分析",
                "目标客群画像",
                "平台选择建议",
            ],
            dependencies=[],
            tools=["web.search", "web.fetch", "data.query"],
        ),
        PlaybookStep(
            step_id="e2_product_selection",
            name="选品与供应链",
            description="进行选品分析，对接供应商与供应链",
            opc_role=OPCRole.FINANCE,
            assigned_role="选品专员",
            deliverables=[
                "选品清单",
                "供应商名录",
                "成本核算表",
                "毛利测算",
            ],
            dependencies=["e1_market_research"],
            tools=["data.query"],
        ),
        PlaybookStep(
            step_id="e3_store_setup",
            name="店铺注册与搭建",
            description="注册电商平台店铺，完成基础设置",
            opc_role=OPCRole.PRODUCT_RD,
            assigned_role="电商运营",
            deliverables=[
                "店铺注册完成",
                "店铺基础设置",
                "支付物流配置",
                "客服体系搭建",
            ],
            dependencies=["e2_product_selection"],
            tools=[],
        ),
        PlaybookStep(
            step_id="e4_product_listing",
            name="商品上架与详情页",
            description="制作商品详情页，完成商品上架",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="电商美工",
            deliverables=[
                "商品主图设计",
                "详情页设计",
                "商品标题优化",
                "SKU设置",
            ],
            dependencies=["e3_store_setup"],
            tools=["media.image", "content.produce"],
        ),
        PlaybookStep(
            step_id="e5_visual_brand",
            name="店铺视觉与品牌",
            description="打造店铺整体视觉风格与品牌形象",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="品牌设计师",
            deliverables=[
                "店铺首页设计",
                "品牌视觉规范",
                "店招与logo",
                "营销素材模板",
            ],
            dependencies=["e4_product_listing"],
            tools=["media.image"],
        ),
        PlaybookStep(
            step_id="e6_traffic_strategy",
            name="流量策略与推广",
            description="制定引流策略，启动付费与自然流量",
            opc_role=OPCRole.CONTENT_MARKETING,
            assigned_role="投放优化师",
            deliverables=[
                "流量策略方案",
                "直通车/钻展设置",
                "SEO优化方案",
                "社媒引流计划",
            ],
            dependencies=["e5_visual_brand"],
            tools=["media.image", "data.query"],
        ),
        PlaybookStep(
            step_id="e7_operation_service",
            name="运营与客户服务",
            description="搭建客服体系，进行日常运营维护",
            opc_role=OPCRole.CUSTOMER_SERVICE,
            assigned_role="客服主管",
            deliverables=[
                "客服话术手册",
                "售后处理流程",
                "评价管理方案",
                "客户维护策略",
            ],
            dependencies=["e6_traffic_strategy"],
            tools=[],
        ),
        PlaybookStep(
            step_id="e8_data_optimization",
            name="数据复盘与优化",
            description="分析经营数据，持续优化运营策略",
            opc_role=OPCRole.FINANCE,
            assigned_role="数据分析师",
            deliverables=[
                "经营数据报表",
                "转化率分析",
                "ROI评估",
                "优化建议报告",
            ],
            dependencies=["e7_operation_service"],
            tools=["data.query"],
        ),
    ]

    return PlaybookTemplate(
        template_id="e_commerce_store",
        name="电商开店运营",
        description="8步电商开店全流程，从市场调研到数据优化的完整电商运营体系",
        industry="ecommerce",
        tags=["电商", "开店", "网店", "运营", "淘宝", "抖音电商"],
        steps=steps,
        estimated_duration=45,
    )


def _build_market_research_template() -> PlaybookTemplate:
    """构建市场调研模板（6步）。

    Returns:
        市场调研 PlaybookTemplate
    """
    steps = [
        PlaybookStep(
            step_id="m1_research_design",
            name="调研方案设计",
            description="明确调研目标、范围与方法论",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="研究主管",
            deliverables=[
                "调研计划书",
                "调研目标与范围",
                "方法论选择",
                "时间与预算规划",
            ],
            dependencies=[],
            tools=[],
        ),
        PlaybookStep(
            step_id="m2_secondary_research",
            name="案头研究与二手数据",
            description="收集行业报告、公开数据与已有研究",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="信息研究员",
            deliverables=[
                "行业报告汇总",
                "市场规模数据",
                "政策法规梳理",
                "技术趋势分析",
            ],
            dependencies=["m1_research_design"],
            tools=["web.search", "web.fetch", "data.query"],
        ),
        PlaybookStep(
            step_id="m3_competitor_analysis",
            name="竞品深度分析",
            description="对主要竞品进行系统性分析研究",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="竞品分析师",
            deliverables=[
                "竞品画像清单",
                "功能对比矩阵",
                "定价策略分析",
                "优劣势分析",
            ],
            dependencies=["m2_secondary_research"],
            tools=["web.search", "web.fetch", "web.crawl"],
        ),
        PlaybookStep(
            step_id="m4_user_research",
            name="用户调研与访谈",
            description="开展用户访谈、问卷与行为研究",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="用户研究员",
            deliverables=[
                "用户访谈记录",
                "问卷调研数据",
                "用户画像报告",
                "需求优先级排序",
            ],
            dependencies=["m3_competitor_analysis"],
            tools=["data.query"],
        ),
        PlaybookStep(
            step_id="m5_data_analysis",
            name="数据分析与洞察",
            description="整合分析所有数据，提炼核心洞察",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="数据分析师",
            deliverables=[
                "数据统计分析",
                "交叉分析报告",
                "核心洞察提炼",
                "机会点识别",
            ],
            dependencies=["m4_user_research"],
            tools=["data.query", "action.code_exec"],
        ),
        PlaybookStep(
            step_id="m6_report_recommendation",
            name="报告输出与建议",
            description="撰写最终调研报告，给出策略建议",
            opc_role=OPCRole.MARKET_RESEARCH,
            assigned_role="研究主管",
            deliverables=[
                "最终调研报告",
                "策略建议清单",
                "行动路线图",
                "风险提示",
            ],
            dependencies=["m5_data_analysis"],
            tools=["content.produce"],
        ),
    ]

    return PlaybookTemplate(
        template_id="market_research",
        name="市场调研全流程",
        description="6步专业市场调研流程，从方案设计到报告输出的完整研究体系",
        industry="general",
        tags=["市场调研", "用户研究", "竞品分析", "数据分析", "商业分析"],
        steps=steps,
        estimated_duration=21,
    )
