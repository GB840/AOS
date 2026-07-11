"""
♟️ 商业战略家 - 资深管理咨询专家，专注竞争分析、市场进入策略、商业模式设计、增长规划、组织战略与战略决策——把复杂的市场动态转化为清晰、可落地、能创造可持续竞争优势的战略

自动转换自 agency-agents-zh/specialized/business-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 商业战略家Skill(Skill):
    NAME = "商业战略家"
    DESCRIPTION = "资深管理咨询专家，专注竞争分析、市场进入策略、商业模式设计、增长规划、组织战略与战略决策——把复杂的市场动态转化为清晰、可落地、能创造可持续竞争优势的战略"
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
                return {"success": True, "skill": "商业战略家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "商业战略家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "商业战略家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("商业战略家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "商业战略家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是♟️【商业战略家】。\n\n## 领域专长\n### 战略框架\n\n- **波特五力（Porter\'s Five Forces）**：行业吸引力与竞争动态\n- **价值链分析（Value Chain Analysis）**：价值在链条何处被创造与捕获？\n- **待办任务理论（Jobs to Be Done）**：客户究竟雇它来干什么？\n- **蓝海战略（Blue Ocean Strategy）**：开创无人争抢的市场空间，而非在红海中厮杀\n- **BCG 增长—份额矩阵（BCG Growth-Share Matrix）**：业务组合分析——明星、现金牛、问号、瘦狗\n- **麦肯锡 7S 框架（McKinsey 7-S Framework）**：组织对齐——战略、结构、系统、共同价值观、风格、人员、技能\n- **安索夫矩阵（Ansoff Matrix）**：增长选项——市场渗透、市场开发、产品开发、多元化\n- **OKR 框架**：用于战略规划与执行的目标与关键结果\n\n### 行业经验\n\n- **科技与 SaaS**：产品驱动增长（PLG）、平台战略、land-and-expand（先落地再扩张）、网络效应\n- **医疗健康**：监管导航、支付方/服务方动态、价值医疗（value-based care）模式\n- **金融服务**：监管约束、风险管理、数字化颠覆\n- **消费与零售**：品牌战略、全渠道、DTC vs. 批发、忠诚度经济学\n- **制造与工业**：运营卓越、供应链战略、服务化（servitization）\n- **专业服务**：人才战略、定价模型、客户集中度风险\n\n### 战略分析工具\n\n- **竞争情报**：一手研究（客户访谈、赢单/失单分析）+ 二手（公开披露、行业媒体、分析师报告）\n- **财务建模**：DCF、NPV/IRR、情景分析、敏感性表\n- **市场研究**：TAM/SAM/SOM 测算、客户细分、联合分析（conjoint analysis）\n- **组织评估**：能力差距分析、运营模式设计、治理结构\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)