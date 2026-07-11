"""
🧠 技术顾问 - 战略型 GIS 顾问，把业务问题转化为地理空间解决方案——做差距分析、技术路线图、RFP 应答，以及横跨 Esri 与开源生态的数字化转型战略。

自动转换自 agency-agents-zh/gis/gis-technical-consultant.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 技术顾问Skill(Skill):
    NAME = "技术顾问"
    DESCRIPTION = "战略型 GIS 顾问，把业务问题转化为地理空间解决方案——做差距分析、技术路线图、RFP 应答，以及横跨 Esri 与开源生态的数字化转型战略。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "gis"
    TAGS = ["gis", "consulting", "expert"]
    CAPABILITIES = ["geospatial_analysis", "map_development", "location_intelligence"]
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
                return {"success": True, "skill": "技术顾问", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "技术顾问", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "技术顾问", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("技术顾问 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "技术顾问", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🧠【技术顾问】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)