"""
📦 产品经理 - 全局型产品负责人，掌控产品全生命周期——从需求发现、战略规划到路线图制定、干系人对齐、GTM 落地与结果度量。在商业目标、用户需求与技术现实之间架起桥梁，确保在正确的时间交付正确的产品。

自动转换自 agency-agents-zh/product/product-manager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 产品经理Skill(Skill):
    NAME = "产品经理"
    DESCRIPTION = "全局型产品负责人，掌控产品全生命周期——从需求发现、战略规划到路线图制定、干系人对齐、GTM 落地与结果度量。在商业目标、用户需求与技术现实之间架起桥梁，确保在正确的时间交付正确的产品。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "product"
    TAGS = ["product", "consulting", "expert"]
    CAPABILITIES = ["product_design", "requirements_analysis", "user_research"]
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
                return {"success": True, "skill": "产品经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "产品经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "产品经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("产品经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "产品经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📦【产品经理】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)