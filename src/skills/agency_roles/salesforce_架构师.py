"""
☁️ Salesforce 架构师 - Salesforce 平台的解决方案架构——多云设计、集成模式、Governor Limits、部署策略和数据模型治理，适用于企业级组织

自动转换自 agency-agents-zh/specialized/specialized-salesforce-architect.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Salesforce架构师Skill(Skill):
    NAME = "salesforce_架构师"
    DESCRIPTION = "Salesforce 平台的解决方案架构——多云设计、集成模式、Governor Limits、部署策略和数据模型治理，适用于企业级组织"
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
                return {"success": True, "skill": "salesforce_架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "salesforce_架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "salesforce_架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Salesforce 架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "salesforce_架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是☁️【Salesforce 架构师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)