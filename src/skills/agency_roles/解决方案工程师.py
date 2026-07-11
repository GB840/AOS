"""
🔧 解决方案工程师 - 亲力亲为的 GIS 原型搭建者，接过技术顾问的策略，将其落地为可运行的演示、概念验证（PoC）和技术验证，覆盖完整的 Esri 与开源技术栈。

自动转换自 agency-agents-zh/gis/gis-solution-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 解决方案工程师Skill(Skill):
    NAME = "解决方案工程师"
    DESCRIPTION = "亲力亲为的 GIS 原型搭建者，接过技术顾问的策略，将其落地为可运行的演示、概念验证（PoC）和技术验证，覆盖完整的 Esri 与开源技术栈。"
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
                return {"success": True, "skill": "解决方案工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "解决方案工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "解决方案工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("解决方案工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "解决方案工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔧【解决方案工程师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)