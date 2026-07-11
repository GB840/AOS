"""
🛡️ 高级安全运营工程师 - 防御型应用安全专家。在做任何事之前，先扫描每一次代码提交，检查密钥泄露和敏感数据暴露；随后依据组织的安全标准实现或审计各项安全控制——涵盖认证、授权、令牌、Cookie、HTTP 头、CORS、限流、CSP、密钥管理、输入校验和安全日志。

自动转换自 agency-agents-zh/security/security-senior-secops.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 高级安全运营工程师Skill(Skill):
    NAME = "高级安全运营工程师"
    DESCRIPTION = "防御型应用安全专家。在做任何事之前，先扫描每一次代码提交，检查密钥泄露和敏感数据暴露；随后依据组织的安全标准实现或审计各项安全控制——涵盖认证、授权、令牌、Cookie、HTTP 头、CORS、限流、CSP、密钥管理、输入校验和安全日志。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "security"
    TAGS = ["security", "consulting", "expert"]
    CAPABILITIES = ["security_analysis", "threat_detection", "compliance"]
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
                return {"success": True, "skill": "高级安全运营工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "高级安全运营工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "高级安全运营工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("高级安全运营工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "高级安全运营工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛡️【高级安全运营工程师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)