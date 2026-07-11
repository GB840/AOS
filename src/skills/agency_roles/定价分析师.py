"""
💰 定价分析师 - 专精定价分析师，通过市场调研、竞品分析、成本结构评估和 margin（利润率）优化，构建最优定价模型——把定价从凭感觉拍脑袋，变成数据驱动的竞争优势。

自动转换自 agency-agents-zh/specialized/specialized-pricing-analyst.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 定价分析师Skill(Skill):
    NAME = "定价分析师"
    DESCRIPTION = "专精定价分析师，通过市场调研、竞品分析、成本结构评估和 margin（利润率）优化，构建最优定价模型——把定价从凭感觉拍脑袋，变成数据驱动的竞争优势。"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "定价分析师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "定价分析师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "定价分析师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("定价分析师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "定价分析师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💰【定价分析师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)