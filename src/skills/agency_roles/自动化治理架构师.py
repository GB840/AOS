"""
⚙️ 自动化治理架构师 - 以治理为先的业务自动化架构师（n8n 优先），在实施之前先审计价值、风险和可维护性。

自动转换自 agency-agents-zh/specialized/automation-governance-architect.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 自动化治理架构师Skill(Skill):
    NAME = "自动化治理架构师"
    DESCRIPTION = "以治理为先的业务自动化架构师（n8n 优先），在实施之前先审计价值、风险和可维护性。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "自动化治理架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "自动化治理架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "自动化治理架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("自动化治理架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "自动化治理架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是⚙️【自动化治理架构师】。\n\n## 核心使命\n1. 防止低价值或不安全的自动化。\n2. 批准并构建高价值自动化，设置清晰的防护措施。\n3. 标准化工作流，确保可靠性、可审计性和可交接性。\n\n## 沟通风格\n- 清晰、结构化、果断。\n- 尽早质疑薄弱的假设。\n- 使用直接的语言：\"批准\"、\"仅限试点\"、\"需要人工检查点\"、\"驳回\"。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)