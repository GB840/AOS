"""
📧 邮件营销策略师 - 资深邮件营销策略师，专注于 CRM 驱动的营销活动、生命周期自动化、分群架构与可送达性。基于 2025-2026 基准数据、AI 驱动的个性化以及后 Apple MPP 时代的衡量体系，设计各类序列（欢迎、培育、再激活、挽回、评价、转介绍）。

自动转换自 agency-agents-zh/marketing/marketing-email-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 邮件营销策略师Skill(Skill):
    NAME = "邮件营销策略师"
    DESCRIPTION = "资深邮件营销策略师，专注于 CRM 驱动的营销活动、生命周期自动化、分群架构与可送达性。基于 2025-2026 基准数据、AI 驱动的个性化以及后 Apple MPP 时代的衡量体系，设计各类序列（欢迎、培育、再激活、挽回、评价、转介绍）。"
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
                return {"success": True, "skill": "邮件营销策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "邮件营销策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "邮件营销策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("邮件营销策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "邮件营销策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📧【邮件营销策略师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)