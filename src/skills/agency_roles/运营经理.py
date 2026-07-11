"""
⚙️ 运营经理 - 业务运营专家，把 Lean（精益）、Six Sigma（六西格玛）和系统思维应用到流程梳理、产能规划、KPI 治理、供应商管理和组织效率提升上——将运营的复杂性转化为可复制、可衡量的绩效。

自动转换自 agency-agents-zh/specialized/operations-manager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 运营经理Skill(Skill):
    NAME = "运营经理"
    DESCRIPTION = "业务运营专家，把 Lean（精益）、Six Sigma（六西格玛）和系统思维应用到流程梳理、产能规划、KPI 治理、供应商管理和组织效率提升上——将运营的复杂性转化为可复制、可衡量的绩效。"
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
                return {"success": True, "skill": "运营经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "运营经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "运营经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("运营经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "运营经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是⚙️【运营经理】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)