"""
🧠 Contributing - 

自动转换自 agency-agents-zh/agency-agents-zh/CONTRIBUTING.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class ContributingSkill(Skill):
    NAME = "contributing"
    DESCRIPTION = ""
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "agency-agents-zh"
    TAGS = ["agency-agents-zh", "consulting", "expert"]
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
                return {"success": True, "skill": "contributing", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "contributing", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "contributing", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Contributing 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "contributing", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🧠【Contributing】。\n\n## 身份与记忆\n- **角色**：具体角色\n- **个性**：性格特点\n- **记忆**：记住什么\n- **经验**：擅长什么\n\n## 核心使命\n具体职责和工作内容。\n\n## 必须遵守的规则\n- 做事的原则和红线。\n\n## 工作流程\n分步骤的工作流。\n\n## 沟通风格\n说话的方式和语气示例。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)