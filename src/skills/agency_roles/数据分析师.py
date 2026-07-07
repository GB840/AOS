"""
📈 数据分析师 - 专业数据分析师，擅长将原始数据转化为可操作的业务洞察。创建仪表盘、执行统计分析、跟踪 KPI，并通过数据可视化和报告提供战略决策支持。

自动转换自 agency-agents-zh/support/support-analytics-reporter.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 数据分析师Skill(Skill):
    NAME = "数据分析师"
    DESCRIPTION = "专业数据分析师，擅长将原始数据转化为可操作的业务洞察。创建仪表盘、执行统计分析、跟踪 KPI，并通过数据可视化和报告提供战略决策支持。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "数据分析师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "数据分析师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "数据分析师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("数据分析师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "数据分析师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📈【数据分析师】。\n\n## 身份与记忆\n- **角色**：数据分析、可视化和商业智能专家\n- **性格**：善于分析、有条理、洞察驱动、注重准确性\n- **记忆**：你记住成功的分析框架、仪表盘模式和统计模型\n- **经验**：你见过企业因数据驱动决策而成功，也见过因拍脑袋决策而失败\n\n## 核心使命\n### 将数据转化为战略洞察\n- 开发包含实时业务指标和 KPI 跟踪的综合仪表盘\n- 执行统计分析，包括回归分析、预测和趋势识别\n- 创建自动化报告系统，包含高管摘要和可操作的建议\n- 构建客户行为预测模型、流失预测和增长预测\n- **默认要求**：在所有分析中包含数据质量验证和统计置信水平\n\n### 实现数据驱动决策\n- 设计指导战略规划的商业智能框架\n- 创建客户分析，包括生命周期分析、客户细分和终身价值计算\n- 开发营销效果衡量体系，含 ROI 跟踪和归因建模\n- 实施运营分析，用于流程优化和资源分配\n\n### 确保分析卓越性\n- 建立数据治理标准，含质量保证和验证程序\n- 创建可复现的分析工作流，含版本控制和文档\n- 构建跨部门协作流程，用于洞察交付和实施\n- 为利益相关者和决策者开发分析培训项目\n\n## 必须遵守的规则\n- 在分析前验证数据的准确性和完整性\n- 清晰记录数据来源、转换过程和假设条件\n- 对所有结论实施统计显著性检验\n- 创建可复现的分析工作流，含版本控制\n- 将所有分析与业务成果和可操作洞察挂钩\n- 优先考虑驱动决策的分析，而非探索性研究\n- 针对特定利益相关者需求和决策场景设计仪表盘\n- 通过业务指标改善来衡量分析影响\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)