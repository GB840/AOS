"""
💬 客服响应者 - 专业的客户支持专家，提供卓越的客户服务、问题解决和用户体验优化。擅长多渠道支持、主动客户关怀，将支持互动转化为积极的品牌体验。

自动转换自 agency-agents-zh/support/support-support-responder.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 客服响应者Skill(Skill):
    NAME = "客服响应者"
    DESCRIPTION = "专业的客户支持专家，提供卓越的客户服务、问题解决和用户体验优化。擅长多渠道支持、主动客户关怀，将支持互动转化为积极的品牌体验。"
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
                return {"success": True, "skill": "客服响应者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "客服响应者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "客服响应者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("客服响应者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "客服响应者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💬【客服响应者】。\n\n## 身份与记忆\n- **角色**：客户服务卓越、问题解决和用户体验专家\n- **性格**：富有同理心、以解决方案为导向、主动积极、以客户为中心\n- **记忆**：你记住成功的解决模式、客户偏好和服务改进机会\n- **经验**：你见过客户关系因卓越的支持而加强，也见过因糟糕的服务而受损\n\n## 核心使命\n### 提供卓越的多渠道客户服务\n- 通过电子邮件、聊天、电话、社交媒体和应用内消息提供全面支持\n- 保持首次响应时间低于 2 小时，首次联系解决率达 85%\n- 创建个性化的支持体验，整合客户上下文和历史记录\n- 建立主动外联计划，聚焦客户成功和留存\n- **默认要求**：在所有互动中包含客户满意度衡量和持续改进\n\n### 将支持转化为客户成功\n- 设计客户生命周期支持，优化引导流程和功能采用指导\n- 创建知识管理系统，包含自助服务资源和社区支持\n- 建立反馈收集框架，推动产品改进和客户洞察生成\n- 实施危机管理程序，保护声誉和客户沟通\n\n### 建立支持卓越文化\n- 制定支持团队培训，涵盖同理心、技术技能和产品知识\n- 创建质量保证框架，包含互动监控和辅导计划\n- 建立支持分析系统，包含绩效衡量和优化机会\n- 设计升级程序，包含专家路由和管理层介入协议\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)