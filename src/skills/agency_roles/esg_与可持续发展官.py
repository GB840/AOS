"""
🌱 ESG 与可持续发展官 - 企业可持续发展战略专家与 ESG 信息披露专员，负责搭建 environmental、social、governance（环境、社会、治理）项目，管理信息披露，推动 decarbonization（脱碳）行动，并使业务战略与利益相关方及监管预期保持一致。

自动转换自 agency-agents-zh/specialized/esg-sustainability-officer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Esg与可持续发展官Skill(Skill):
    NAME = "esg_与可持续发展官"
    DESCRIPTION = "企业可持续发展战略专家与 ESG 信息披露专员，负责搭建 environmental、social、governance（环境、社会、治理）项目，管理信息披露，推动 decarbonization（脱碳）行动，并使业务战略与利益相关方及监管预期保持一致。"
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
                return {"success": True, "skill": "esg_与可持续发展官", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "esg_与可持续发展官", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "esg_与可持续发展官", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("ESG 与可持续发展官 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "esg_与可持续发展官", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🌱【ESG 与可持续发展官】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)