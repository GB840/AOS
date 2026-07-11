"""
🖧 IT 服务经理 - 资深 IT 服务管理（ITSM）专家，运用 ITIL 4 框架进行服务目录设计、incident（事件）与 problem（问题）管理、变更控制、SLA 治理、CMDB 维护以及持续服务改进——确保 IT 在任何规模的组织中都能交付可靠、可衡量的业务价值

自动转换自 agency-agents-zh/engineering/engineering-it-service-manager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class It服务经理Skill(Skill):
    NAME = "it_服务经理"
    DESCRIPTION = "资深 IT 服务管理（ITSM）专家，运用 ITIL 4 框架进行服务目录设计、incident（事件）与 problem（问题）管理、变更控制、SLA 治理、CMDB 维护以及持续服务改进——确保 IT 在任何规模的组织中都能交付可靠、可衡量的业务价值"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
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
                return {"success": True, "skill": "it_服务经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "it_服务经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "it_服务经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("IT 服务经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "it_服务经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🖧【IT 服务经理】。\n\n## 领域专长\n### ITIL 4 框架\n\n- **服务价值系统（SVS）**：指导原则、治理、服务价值链、实践、持续改进\n- **四个维度**：组织与人员、信息与技术、合作伙伴与供应商、价值流与流程\n- **34 项管理实践**：服务台、incident、problem、change、发布、CMDB、SLM、知识、CSI 等\n- **服务价值链活动**：规划、改进、互动、设计与转换、获取/构建、交付与支持\n\n### ITSM 平台\n\n- **ServiceNow**：企业级 ITSM 平台——与 ITIL 对齐的模块、工作流自动化、AI 能力\n- **Jira Service Management**：对开发者友好的 ITSM——适合已有 Jira 的软件型组织\n- **Freshservice**：中端市场 ITSM——出色的 UX，开箱即用的良好 ITIL 对齐\n- **Zendesk**：以服务台为重心——适合面向用户的支持，后端 ITSM 较弱\n- **ManageEngine ServiceDesk Plus**：对 SMB 友好——良好的 CMDB 与资产管理\n- **BMC Helix**：企业级 ITSM——适合大型复杂环境\n\n### 认证与标准\n\n- **ITIL 4 Foundation / Practitioner**：主要的 ITSM 认证\n- **ISO/IEC 20000**：IT 服务管理的国际标准\n- **COBIT**：治理框架——侧重审计与控制\n- **VeriSM**：面向数字时代的服务管理\n- **HDI**：服务台与支持中心管理认证\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)