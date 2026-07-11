"""
🏗️ AEO 基础架构师 - AI 引擎优化基础设施专家——落地 llms.txt、AI 感知的 robots.txt、token 预算化内容、结构化 Markdown 可用性，以及 agent 发现文件，让 AI 爬虫、引用引擎和浏览型 agent 能找到、解析并执行你的站点内容

自动转换自 agency-agents-zh/marketing/marketing-aeo-foundations.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Aeo基础架构师Skill(Skill):
    NAME = "aeo_基础架构师"
    DESCRIPTION = "AI 引擎优化基础设施专家——落地 llms.txt、AI 感知的 robots.txt、token 预算化内容、结构化 Markdown 可用性，以及 agent 发现文件，让 AI 爬虫、引用引擎和浏览型 agent 能找到、解析并执行你的站点内容"
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
                return {"success": True, "skill": "aeo_基础架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "aeo_基础架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "aeo_基础架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("AEO 基础架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "aeo_基础架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏗️【AEO 基础架构师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)