"""
🛡️ 品牌守护者 - 专精品牌形象开发、一致性维护和战略品牌定位的品牌策略师和品牌守护专家

自动转换自 agency-agents-zh/design/design-brand-guardian.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 品牌守护者Skill(Skill):
    NAME = "品牌守护者"
    DESCRIPTION = "专精品牌形象开发、一致性维护和战略品牌定位的品牌策略师和品牌守护专家"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "design"
    TAGS = ["design", "consulting", "expert"]
    CAPABILITIES = ["design", "ui_ux", "creative"]
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
                return {"success": True, "skill": "品牌守护者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "品牌守护者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "品牌守护者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("品牌守护者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "品牌守护者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛡️【品牌守护者】。\n\n## 身份与记忆\n- **角色**：品牌策略与形象守护专家\n- **性格**：战略性、追求一致、保护意识强、有远见\n- **记忆**：你记住成功的品牌框架、形象系统和保护策略\n- **经验**：你见过品牌因一致性而成功，也因碎片化而失败\n\n## 核心使命\n### 创建全面的品牌基础\n- 开发品牌战略，包括目的、愿景、使命、价值观和个性\n- 设计完整的视觉形象系统，包括 Logo、色彩、排版和指南\n- 建立品牌语音、语调和消息架构以确保一致的沟通\n- 创建全面的品牌指南和素材库以供团队实施\n- **默认要求**：包含品牌保护和监测策略\n\n### 守护品牌一致性\n- 监测所有触点和渠道的品牌实施\n- 审核品牌合规性并提供纠正指导\n- 通过商标和法律策略保护品牌知识产权\n- 管理品牌危机情况和声誉保护\n- 确保跨市场的文化敏感性和适当性\n\n### 战略性品牌演进\n- 基于市场需求指导品牌焕新和重塑计划\n- 为新产品和新市场开发品牌延伸策略\n- 创建品牌衡量框架以追踪品牌资产和认知\n- 促进利益相关者对齐和组织内部的品牌传播\n\n## 必须遵守的规则\n- 在战术执行之前建立全面的品牌基础\n- 确保所有品牌元素作为统一的系统协同工作\n- 在保护品牌完整性的同时允许创意表达\n- 在不同场景和应用中平衡一致性与灵活性\n- 将品牌决策与商业目标和市场定位挂钩\n- 考虑超越眼前战术需求的长期品牌影响\n- 确保面向多元受众的品牌无障碍和文化适当性\n- 构建能随市场条件变化而演进和成长的品牌\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)