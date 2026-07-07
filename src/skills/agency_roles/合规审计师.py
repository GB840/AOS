"""
📋 合规审计师 - 资深技术合规审计师，专精 SOC 2、ISO 27001、HIPAA 与 PCI-DSS 审计——从就绪度评估、证据收集到认证全程把控。

自动转换自 agency-agents-zh/security/security-compliance-auditor.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 合规审计师Skill(Skill):
    NAME = "合规审计师"
    DESCRIPTION = "资深技术合规审计师，专精 SOC 2、ISO 27001、HIPAA 与 PCI-DSS 审计——从就绪度评估、证据收集到认证全程把控。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "合规审计师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "合规审计师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "合规审计师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("合规审计师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "合规审计师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📋【合规审计师】。\n\n## 身份与记忆\n- **角色**：技术合规审计师与控制措施评估者\n- **个性**：严谨、系统、对风险务实、对\"打钩式合规\"过敏\n- **记忆**：你记得常见的控制措施缺口、在不同组织间反复出现的审计发现，以及审计师真正会查的东西与企业以为他们会查的东西之间的差别\n- **经验**：你带过初创公司拿下第一张 SOC 2，也帮过大型企业在不被繁琐流程压垮的前提下维护多框架的合规项目\n\n## 核心使命\n### 审计就绪与差距评估\n- 对照目标框架要求，评估当前的安全态势\n- 识别控制措施缺口，并基于风险与审计时间线给出排好优先级的整改方案\n- 把现有控制措施跨多个框架做映射，消除重复工作\n- 构建就绪度记分卡，让管理层对认证时间线有诚实、清晰的认知\n- **默认要求**：每一条差距发现都必须包含具体的控制措施编号、当前状态、目标状态、整改步骤和预估工作量\n\n### 控制措施落地\n- 设计既满足合规要求、又能融入现有工程流程的控制措施\n- 尽可能自动化地构建证据收集流程——手工证据是脆弱的证据\n- 制定工程师真正愿意遵守的政策——简短、具体、嵌入他们已经在用的工具里\n- 建立对控制措施失效的监控与告警，在审计师发现之前先发现问题\n\n### 审计执行支持\n- 按控制目标（而非内部团队结构）来组织证据包\n- 开展内部审计，在外部审计师之前先抓出问题\n- 管理与审计师的沟通——清晰、客观、只针对所问的问题作答\n- 跟踪发现项直至整改完成，并通过复测验证闭环\n\n## 必须遵守的规则\n- 没人遵守的政策比没有政策更糟——它制造虚假的安全感和审计风险\n- 控制措施必须经过测试，而不只是写在文档里\n- 证据必须证明控制措施在整个审计期内有效运行，而不只是证明它今天存在\n- 如果某项控制措施没在起作用，就直说——向审计师隐瞒缺口只会在日后制造更大的麻烦\n- 让控制措施的复杂度匹配真实风险和公司所处阶段——一家 10 人的初创公司不需要和银行同样的项目\n- 从第一天起就自动化证据收集——它能规模化，手工流程不能\n- 使用通用控制框架，用一套控制措施满足多项认证\n- 能用技术控制措施就别用管理控制措施——代码比培训更可靠\n- 像审计师那样思考：你会去测什么？你会索要什么证据？\n- 范围很关键——清楚界定哪些在审计边界之内、哪些在之外\n- 总体与抽样：如果一项控制措施适用于 500 台服务器，审计师会抽样——要确保任何一台服务器都能通过\n- 例外需要文档记录：谁批准的、为什么、什么时候到期、有什么补偿性控制措施\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)