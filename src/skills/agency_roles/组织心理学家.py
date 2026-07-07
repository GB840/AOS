"""
🧠 组织心理学家 - 应用型组织心理学家，诊断团队动力、psychological safety（心理安全感）、burnout（职业倦怠）风险与文化健康度——用循证框架帮助领导者打造高绩效、有韧性、心理安全的组织。

自动转换自 agency-agents-zh/specialized/organizational-psychologist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 组织心理学家Skill(Skill):
    NAME = "组织心理学家"
    DESCRIPTION = "应用型组织心理学家，诊断团队动力、psychological safety（心理安全感）、burnout（职业倦怠）风险与文化健康度——用循证框架帮助领导者打造高绩效、有韧性、心理安全的组织。"
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
                return {"success": True, "skill": "组织心理学家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "组织心理学家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "组织心理学家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("组织心理学家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "组织心理学家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🧠【组织心理学家】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)