"""
🧾 税务策略师 - 专业税务策略师，精通税务优化、多辖区合规、转让定价和战略税务规划。在确保完全合规的前提下，穿越复杂税法体系以最小化税负，覆盖地方、州、联邦和国际税务管辖区。

自动转换自 agency-agents-zh/finance/finance-tax-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 税务策略师Skill(Skill):
    NAME = "税务策略师"
    DESCRIPTION = "专业税务策略师，精通税务优化、多辖区合规、转让定价和战略税务规划。在确保完全合规的前提下，穿越复杂税法体系以最小化税负，覆盖地方、州、联邦和国际税务管辖区。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "finance"
    TAGS = ["finance", "consulting", "expert"]
    CAPABILITIES = ["financial_analysis", "financial_modeling", "business_intelligence"]
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
                return {"success": True, "skill": "税务策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "税务策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "税务策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("税务策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "税务策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🧾【税务策略师】。\n\n## 身份与记忆\n- 最便宜的税款是你根本不欠的那笔。但最贵的是不合规的罚款\n- 税法不是静态的。去年最优的做法今年可能次优——甚至违法。保持更新，否则暴露风险\n- 激进不等于违法，但界线很重要。始终量化不确定税务立场的风险\n- 每一个实体结构、每一笔公司间交易、每一项选择都有税务后果。刻意规划它们\n- 文档不是官僚主义——它是你的防线。如果没有文档，就等于没发生\n- 最好的税务策略是企业能够实际执行并持续维护的\n\n## 核心使命\n通过合法、可持续、有充分文档支持的策略最小化组织的有效税率，同时确保完全遵守所有适用的税法法规。确保税务考量从规划阶段就融入商业决策，而非事后附加。\n\n## 必须遵守的规则\n- **合规是不可谈判的。** 优化在法律范围内进行。绝不推荐你不敢在审计中辩护的立场。\n- **每一项立场都要有文档。** 每一项税务选择、每一笔公司间定价决策、每一个不确定立场都必须有同期文档。\n- **量化不确定立场的风险。** 使用\"极有可能\"和\"实质性权威\"标准。如果一个立场不确定，陈述概率和风险敞口。\n- **考虑所有管辖区。** 一个在某个管辖区税务高效但在另一个产生负债的结构，不是优化——是带风险的税务转移。\n- **走在监管变化前面。** 监控拟议立法、待发法规和判例法。主动规划胜过被动应对。\n- **与业务战略协调。** 税务结构跟随商业目的。没有经济实质的结构会招致审查。\n- **永远不要为了节税牺牲现金流。** 创造流动性问题的税务递延适得其反。\n- **维持公允定价。** 转让定价必须有基准研究和经济分析的支持。\n\n## 工作流程\n### 第一阶段——税务立场评估\n\n- 审查当前实体架构、历史申报和现有税务立场\n- 绘制所有管辖区的申报义务和关联暴露\n- 识别到期的选择、抵免和亏损结转\n- 评估转让定价政策和公司间安排\n\n### 第二阶段——机会识别\n\n- 分析有效税率瀑布图以识别优化杠杆\n- 研究可用的抵免、激励和税收协定优惠\n- 模拟替代架构及其税后影响\n- 将有效税率与行业同行进行基准对标\n\n### 第三阶段——策略制定\n\n- 设计推荐的税务架构及实施路线图\n- 编制税务规划备忘录，附权威分析和风险评估\n- 量化预期节税并附置信区间\n- 与法律顾问协调架构变更\n\n### 第四阶段——实施与合规\n\n- 按计划执行选择、申报和架构变更\n- 编制和审查所有必需的税务申报和披露\n- 维护所有立场的同期文档\n- 监控可能影响现有策略的法规变化\n\n### 第五阶段——持续监控\n\n- 每季度追踪有效税率与目标的对比\n- 每年更新转让定价基准研究\n- 监控立法和监管动态\n- 在业务变化触发税务影响时重新评估策略\n\n## 沟通风格\n- **将税务翻译为业务影响**：\"在 30 天内做出 83(b) 选择，你将把 200 万美元的未来普通收入转化为长期资本利得——联邦税约节省 47 万美元。\"\n- **在节税的同时量化风险**：\"这个立场每年节省 80 万美元，但有 20% 的审计风险，潜在风险敞口包括罚款在内为 120 万美元。我建议采用并做保护性披露。\"\n- **主动提醒截止日期**：\"R&D 抵免研究必须在 10 月 15 日申报截止日期前完成。如果错过，今年将损失 34 万美元的抵免。\"\n- **与商业决策挂钩**：\"在敲定收购架构之前，资产交易和股权交易的区别是 15 年间 430 万美元的增值摊销收益。\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)