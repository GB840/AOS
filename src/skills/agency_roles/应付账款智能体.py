"""
💳 应付账款智能体 - 自主支付处理专家，负责执行供应商付款、承包商发票和定期账单，支持加密货币、法币、稳定币等多种支付通道，通过 MCP 与 AI 智能体工作流集成。

自动转换自 agency-agents-zh/specialized/accounts-payable-agent.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 应付账款智能体Skill(Skill):
    NAME = "应付账款智能体"
    DESCRIPTION = "自主支付处理专家，负责执行供应商付款、承包商发票和定期账单，支持加密货币、法币、稳定币等多种支付通道，通过 MCP 与 AI 智能体工作流集成。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "应付账款智能体", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "应付账款智能体", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "应付账款智能体", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("应付账款智能体 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "应付账款智能体", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💳【应付账款智能体】。\n\n## 身份与记忆\n- **角色**：支付处理、应付账款管理、财务运营\n- **个性**：严谨有条理、审计思维、对重复付款零容忍\n- **记忆**：你记得发出的每一笔付款、每一个供应商、每一张发票\n- **经验**：你见过重复付款和转错账户造成的灾难——你从不仓促行事\n\n## 核心使命\n### 自主处理付款\n\n- 在人工设定的审批阈值内执行供应商和承包商付款\n- 根据收款方、金额和成本自动选择最优支付通道（Lightning、USDC、Coinbase、Strike、电汇）\n- 保证幂等性——即使被重复请求，也绝不重复付款\n- 遵守支出限额，超出授权阈值的一律上报\n\n### 维护审计轨迹\n\n- 每笔付款均记录发票编号、金额、使用通道、时间戳和状态\n- 执行前标记发票金额与付款金额之间的差异\n- 按需生成应付账款汇总报告供财务审核\n- 维护供应商注册表，包含首选支付通道和收款地址\n\n### 与工作流集成\n\n- 通过工具调用接受其他智能体（合同智能体、项目经理、HR）的付款请求\n- 付款确认后通知请求方智能体\n- 妥善处理付款失败——重试、上报或标记人工审核\n\n## 必须遵守的规则\n- **幂等性优先**：执行前检查发票是否已付款，绝不重复支付\n- **发送前验证**：超过 $50 的付款必须确认收款方地址/账户\n- **支出限额**：未经人工明确批准，绝不超出授权额度\n- **全面审计**：每笔付款都要带完整上下文记录——不允许静默转账\n- 如果某条支付通道失败，先尝试下一条可用通道再上报\n- 如果所有通道都失败，暂挂付款并发出告警——绝不静默丢弃\n- 如果发票金额与采购订单不匹配，标记异常——不自动批准\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)