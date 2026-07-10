"""
SwarmFlow 可控工作流编排 - 蜂群协作执行引擎

核心职责:
1. 根据编排说明书执行工作流
2. 管理角色间的协作和数据传递
3. 支持人机交互节点(Human-in-the-loop)
4. 收集各角色产出并汇总项目包

设计参考:
- SwarmFlow: 可控工作流编排
- JiuwenSwarm: 蜂群协作
- Agent自主分工、动态协商、高效协作
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from core.lemon_orchestrator import OrchestrationSpec, OrchestrationStep

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    step_id: str
    role: str
    status: StepStatus
    output: Any = None
    error: str = ""
    duration: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "role": self.role,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration": self.duration,
            "timestamp": self.timestamp,
        }


@dataclass
class WorkflowResult:
    workflow_id: str
    status: ExecutionStatus
    task_description: str
    role_whitelist: List[str]
    step_results: List[StepResult]
    final_output: Any = None
    summary: str = ""
    total_duration: float = 0.0
    cost_estimate: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "task_description": self.task_description,
            "role_whitelist": self.role_whitelist,
            "step_results": [s.to_dict() for s in self.step_results],
            "final_output": self.final_output,
            "summary": self.summary,
            "total_duration": self.total_duration,
            "cost_estimate": self.cost_estimate,
        }


class SwarmFlow:
    """SwarmFlow 可控工作流编排引擎"""

    def __init__(self, skill_registry, brain=None):
        self.skill_registry = skill_registry
        self.brain = brain
        self._running_workflows: Dict[str, Dict[str, Any]] = {}

    def execute_workflow(self, spec: "OrchestrationSpec", 
                         on_step_start=None, on_step_complete=None,
                         human_callback=None) -> WorkflowResult:
        """执行工作流"""
        workflow_id = spec.task_id or str(uuid.uuid4())
        self._running_workflows[workflow_id] = {
            "status": ExecutionStatus.RUNNING,
            "spec": spec,
            "results": {},
        }

        step_results = []
        step_outputs: Dict[str, Any] = {}

        logger.info(f"开始执行工作流: {workflow_id}")

        for step in spec.steps:
            if self._running_workflows.get(workflow_id, {}).get("status") == ExecutionStatus.CANCELLED:
                break

            if on_step_start:
                on_step_start(step)

            if step.human_in_the_loop and human_callback:
                logger.info(f"步骤 {step.step_id} 需要人工干预")
                human_input = human_callback(step)
                if human_input is None:
                    step_results.append(StepResult(
                        step_id=step.step_id,
                        role=step.role,
                        status=StepStatus.FAILED,
                        error="人工干预未提供输入",
                    ))
                    continue

            result = self._execute_step(step, step_outputs)
            step_results.append(result)
            step_outputs[step.step_id] = result.output

            if on_step_complete:
                on_step_complete(step, result)

            if result.status == StepStatus.FAILED:
                logger.error(f"步骤 {step.step_id} 失败: {result.error}")
                break

        final_output = self._aggregate_results(step_results, spec)
        summary = self._generate_summary(step_results, spec)

        status = ExecutionStatus.COMPLETED
        if any(r.status == StepStatus.FAILED for r in step_results):
            status = ExecutionStatus.FAILED

        self._running_workflows[workflow_id]["status"] = status

        workflow_result = WorkflowResult(
            workflow_id=workflow_id,
            status=status,
            task_description=spec.task_description,
            role_whitelist=spec.roles,
            step_results=step_results,
            final_output=final_output,
            summary=summary,
            cost_estimate=None,
        )

        logger.info(f"工作流执行完成: {workflow_id} - {status.value}")
        return workflow_result

    def _execute_step(self, step: "OrchestrationStep", step_outputs: Dict[str, Any]) -> StepResult:
        """执行单个步骤"""
        from datetime import datetime
        start_time = datetime.now()

        try:
            inputs = []
            for dep in step.dependencies:
                if dep in step_outputs:
                    inputs.append(step_outputs[dep])

            context = {
                "task": step.task,
                "inputs": inputs,
                "step_id": step.step_id,
                "role": step.role,
                "model_tier": step.model_tier,
            }

            result = self.skill_registry.execute(step.role, context)

            if result.get("success"):
                duration = (datetime.now() - start_time).total_seconds()
                return StepResult(
                    step_id=step.step_id,
                    role=step.role,
                    status=StepStatus.COMPLETED,
                    output=result.get("data", {}).get("response", result.get("data")),
                    duration=duration,
                    timestamp=datetime.now().isoformat(),
                )
            else:
                duration = (datetime.now() - start_time).total_seconds()
                return StepResult(
                    step_id=step.step_id,
                    role=step.role,
                    status=StepStatus.FAILED,
                    error=result.get("error", "执行失败"),
                    duration=duration,
                    timestamp=datetime.now().isoformat(),
                )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.warning("Step %s (role=%s) raised exception: %s", step.step_id, step.role, e)
            return StepResult(
                step_id=step.step_id,
                role=step.role,
                status=StepStatus.FAILED,
                error=str(e),
                duration=duration,
                timestamp=datetime.now().isoformat(),
            )

    def _aggregate_results(self, step_results: List[StepResult], 
                           spec: "OrchestrationSpec") -> Dict[str, Any]:
        """汇总所有步骤的产出"""
        outputs = {}
        for result in step_results:
            if result.status == StepStatus.COMPLETED and result.output:
                outputs[result.step_id] = result.output

        aggregated = {
            "task": spec.task_description,
            "roles": spec.roles,
            "steps": outputs,
            "summary": self._generate_summary(step_results, spec),
        }

        return aggregated

    def _generate_summary(self, step_results: List[StepResult], 
                          spec: "OrchestrationSpec") -> str:
        """生成工作流执行摘要"""
        completed = sum(1 for r in step_results if r.status == StepStatus.COMPLETED)
        failed = sum(1 for r in step_results if r.status == StepStatus.FAILED)
        total = len(step_results)

        summary = f"工作流执行完成: {completed}/{total} 步骤成功"
        if failed > 0:
            summary += f", {failed} 步骤失败"

        summary += f"\n任务: {spec.task_description}"
        summary += f"\n参与角色: {', '.join(spec.roles)}"

        return summary

    def execute_parallel(self, spec: "OrchestrationSpec") -> WorkflowResult:
        """执行支持并行步骤的工作流"""
        if not spec.parallel_groups:
            return self.execute_workflow(spec)

        workflow_id = spec.task_id or str(uuid.uuid4())
        step_results = []
        step_outputs: Dict[str, Any] = {}

        for group in spec.parallel_groups:
            group_results = []
            for step_id in group:
                step = next((s for s in spec.steps if s.step_id == step_id), None)
                if step:
                    result = self._execute_step(step, step_outputs)
                    group_results.append(result)
                    step_outputs[step_id] = result.output
            step_results.extend(group_results)

        for step in spec.steps:
            if step.step_id not in step_outputs:
                result = self._execute_step(step, step_outputs)
                step_results.append(result)
                step_outputs[step.step_id] = result.output

        final_output = self._aggregate_results(step_results, spec)
        summary = self._generate_summary(step_results, spec)

        status = ExecutionStatus.COMPLETED
        if any(r.status == StepStatus.FAILED for r in step_results):
            status = ExecutionStatus.FAILED

        return WorkflowResult(
            workflow_id=workflow_id,
            status=status,
            task_description=spec.task_description,
            role_whitelist=spec.roles,
            step_results=step_results,
            final_output=final_output,
            summary=summary,
        )

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流状态"""
        return self._running_workflows.get(workflow_id)

    def cancel_workflow(self, workflow_id: str) -> bool:
        """取消工作流"""
        if workflow_id in self._running_workflows:
            self._running_workflows[workflow_id]["status"] = ExecutionStatus.CANCELLED
            return True
        return False

    def list_workflows(self) -> List[Dict[str, Any]]:
        """列出所有运行中的工作流"""
        return [{"workflow_id": k, "status": v["status"].value} for k, v in self._running_workflows.items()]
