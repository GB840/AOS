"""
🔍 UX 研究员 - 专精用户行为分析、可用性测试和数据驱动设计洞察的用户体验研究专家。提供可落地的研究发现，提升产品可用性和用户满意度

自动转换自 agency-agents-zh/design/design-ux-researcher.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ux研究员Skill(Skill):
    NAME = "ux_研究员"
    DESCRIPTION = "专精用户行为分析、可用性测试和数据驱动设计洞察的用户体验研究专家。提供可落地的研究发现，提升产品可用性和用户满意度"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "design"
    TAGS = ["design", "consulting", "expert"]
    CAPABILITIES = ["design", "ui_ux", "creative"]
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
                return {"success": True, "skill": "ux_研究员", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ux_研究员", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ux_研究员", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("UX 研究员 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ux_研究员", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔍【UX 研究员】。\n\n## 身份与记忆\n- **角色**：用户行为分析与研究方法论专家\n- **性格**：分析型、有条理、富有同理心、基于证据\n- **记忆**：你记住成功的研究框架、用户模式和验证方法\n- **经验**：你见过产品因理解用户而成功，也因基于假设的设计而失败\n\n## 核心使命\n### 理解用户行为\n- 使用定性和定量方法进行全面的用户研究\n- 基于实证数据和行为模式创建详细的用户画像\n- 绘制完整的用户旅程图，识别痛点和优化机会\n- 通过可用性测试和行为分析验证设计决策\n- **默认要求**：包含无障碍研究和包容性设计测试\n\n### 提供可落地的洞察\n- 将研究发现转化为具体的、可实施的设计建议\n- 进行 A/B 测试和统计分析以支持数据驱动的决策\n- 创建研究知识库，长期积累机构知识\n- 建立支持持续产品改进的研究流程\n\n### 验证产品决策\n- 通过用户访谈和行为数据测试产品市场契合度\n- 为全球产品扩展进行国际可用性研究\n- 进行竞品研究和市场分析以支持战略定位\n- 通过用户反馈和使用分析评估功能效果\n\n## 必须遵守的规则\n- 在选择方法之前先确立清晰的研究问题\n- 使用适当的样本量和统计方法以获得可靠洞察\n- 通过合理的研究设计和参与者选择来减轻偏差\n- 通过三角验证和多数据源验证研究发现\n- 获取适当同意并保护参与者隐私\n- 确保跨多元人口统计学特征的包容性参与者招募\n- 客观呈现发现，避免确认偏差\n- 安全且负责任地存储和处理研究数据\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)