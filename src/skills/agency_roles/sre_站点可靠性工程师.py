"""
🛠️ SRE (站点可靠性工程师) - 站点可靠性工程专家，精通 SLO、错误预算、可观测性、混沌工程和减少重复劳动，守护大规模生产系统的稳定性。

自动转换自 agency-agents-zh/engineering/engineering-sre.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Sre站点可靠性工程师Skill(Skill):
    NAME = "sre_站点可靠性工程师"
    DESCRIPTION = "站点可靠性工程专家，精通 SLO、错误预算、可观测性、混沌工程和减少重复劳动，守护大规模生产系统的稳定性。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
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
                return {"success": True, "skill": "sre_站点可靠性工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "sre_站点可靠性工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "sre_站点可靠性工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("SRE (站点可靠性工程师) 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "sre_站点可靠性工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛠️【SRE (站点可靠性工程师)】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)