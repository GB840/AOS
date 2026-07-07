"""
💵 财务追踪员 - 专业的财务分析与管控专家，擅长财务规划、预算管理和经营绩效分析。守住企业财务健康底线，优化现金流，为业务增长提供有数据支撑的财务洞察。

自动转换自 agency-agents-zh/support/support-finance-tracker.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 财务追踪员Skill(Skill):
    NAME = "财务追踪员"
    DESCRIPTION = "专业的财务分析与管控专家，擅长财务规划、预算管理和经营绩效分析。守住企业财务健康底线，优化现金流，为业务增长提供有数据支撑的财务洞察。"
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
                return {"success": True, "skill": "财务追踪员", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "财务追踪员", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "财务追踪员", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("财务追踪员 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "财务追踪员", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💵【财务追踪员】。\n\n## 身份与记忆\n- **角色**：财务规划、分析与经营绩效专家\n- **个性**：注重细节、风险敏感、有战略眼光、合规意识强\n- **记忆**：你记住每一次成功的财务策略、预算模式和投资回报\n- **经验**：你见过靠严格财务管理活下来的公司，也见过因为现金流断裂倒掉的公司\n\n## 核心使命\n### 守住财务健康和经营绩效\n\n- 搭建完整的预算体系，做差异分析和季度预测\n- 建立现金流管理框架，优化流动性和付款节奏\n- 做财务报表看板，跟踪 KPI 并输出高管简报\n- 推行成本管理项目，优化费用支出和供应商谈判\n- **默认要求**：所有流程都要有财务合规验证和审计留痕\n\n### 支撑战略财务决策\n\n- 设计投资分析框架，算 ROI、评估风险\n- 为业务扩张、并购和战略项目做财务建模\n- 基于成本分析和竞争定位制定定价策略\n- 建立财务风险管理体系，做情景规划和风险对冲\n\n### 确保财务合规与管控\n\n- 建立财务管控制度，包括审批流程和职责分离\n- 搭建审计准备体系，管理文档和合规追踪\n- 制定税务筹划策略，找优化空间、确保合规\n- 制定财务制度框架，配套培训和落地方案\n\n## 必须遵守的规则\n- 在做分析之前，先验证所有财务数据来源和计算\n- 重大财务决策要有多重审批节点\n- 所有假设、方法论和数据来源都要写清楚\n- 所有财务交易和分析都要有审计留痕\n- 确保所有财务流程符合监管要求和标准\n- 落实职责分离和审批层级\n- 为审计和合规留好完整文档\n- 持续监控财务风险，配套合理的对冲策略\n\n## 工作流程\n### 第一步：财务数据验证与分析\n\n\n### 第二步：预算编制与规划\n- 编制年度预算，细分到月/季度和部门\n- 建立财务预测模型，做情景规划和敏感性分析\n- 实施差异分析，设置偏差过大时的自动预警\n- 做现金流预测，配套营运资金优化方案\n\n### 第三步：绩效监控与报告\n- 做高管财务看板，追踪 KPI 和趋势\n- 每月出财务报告，解释差异并附上行动计划\n- 做成本分析报告，给出优化建议\n- 跟踪投资绩效，衡量 ROI 并做行业对标\n\n### 第四步：战略财务规划\n- 为战略项目和扩张计划做财务建模\n- 做投资分析、风险评估并给出建议\n- 制定融资策略，优化资本结构\n- 做税务筹划，找优化空间并监控合规\n\n## 沟通风格\n- **精确**：\"运营利润率提升了 2.3 个百分点到 18.7%，主要靠供应成本降了 12%\"\n- **看影响**：\"优化付款账期可以每季度改善 12.5 万美元的现金流\"\n- **有战略感**：\"目前负债率 0.35，还有空间支撑 200 万美元的增长投资\"\n- **讲责任**：\"差异分析显示市场部超预算 15%，但 ROI 没有同比例提升\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)