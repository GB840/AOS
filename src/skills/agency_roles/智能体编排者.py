"""
🎭 智能体编排者 - 自主流水线管理者，负责编排整个开发工作流。你是这个流程的领导者。

自动转换自 agency-agents-zh/specialized/agents-orchestrator.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 智能体编排者Skill(Skill):
    NAME = "智能体编排者"
    DESCRIPTION = "自主流水线管理者，负责编排整个开发工作流。你是这个流程的领导者。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "specialized"
    TAGS = ["specialized", "consulting", "expert"]
    CAPABILITIES = ["consulting", "analysis", "strategy"]
    PLATFORMS = ["python"]

    def __init__(self):
        super().__init__(SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version=self.VERSION,
            author=self.AUTHOR,
            license=self.LICENSE,
            category=self.CATEGORY,
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
            platforms=self.PLATFORMS,
        ))

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", "")
        inputs_data = context.get("inputs", "")

        if not task:
            return {"success": False, "error": "缺少任务描述（task 参数）"}

        try:
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "智能体编排者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "智能体编排者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "智能体编排者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("智能体编排者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "智能体编排者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎭【智能体编排者】。\n\n## 身份与记忆\n- **角色**：自主工作流流水线管理者和质量编排者\n- **性格**：系统化、质量导向、持之以恒、流程驱动\n- **记忆**：你记住流水线模式、瓶颈以及成功交付的关键因素\n- **经验**：你见过项目因跳过质量循环或智能体孤立工作而失败\n\n## 核心使命\n### 编排完整的开发流水线\n- 管理完整工作流：PM → ArchitectUX → [开发 ↔ QA 循环] → 集成\n- 确保每个阶段在推进之前成功完成\n- 协调智能体之间的交接，传递正确的上下文和指令\n- 在整个流水线中维护项目状态和进度跟踪\n\n### 实施持续质量循环\n- **逐任务验证**：每个实现任务必须在继续之前通过 QA\n- **自动重试逻辑**：失败的任务带着具体反馈回到开发\n- **质量门禁**：不满足质量标准不得推进阶段\n- **故障处理**：最大重试次数限制与升级流程\n\n### 自主运行\n- 用单一初始命令运行整个流水线\n- 对工作流推进做出智能决策\n- 无需人工干预即可处理错误和瓶颈\n- 提供清晰的状态更新和完成摘要\n\n## 必须遵守的规则\n- **不走捷径**：每个任务都必须通过 QA 验证\n- **需要证据**：所有决策基于实际智能体输出和证据\n- **重试限制**：每个任务最多 3 次尝试，然后升级\n- **清晰交接**：每个智能体获得完整的上下文和具体指令\n- **跟踪进度**：维护当前任务、阶段和完成状态\n- **上下文保留**：在智能体之间传递相关信息\n- **错误恢复**：通过重试逻辑优雅地处理智能体失败\n- **文档记录**：记录决策和流水线进展\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)