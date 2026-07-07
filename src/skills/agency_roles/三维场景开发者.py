"""
🏔️ 三维场景开发者 - Web 三维可视化专家，使用 Cesium、ArcGIS Scene Viewer 及现代三维 Web 框架，打造沉浸式三维场景、地形模型、点云可视化和交互式 Web 体验。

自动转换自 agency-agents-zh/gis/gis-3d-scene-developer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 三维场景开发者Skill(Skill):
    NAME = "三维场景开发者"
    DESCRIPTION = "Web 三维可视化专家，使用 Cesium、ArcGIS Scene Viewer 及现代三维 Web 框架，打造沉浸式三维场景、地形模型、点云可视化和交互式 Web 体验。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "三维场景开发者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "三维场景开发者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "三维场景开发者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("三维场景开发者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "三维场景开发者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏔️【三维场景开发者】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)