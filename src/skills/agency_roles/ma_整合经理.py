"""
🤝 M&A 整合经理 - 并购(M&A)整合专家，负责设计并执行并购后整合(PMI)项目——涵盖 Day 1 就绪、百日计划、synergy(协同效应)追踪、文化整合、职能工作流协调，以及过渡服务协议(TSA)管理。

自动转换自 agency-agents-zh/specialized/ma-integration-manager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ma整合经理Skill(Skill):
    NAME = "ma_整合经理"
    DESCRIPTION = "并购(M&A)整合专家，负责设计并执行并购后整合(PMI)项目——涵盖 Day 1 就绪、百日计划、synergy(协同效应)追踪、文化整合、职能工作流协调，以及过渡服务协议(TSA)管理。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "specialized"
    TAGS = ["specialized", "consulting", "expert"]
    CAPABILITIES = ["consulting", "analysis", "strategy"]
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
                return {"success": True, "skill": "ma_整合经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ma_整合经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ma_整合经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("M&A 整合经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ma_整合经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🤝【M&A 整合经理】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)