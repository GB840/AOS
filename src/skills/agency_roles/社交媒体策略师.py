"""
📱 社交媒体策略师 - 跨平台社交媒体策略专家，专注 LinkedIn、Twitter 等职业社交平台的品牌建设、社区运营和整合营销。

自动转换自 agency-agents-zh/marketing/marketing-social-media-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 社交媒体策略师Skill(Skill):
    NAME = "社交媒体策略师"
    DESCRIPTION = "跨平台社交媒体策略专家，专注 LinkedIn、Twitter 等职业社交平台的品牌建设、社区运营和整合营销。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "marketing"
    TAGS = ["marketing", "consulting", "expert"]
    CAPABILITIES = ["marketing_strategy", "content_creation", "campaign_management"]
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
                return {"success": True, "skill": "社交媒体策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "社交媒体策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "社交媒体策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("社交媒体策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "社交媒体策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📱【社交媒体策略师】。\n\n## 沟通风格\n- **策略性**：建议有数据支撑，符合平台最佳实践\n- **适应性**：不同平台用不同的语气和风格\n- **专业性**：建立专家权威的表达方式\n- **协作性**：和各平台专项智能体无缝配合\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)