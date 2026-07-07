"""
🛸 无人机实景测绘专家 - 摄影测量与实景采集专家，把无人机影像处理成 orthomosaic（正射影像）、数字地形模型、point cloud（点云）和三维网格——打通现场采集与 GIS 可用成果之间的链路。

自动转换自 agency-agents-zh/gis/gis-drone-reality-mapping.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 无人机实景测绘专家Skill(Skill):
    NAME = "无人机实景测绘专家"
    DESCRIPTION = "摄影测量与实景采集专家，把无人机影像处理成 orthomosaic（正射影像）、数字地形模型、point cloud（点云）和三维网格——打通现场采集与 GIS 可用成果之间的链路。"
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
                return {"success": True, "skill": "无人机实景测绘专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "无人机实景测绘专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "无人机实景测绘专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("无人机实景测绘专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "无人机实景测绘专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛸【无人机实景测绘专家】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)