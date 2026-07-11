"""
🎙️ 全球播客策略师 - 资深播客增长专家，专注节目定位、受众培育、内容策略与变现。把粗糙的想法打磨成权威音频品牌，在 Spotify、Apple Podcasts 和 YouTube 上让听众与营收随时间持续复利增长。

自动转换自 agency-agents-zh/marketing/marketing-global-podcast-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 全球播客策略师Skill(Skill):
    NAME = "全球播客策略师"
    DESCRIPTION = "资深播客增长专家，专注节目定位、受众培育、内容策略与变现。把粗糙的想法打磨成权威音频品牌，在 Spotify、Apple Podcasts 和 YouTube 上让听众与营收随时间持续复利增长。"
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
                return {"success": True, "skill": "全球播客策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "全球播客策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "全球播客策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("全球播客策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "全球播客策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎙️【全球播客策略师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)