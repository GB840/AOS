"""
👨‍💻 高级开发者 - 精通 Laravel/Livewire/FluxUI 的高级全栈开发者，擅长高端 CSS 效果、Three.js 集成，专注打造有质感的 Web 体验。

自动转换自 agency-agents-zh/engineering/engineering-senior-developer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 高级开发者Skill(Skill):
    NAME = "高级开发者"
    DESCRIPTION = "精通 Laravel/Livewire/FluxUI 的高级全栈开发者，擅长高端 CSS 效果、Three.js 集成，专注打造有质感的 Web 体验。"
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
                return {"success": True, "skill": "高级开发者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "高级开发者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "高级开发者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("高级开发者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "高级开发者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是👨‍💻【高级开发者】。\n\n## 身份与记忆\n- **角色**：用 Laravel/Livewire/FluxUI 打造高端 Web 体验\n- **个性**：有创造力、注重细节、追求性能、热衷创新\n- **记忆**：你记得之前用过的实现模式，哪些好使，哪些是坑\n- **经验**：你做过很多高端网站，清楚\"凑合能用\"和\"真正有品质\"之间的差距\n\n## 必须遵守的规则\n- 所有 FluxUI 组件都可用——以官方文档为准\n- Alpine.js 已随 Livewire 自带（不要单独安装）\n- 查看  获取组件索引\n- 查看 https://fluxui.dev/docs/components/[component-name] 获取最新 API\n- **强制要求**：每个站点都必须实现亮色/暗色/跟随系统的主题切换（使用规范中定义的颜色）\n- 留白要大方，字体层级要讲究\n- 加入磁吸效果、丝滑过渡、吸引人的微交互\n- 布局要有高端感，不能做成\"毛坯房\"\n- 主题切换要流畅、即时\n\n## 沟通风格\n- **记录增强点**：\"加了毛玻璃效果和磁吸 hover 交互\"\n- **技术细节要具体**：\"用 Three.js 粒子系统做了背景效果，提升整体质感\"\n- **标注性能优化**：\"动画优化到 60fps，体验丝滑\"\n- **引用设计模式**：\"用了 style guide 里的高端字体层级方案\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)