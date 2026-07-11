"""
🏗️ BIM/GIS 专家 - 整合专家，打通 BIM（建筑信息模型）与 GIS（地理信息系统）——负责 Revit/IFC 数据转换、室内地图、数字孪生架构与设施管理数据模型。

自动转换自 agency-agents-zh/gis/gis-bim-specialist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Bimgis专家Skill(Skill):
    NAME = "bimgis_专家"
    DESCRIPTION = "整合专家，打通 BIM（建筑信息模型）与 GIS（地理信息系统）——负责 Revit/IFC 数据转换、室内地图、数字孪生架构与设施管理数据模型。"
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
                return {"success": True, "skill": "bimgis_专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "bimgis_专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "bimgis_专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("BIM/GIS 专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "bimgis_专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏗️【BIM/GIS 专家】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)