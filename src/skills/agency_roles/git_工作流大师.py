"""
🔀 Git 工作流大师 - Git 工作流专家，精通分支策略、版本控制最佳实践，包括约定式提交、变基、工作树和 CI 友好的分支管理。

自动转换自 agency-agents-zh/engineering/engineering-git-workflow-master.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Git工作流大师Skill(Skill):
    NAME = "git_工作流大师"
    DESCRIPTION = "Git 工作流专家，精通分支策略、版本控制最佳实践，包括约定式提交、变基、工作树和 CI 友好的分支管理。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
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
                return {"success": True, "skill": "git_工作流大师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "git_工作流大师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "git_工作流大师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Git 工作流大师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "git_工作流大师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔀【Git 工作流大师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)