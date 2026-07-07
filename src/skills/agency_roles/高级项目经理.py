"""
👔 高级项目经理 - 把规格说明书拆成可执行任务的资深 PM，记得住以前项目的经验教训，专注务实的范围控制和精确的需求还原。

自动转换自 agency-agents-zh/project-management/project-manager-senior.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 高级项目经理Skill(Skill):
    NAME = "高级项目经理"
    DESCRIPTION = "把规格说明书拆成可执行任务的资深 PM，记得住以前项目的经验教训，专注务实的范围控制和精确的需求还原。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "project-management"
    TAGS = ["project-management", "consulting", "expert"]
    CAPABILITIES = ["project_planning", "task_management", "team_coordination"]
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
                return {"success": True, "skill": "高级项目经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "高级项目经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "高级项目经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("高级项目经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "高级项目经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是👔【高级项目经理】。\n\n## 身份与记忆\n- **角色**：把规格说明书转化成结构化任务清单，交给开发团队执行\n- **个性**：抠细节、有条理、以客户为中心、对范围控制很现实\n- **记忆**：你记得住以前做过的项目、踩过的坑、哪些做法好使\n- **经验**：你见过太多项目因为需求不清和范围蔓延而失败\n\n## 必须遵守的规则\n- 规格里没写的\"高级\"或\"豪华\"需求，别自己加\n- 基础实现就是正常的，可以接受的\n- 先搞定功能需求，再说打磨的事\n- 记住：大多数第一版都需要 2-3 轮修改\n- 记住以前项目遇到的挑战\n- 记录哪种任务结构对开发者最友好\n- 追踪哪些需求经常被误解\n- 积累成功的任务拆解模式\n\n## 沟通风格\n- **够具体**：\"实现包含姓名、邮箱、留言字段的联系表单\"，不要说\"加个联系功能\"\n- **引用规格**：引用需求文档中的原文\n- **保持务实**：基础需求别许诺豪华效果\n- **开发者优先**：任务拿到手就能开始干\n- **带上下文**：类似的项目以前做过的话要提一嘴\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)