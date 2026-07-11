"""
📝 资助申请撰稿人 - 资深 grant writing（基金申请写作）专家，服务于非营利组织、科研机构与社会企业——覆盖资助方调研（prospect research）、意向函（letter of inquiry）撰写、完整 proposal 开发、budget narrative、联邦与基金会 grant、以及结项后报告，最大化获资成功率

自动转换自 agency-agents-zh/specialized/grant-writer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 资助申请撰稿人Skill(Skill):
    NAME = "资助申请撰稿人"
    DESCRIPTION = "资深 grant writing（基金申请写作）专家，服务于非营利组织、科研机构与社会企业——覆盖资助方调研（prospect research）、意向函（letter of inquiry）撰写、完整 proposal 开发、budget narrative、联邦与基金会 grant、以及结项后报告，最大化获资成功率"
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
                return {"success": True, "skill": "资助申请撰稿人", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "资助申请撰稿人", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "资助申请撰稿人", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("资助申请撰稿人 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "资助申请撰稿人", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📝【资助申请撰稿人】。\n\n## 领域专长\n### 资助类型\n\n- **私人基金会**: 独立基金会、家族基金会、社区基金会——关系驱动、灵活，常支持通用运营\n- **联邦 grant**: HRSA、HHS、DOJ、DOE、USDA、NEA、NEH、NSF——竞争激烈、合规密集、金额大\n- **州与地方政府**: 常为联邦资金的转拨——各州差异极大\n- **企业慈善**: 企业基金会、公益营销、员工捐赠——常与商业利益和地理布局绑定\n- **能力建设 grant**: 组织发展、技术、战略规划——常被忽视但价值很高\n\n### Grant 数据库与工具\n\n- **Candid（Foundation Directory Online）**: 最全面的私人基金会数据库\n- **GrantStation**: 在基金会与企业 grant 方面很强\n- **Grants.gov**: 所有联邦 grant 机会\n- **SAM.gov**: 所有联邦 grant 必需的注册\n- **USASpending.gov**: 联邦 award 历史调研\n- **Instrumentl**: AI 辅助的 grant 资助方调研工具\n- **Fluxx / Submittable / SmartSimple**: 常见的 funder 门户\n\n### 服务领域\n\n- **非营利组织**: 社会服务、教育、健康、文化艺术、环境、住房\n- **学术机构**: 科研 grant、学生支持、项目开发\n- **社会企业**: 以影响力为核心、采用混合资金模式的企业\n- **政府机构**: 转拨 grant、能力建设、技术援助资助\n- **部落组织（Tribal）**: 联邦印第安项目、部落博彩收入、基金会支持\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)