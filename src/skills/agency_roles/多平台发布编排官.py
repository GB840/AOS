"""
📡 多平台发布编排官 - 一键中文博客发布的专家级编排官。把同一篇文章通过 Wechatsync(主通道)路由到 知乎 / 小红书 / CSDN / B站 / 公众号 / 掘金,并以 xhs-mcp 和 biliup 作为专用兜底。负责各平台内容适配、草稿优先发布、频率控制与风险规避。绝不自动发布——始终停在草稿阶段交由人工审核。

自动转换自 agency-agents-zh/marketing/marketing-multi-platform-publisher.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 多平台发布编排官Skill(Skill):
    NAME = "多平台发布编排官"
    DESCRIPTION = "一键中文博客发布的专家级编排官。把同一篇文章通过 Wechatsync(主通道)路由到 知乎 / 小红书 / CSDN / B站 / 公众号 / 掘金,并以 xhs-mcp 和 biliup 作为专用兜底。负责各平台内容适配、草稿优先发布、频率控制与风险规避。绝不自动发布——始终停在草稿阶段交由人工审核。"
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
                return {"success": True, "skill": "多平台发布编排官", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "多平台发布编排官", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "多平台发布编排官", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("多平台发布编排官 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "多平台发布编排官", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📡【多平台发布编排官】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)