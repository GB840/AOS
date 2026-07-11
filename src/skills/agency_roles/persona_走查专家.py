"""
🎭 Persona 走查专家 - 从设定好的 persona（用户画像）心理视角出发，对网页进行认知走查的模拟——捕捉每个滚动位置上的情绪反应与理性思考，再输出植根于 LIFT、Cialdini、Fogg 框架的结构化 CRO 报告

自动转换自 agency-agents-zh/design/design-persona-walkthrough.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Persona走查专家Skill(Skill):
    NAME = "persona_走查专家"
    DESCRIPTION = "从设定好的 persona（用户画像）心理视角出发，对网页进行认知走查的模拟——捕捉每个滚动位置上的情绪反应与理性思考，再输出植根于 LIFT、Cialdini、Fogg 框架的结构化 CRO 报告"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "design"
    TAGS = ["design", "consulting", "expert"]
    CAPABILITIES = ["design", "ui_ux", "creative"]
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
                return {"success": True, "skill": "persona_走查专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "persona_走查专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "persona_走查专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Persona 走查专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "persona_走查专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎭【Persona 走查专家】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)