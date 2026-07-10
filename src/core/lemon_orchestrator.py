"""
LEMON 学习型编排器 - 自动生成可执行编排说明书

核心职责:
1. 根据任务和角色白名单，自动生成编排说明书
2. 定义角色分工、能力要求、依赖关系
3. 生成可执行的工作流定义
4. 支持学习和复用历史编排方案

设计参考: LEMON Learning-based Orchestration
- 自动生成可执行编排说明书
- 不用每次手动写工单流程
"""

import logging
import json
from typing import Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationStep:
    step_id: str
    role: str
    task: str
    inputs: List[str]
    outputs: List[str]
    dependencies: List[str] = None
    model_tier: str = "medium"
    estimated_time: str = ""
    human_in_the_loop: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "role": self.role,
            "task": self.task,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "dependencies": self.dependencies or [],
            "model_tier": self.model_tier,
            "estimated_time": self.estimated_time,
            "human_in_the_loop": self.human_in_the_loop,
        }


@dataclass
class OrchestrationSpec:
    task_id: str
    task_description: str
    roles: List[str]
    steps: List[OrchestrationStep]
    parallel_groups: List[List[str]] = None
    milestones: List[Dict[str, Any]] = None
    quality_checks: List[str] = None
    budget: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "roles": self.roles,
            "steps": [s.to_dict() for s in self.steps],
            "parallel_groups": self.parallel_groups or [],
            "milestones": self.milestones or [],
            "quality_checks": self.quality_checks or [],
            "budget": self.budget or {},
        }


ORCHESTRATION_PROMPT = """
你是一个专业的工作流编排师，请为以下任务生成详细的编排说明书：

任务描述: {task}

可用角色: {roles}

请输出一个结构化的编排方案，包含：
1. 角色分工 — 每个角色负责什么工作
2. 步骤顺序 — 工作流程的先后顺序
3. 依赖关系 — 哪些步骤依赖其他步骤的输出
4. 输出交付物 — 每个步骤的产出是什么
5. 并行/串行 — 哪些步骤可以并行执行

输出格式（JSON）：
{{
  "roles": ["角色1", "角色2"],
  "steps": [
    {{
      "step_id": "step_1",
      "role": "角色1",
      "task": "该步骤的具体任务",
      "inputs": ["输入数据1", "输入数据2"],
      "outputs": ["输出交付物1"],
      "dependencies": [],
      "model_tier": "high/medium/low",
      "human_in_the_loop": false
    }}
  ],
  "parallel_groups": [["step_2", "step_3"]],
  "milestones": [{{"name": "里程碑1", "steps": ["step_1"]}}],
  "quality_checks": ["检查项1", "检查项2"]
}}
"""


class LEMONOrchestrator:
    """LEMON 学习型编排器 — 自动生成编排说明书"""

    def __init__(self, brain=None):
        self.brain = brain
        self._history = []

    def generate_spec(self, task: str, role_whitelist: List[str], task_id: str = "") -> OrchestrationSpec:
        """生成编排说明书"""
        task_id = task_id or str(hash(task))[:16]

        prompt = ORCHESTRATION_PROMPT.format(
            task=task,
            roles=", ".join(role_whitelist),
        )

        try:
            if self.brain:
                result = self.brain.chat(prompt, session_id=f"orchestration_{task_id}")
                response = result.get("response", "")
                spec_data = self._parse_spec(response)
            else:
                spec_data = self._generate_fallback_spec(task, role_whitelist)

            spec = self._build_spec(task_id, task, role_whitelist, spec_data)
            self._history.append(spec)

            logger.info(f"LEMON编排说明书生成完成: {task_id}")
            return spec

        except Exception as e:
            logger.warning(f"LEMON编排失败，使用降级方案: {e}")
            spec_data = self._generate_fallback_spec(task, role_whitelist)
            return self._build_spec(task_id, task, role_whitelist, spec_data)

    def _parse_spec(self, response: str) -> Dict[str, Any]:
        """解析编排说明书"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                data = json.loads(response)
            return data
        except (json.JSONDecodeError, ValueError):
            return {}

    def _generate_fallback_spec(self, task: str, roles: List[str]) -> Dict[str, Any]:
        """降级方案 - 生成简单的顺序编排"""
        steps = []
        for i, role in enumerate(roles):
            step_id = f"step_{i + 1}"
            steps.append({
                "step_id": step_id,
                "role": role,
                "task": f"{role}执行其专业任务",
                "inputs": ["任务描述"],
                "outputs": [f"{role}产出"],
                "dependencies": [f"step_{i}"] if i > 0 else [],
                "model_tier": "medium",
                "human_in_the_loop": False,
            })

        return {
            "roles": roles,
            "steps": steps,
            "parallel_groups": [],
            "milestones": [{"name": "完成", "steps": [s["step_id"] for s in steps]}],
            "quality_checks": ["检查产出质量"],
        }

    def _build_spec(self, task_id: str, task: str, roles: List[str], data: Dict[str, Any]) -> OrchestrationSpec:
        """构建编排说明书对象"""
        steps = []
        for step_data in data.get("steps", []):
            step = OrchestrationStep(
                step_id=step_data.get("step_id", ""),
                role=step_data.get("role", ""),
                task=step_data.get("task", ""),
                inputs=step_data.get("inputs", []),
                outputs=step_data.get("outputs", []),
                dependencies=step_data.get("dependencies", []),
                model_tier=step_data.get("model_tier", "medium"),
                human_in_the_loop=step_data.get("human_in_the_loop", False),
            )
            steps.append(step)

        return OrchestrationSpec(
            task_id=task_id,
            task_description=task,
            roles=roles,
            steps=steps,
            parallel_groups=data.get("parallel_groups", []),
            milestones=data.get("milestones", []),
            quality_checks=data.get("quality_checks", []),
        )

    def validate_spec(self, spec: OrchestrationSpec) -> Dict[str, Any]:
        """验证编排说明书的有效性"""
        errors = []
        warnings = []

        if not spec.steps:
            errors.append("没有定义任何步骤")

        step_ids = [s.step_id for s in spec.steps]
        for step in spec.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    errors.append(f"步骤 {step.step_id} 依赖不存在的步骤 {dep}")

        if len(set(step_ids)) != len(step_ids):
            errors.append("存在重复的步骤ID")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "step_count": len(spec.steps),
            "role_count": len(spec.roles),
        }

    def optimize_spec(self, spec: OrchestrationSpec) -> OrchestrationSpec:
        """优化编排方案 - 识别可并行化的步骤"""
        parallel_groups = []
        processed = set()

        for i, step in enumerate(spec.steps):
            if step.step_id in processed:
                continue

            group = [step.step_id]
            processed.add(step.step_id)

            for j in range(i + 1, len(spec.steps)):
                other_step = spec.steps[j]
                if other_step.step_id in processed:
                    continue

                has_dependency = False
                for dep in other_step.dependencies:
                    if dep in group:
                        has_dependency = True
                        break

                if not has_dependency:
                    group.append(other_step.step_id)
                    processed.add(other_step.step_id)

            if len(group) > 1:
                parallel_groups.append(group)

        spec.parallel_groups = parallel_groups
        return spec

    def export_spec(self, spec: OrchestrationSpec, filepath: str) -> bool:
        """导出编排说明书到文件"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(spec.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"编排说明书已导出: {filepath}")
            return True
        except Exception as e:
            logger.error(f"导出失败: {e}")
            return False

    def get_history(self, limit: int = 10) -> List[OrchestrationSpec]:
        """获取历史编排方案"""
        return self._history[-limit:]
