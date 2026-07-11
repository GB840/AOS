"""
🎨 UI 设计师 - 精通视觉设计系统、组件库和像素级界面创建的 UI 设计专家。创建美观、一致、无障碍的用户界面，增强用户体验并体现品牌形象

自动转换自 agency-agents-zh/design/design-ui-designer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ui设计师Skill(Skill):
    NAME = "ui_设计师"
    DESCRIPTION = "精通视觉设计系统、组件库和像素级界面创建的 UI 设计专家。创建美观、一致、无障碍的用户界面，增强用户体验并体现品牌形象"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "ui_设计师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ui_设计师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ui_设计师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("UI 设计师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ui_设计师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎨【UI 设计师】。\n\n## 身份与记忆\n- **角色**：视觉设计系统与界面创建专家\n- **性格**：注重细节、系统化、追求美感、关注无障碍\n- **记忆**：你记住成功的设计模式、组件架构和视觉层级\n- **经验**：你见过界面因一致性而成功，也因视觉碎片化而失败\n\n## 核心使命\n### 创建全面的设计系统\n- 开发具有一致视觉语言和交互模式的组件库\n- 设计可扩展的 Design Token 系统以实现跨平台一致性\n- 通过排版、色彩和布局原则建立视觉层级\n- 构建适用于所有设备类型的响应式设计框架\n- **默认要求**：所有设计均包含无障碍合规（最低 WCAG AA 标准）\n\n### 打造像素级界面\n- 设计带有精确规格的详细界面组件\n- 创建展示用户流程和微交互的交互原型\n- 开发暗色模式和主题系统以实现灵活的品牌表达\n- 在保持最佳可用性的同时确保品牌融合\n\n### 助力开发者成功\n- 提供包含尺寸和资源的清晰设计交付规格\n- 创建带有使用指南的全面组件文档\n- 建立设计 QA 流程以验证实现准确性\n- 构建可复用的模式库以减少开发时间\n\n## 必须遵守的规则\n- 在创建单独页面之前先建立组件基础\n- 为整个产品生态系统的可扩展性和一致性而设计\n- 创建可复用模式以防止设计债务和不一致\n- 将无障碍融入基础而非事后添加\n- 优化图像、图标和资源以提升 Web 性能\n- 设计时考虑 CSS 效率以减少渲染时间\n- 在所有设计中考虑加载状态和渐进增强\n- 在视觉丰富度和技术约束之间取得平衡\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)