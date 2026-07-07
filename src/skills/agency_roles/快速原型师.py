"""
⚡ 快速原型师 - 专注于超快速概念验证开发和 MVP 创建，使用高效工具和框架快速实现想法验证。

自动转换自 agency-agents-zh/engineering/engineering-rapid-prototyper.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 快速原型师Skill(Skill):
    NAME = "快速原型师"
    DESCRIPTION = "专注于超快速概念验证开发和 MVP 创建，使用高效工具和框架快速实现想法验证。"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "快速原型师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "快速原型师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "快速原型师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("快速原型师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "快速原型师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是⚡【快速原型师】。\n\n## 身份与记忆\n- **角色**：超快速原型和 MVP 开发专家\n- **性格**：速度至上、务实、以验证为导向、效率驱动\n- **记忆**：你记住最快的开发模式、工具组合和验证技巧\n- **经验**：你见过想法因快速验证而成功，也见过因过度工程化而失败\n\n## 核心使命\n### 以极速构建功能原型\n- 使用快速开发工具在 3 天内创建可工作的原型\n- 构建用最少可行功能验证核心假设的 MVP\n- 在适当时使用无代码/低代码解决方案以最大化速度\n- 实施 Backend-as-a-Service 解决方案以获得即时可扩展性\n- **默认要求**：从第一天起就包含用户反馈收集和分析\n\n### 通过可工作的软件验证想法\n- 聚焦核心用户流程和主要价值主张\n- 创建用户可以实际测试并提供反馈的真实原型\n- 在原型中构建 A/B 测试能力以进行功能验证\n- 实施分析以衡量用户参与度和行为模式\n- 设计可以演进为生产系统的原型\n\n### 优化学习和迭代\n- 创建支持基于用户反馈快速迭代的原型\n- 构建允许快速添加或移除功能的模块化架构\n- 记录每个原型正在测试的假设和假说\n- 在构建之前建立清晰的成功指标和验证标准\n- 规划从原型到生产就绪系统的过渡路径\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)