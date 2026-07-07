"""
🔄 变革管理顾问 - 资深变革管理专家，运用 ADKAR、Kotter 和 Prosci 框架，引导组织顺利完成技术落地、组织重构、文化转型与并购整合——管理阻力、推动接纳，并确保变革在上线之后长久落地

自动转换自 agency-agents-zh/specialized/change-management-consultant.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 变革管理顾问Skill(Skill):
    NAME = "变革管理顾问"
    DESCRIPTION = "资深变革管理专家，运用 ADKAR、Kotter 和 Prosci 框架，引导组织顺利完成技术落地、组织重构、文化转型与并购整合——管理阻力、推动接纳，并确保变革在上线之后长久落地"
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
                return {"success": True, "skill": "变革管理顾问", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "变革管理顾问", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "变革管理顾问", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("变革管理顾问 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "变革管理顾问", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔄【变革管理顾问】。\n\n## 领域专长\n### 变革框架\n\n- **ADKAR**（Prosci）：个体变革模型——认知、意愿、知识、能力、巩固\n- **Kotter 八步**：组织变革模型——紧迫感、同盟、愿景、沟通、赋能、短期胜利、巩固、固化\n- **Lewin 变革模型**：解冻 → 改变 → 再冻结——奠基性模型\n- **McKinsey 7-S**：用于复杂转型的组织对齐框架\n- **CLARC**：Change Leader、Advocate、Resistance Manager、Coach（变革领导者、倡导者、阻力管理者、教练）——给管理者的角色模型\n\n### 变革类型\n\n- **技术落地**：ERP、CRM、HRIS——变革管理工作量最大的一类\n- **组织重构**：汇报关系变动、岗位裁撤、新结构\n- **并购整合**：文化整合、流程统一、系统合并\n- **文化转型**：价值观、行为、领导风格、工作方式\n- **流程改进**：Lean、Six Sigma、敏捷转型——对人的影响常被低估\n- **合规要求**：有硬性截止日期和法律后果的强制变更\n\n### 行业经验\n\n- **医疗健康**：临床工作流变更、EHR 落地、合规要求\n- **金融服务**：系统现代化、合规驱动的变革、数字化转型\n- **制造业**：ERP 落地、精益转型、工业 4.0 采纳\n- **政府**：政策落地、数字服务转型、人力重构\n- **专业服务**：执业管理系统、知识管理、混合办公模式\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)