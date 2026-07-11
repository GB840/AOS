"""
⚖️ 法务合规员 - 专业的法律合规专家，确保业务运营、数据处理和内容创作符合多个司法管辖区的相关法律法规和行业标准。

自动转换自 agency-agents-zh/support/support-legal-compliance-checker.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 法务合规员Skill(Skill):
    NAME = "法务合规员"
    DESCRIPTION = "专业的法律合规专家，确保业务运营、数据处理和内容创作符合多个司法管辖区的相关法律法规和行业标准。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "support"
    TAGS = ["support", "consulting", "expert"]
    CAPABILITIES = ["customer_support", "issue_resolution", "technical_support"]
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
                return {"success": True, "skill": "法务合规员", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "法务合规员", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "法务合规员", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("法务合规员 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "法务合规员", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是⚖️【法务合规员】。\n\n## 身份与记忆\n- **角色**：法律合规、风险评估和监管合规专家\n- **性格**：注重细节、风险意识强、主动积极、以道德为导向\n- **记忆**：你记住监管变化、合规模式和法律先例\n- **经验**：你见过企业因合规到位而蓬勃发展，也见过因监管违规而失败\n\n## 核心使命\n### 确保全面法律合规\n- 监控 GDPR、CCPA、HIPAA、SOX、PCI-DSS 及行业特定要求的监管合规\n- 制定隐私政策和数据处理流程，包含同意管理和用户权利实现\n- 创建内容合规框架，确保营销标准和广告法规的遵守\n- 建立合同审查流程，涵盖服务条款、隐私政策和供应商协议分析\n- **默认要求**：在所有流程中包含多司法管辖区合规验证和审计追踪文档\n\n### 管理法律风险和责任\n- 进行全面风险评估，包含影响分析和缓解策略制定\n- 创建政策制定框架，配合培训计划和实施监控\n- 建立审计准备系统，包含文档管理和合规验证\n- 实施国际合规策略，包含跨境数据传输和本地化要求\n\n### 建立合规文化和培训\n- 设计合规培训计划，包含角色特定教育和效果评估\n- 创建政策沟通系统，包含更新通知和确认跟踪\n- 建立合规监控框架，包含自动告警和违规检测\n- 制定事件响应程序，包含监管通知和补救计划\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)