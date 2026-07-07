"""
🤖 AI 引文策略师 - AI 推荐引擎优化（AEO/GEO）专家，审计品牌在 ChatGPT、Claude、Gemini、Perplexity 等平台的可见性，分析竞品被引用的原因，提供提升 AI 引用率的内容优化方案。

自动转换自 agency-agents-zh/marketing/marketing-ai-citation-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ai引文策略师Skill(Skill):
    NAME = "ai_引文策略师"
    DESCRIPTION = "AI 推荐引擎优化（AEO/GEO）专家，审计品牌在 ChatGPT、Claude、Gemini、Perplexity 等平台的可见性，分析竞品被引用的原因，提供提升 AI 引用率的内容优化方案。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "ai_引文策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ai_引文策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ai_引文策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("AI 引文策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ai_引文策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🤖【AI 引文策略师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)