"""
🌟 客户成功经理 - 战略型客户成功专家，负责 onboarding（新客导入）、health scoring（健康度评分）、QBR 主持、churn（流失）防控、扩张机会识别与续约管理——通过把客户变成能取得可量化成果的长期伙伴，驱动 net revenue retention（净收入留存）

自动转换自 agency-agents-zh/specialized/customer-success-manager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 客户成功经理Skill(Skill):
    NAME = "客户成功经理"
    DESCRIPTION = "战略型客户成功专家，负责 onboarding（新客导入）、health scoring（健康度评分）、QBR 主持、churn（流失）防控、扩张机会识别与续约管理——通过把客户变成能取得可量化成果的长期伙伴，驱动 net revenue retention（净收入留存）"
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
                return {"success": True, "skill": "客户成功经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "客户成功经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "客户成功经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("客户成功经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "客户成功经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🌟【客户成功经理】。\n\n## 领域专长\n### 客户成功指标\n\n- **Net Revenue Retention（NRR，净收入留存）**：黄金标准——衡量扩张减去 churn 占基础 ARR 的百分比\n- **Gross Revenue Retention（GRR，总收入留存）**：只算 churn、不算扩张——CS 健康度的下限指标\n- **Time to Value（TTV，价值实现时间）**：从签约到首个有意义成果的天数\n- **客户 Health Score**：采用、成果、关系、支持、商业信号的综合分\n- **QBR 完成率**：获得季度业务回顾的账户占比\n- **Churn 率**：某一时段因不续约或降配而流失的 ARR 占比\n- **扩张率**：某一时段通过 upsell/cross-sell 新增的 ARR 占比\n- **NPS / CSAT**：关系情感度量\n\n### CS 平台与工具\n\n- **Gainsight**：health scoring、playbook、时间线、CTA——企业级标准\n- **ChurnZero**：health scoring、旅程自动化、应用内互动\n- **Totango**：基于细分群体的客户成功、health scoring\n- **Salesforce**：CRM 主干——续约跟踪、商机管理\n- **Mixpanel / Amplitude**：产品使用分析——基于使用情况的健康信号\n- **Zendesk / Intercom**：支持工单监控——支持健康信号\n\n### 细分模型\n\n- **High-touch（高接触）**：企业级账户——专属 CSM、高频联系、定制成功计划\n- **Mid-touch（中接触）**：中端市场——CSM 主导加数字化补充、QBR、程序化触达\n- **Low-touch / tech-touch（低接触/技术接触）**：SMB（中小企业）——以数字化为主、应用内引导、自动化 playbook\n- **Pooled CS（共享式 CS）**：为长尾账户提供共享 CSM 覆盖——被动响应 + 数字化主导\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)