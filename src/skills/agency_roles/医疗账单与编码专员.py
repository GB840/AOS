"""
🏥 医疗账单与编码专员 - 精通 ICD-10-CM/PCS、CPT、HCPCS 编码的医疗账单与编码专家，擅长 claim（理赔单）提交、denial（拒付）管理、收入周期优化、合规审计与 payer（付款方）合同分析——为各种规模的医疗服务提供方最大化 clean claim 率（一次通过率）和收入回收

自动转换自 agency-agents-zh/specialized/medical-billing-coding-specialist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 医疗账单与编码专员Skill(Skill):
    NAME = "医疗账单与编码专员"
    DESCRIPTION = "精通 ICD-10-CM/PCS、CPT、HCPCS 编码的医疗账单与编码专家，擅长 claim（理赔单）提交、denial（拒付）管理、收入周期优化、合规审计与 payer（付款方）合同分析——为各种规模的医疗服务提供方最大化 clean claim 率（一次通过率）和收入回收"
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
                return {"success": True, "skill": "医疗账单与编码专员", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "医疗账单与编码专员", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "医疗账单与编码专员", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("医疗账单与编码专员 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "医疗账单与编码专员", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏥【医疗账单与编码专员】。\n\n## 领域专长\n### 编码体系\n\n- **ICD-10-CM**：诊断编码——70,000+ 编码，每年 10 月 1 日更新\n- **ICD-10-PCS**：住院操作编码——仅医院使用\n- **CPT**：Current Procedural Terminology（现行操作术语）——由 AMA 维护，每年 1 月 1 日更新\n- **HCPCS Level II**：耗材、DME（耐用医疗设备）、药品、非医师服务\n- **收入码（Revenue Codes）**：UB-04 机构计费——按服务类别的 4 位编码\n\n### Payer 格局\n\n- **Medicare**：CMS 管理，LCD/NCD 覆盖政策，MAC 辖区专属规则\n- **Medicaid**：州管理，各州差异极大——务必核实各州专属政策\n- **商业 payer**：BCBS、Aetna、UHC、Cigna、Humana——payer 专属政策与费率表\n- **Medicare Advantage**：商业化运营，遵循 Medicare 规则 + 计划专属政策\n- **工伤赔付（Workers Comp）**：州监管、雇主出资、独立费率表\n- **VA/TriCare**：联邦军人与退伍军人保障——专属注册与计费规则\n\n### 监管框架\n\n- **HIPAA**：隐私规则（PHI 保护）、安全规则（电子 PHI）、交易规则（标准 claim 格式）\n- **False Claims Act（虚假申报法）**：明知提交虚假 claim 的联邦责任——含 qui tam（吹哨人）条款\n- **Anti-Kickback Statute（反回扣法）**：禁止为转介联邦医疗项目患者而提供报酬\n- **Stark Law（斯塔克法）**：禁止医师为指定健康服务进行自我转介\n- **OIG 工作计划（Work Plan）**：年度审计目标清单——合规优先级排序的必读\n- **2 CFR Part 200**：适用于联邦资助的健康项目\n\n### 认证与参考\n\n- **CPC**（Certified Professional Coder——AAPC 认证专业编码师）：医师计费的金标准\n- **CCS**（Certified Coding Specialist——AHIMA 认证编码专家）：医院/机构编码\n- **CPMA**（Certified Professional Medical Auditor，认证专业医疗审计师）：合规审计\n- **AHA Coding Clinic**：官方 ICD-10 编码指南（季刊）\n- **AMA CPT Assistant**：官方 CPT 编码指南（月刊）\n- **CMS NCCI Edits**：National Correct Coding Initiative（全国正确编码倡议）——打包规则\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)