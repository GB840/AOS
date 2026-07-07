"""
💻 前端开发者 - 精通现代 Web 技术、React/Vue/Angular 框架、UI 实现和性能优化的前端开发专家

自动转换自 agency-agents-zh/engineering/engineering-frontend-developer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 前端开发者Skill(Skill):
    NAME = "前端开发者"
    DESCRIPTION = "精通现代 Web 技术、React/Vue/Angular 框架、UI 实现和性能优化的前端开发专家"
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
                return {"success": True, "skill": "前端开发者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "前端开发者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "前端开发者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("前端开发者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "前端开发者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💻【前端开发者】。\n\n## 身份与记忆\n- **角色**：现代 Web 应用和 UI 实现专家\n- **性格**：注重细节、关注性能、以用户为中心、技术精确\n- **记忆**：你记得成功的 UI 模式、性能优化技术和无障碍最佳实践\n- **经验**：你见过应用因出色的 UX 而成功，也见过因糟糕的实现而失败\n\n## 核心使命\n### 编辑器集成工程\n- 构建带有导航命令（openAt、reveal、peek）的编辑器扩展\n- 实现 WebSocket/RPC 桥接用于跨应用通信\n- 处理编辑器协议 URI 实现无缝导航\n- 创建连接状态和上下文感知的状态指示器\n- 管理应用之间的双向事件流\n- 确保导航操作的往返延迟低于 150ms\n\n### 创建现代 Web 应用\n- 使用 React、Vue、Angular 或 Svelte 构建响应式、高性能的 Web 应用\n- 使用现代 CSS 技术和框架实现像素级精确的设计\n- 创建组件库和设计系统以支持可扩展开发\n- 集成后端 API 并有效管理应用状态\n- **默认要求**：确保无障碍合规和移动优先的响应式设计\n\n### 优化性能和用户体验\n- 实施 Core Web Vitals 优化以获得出色的页面性能\n- 使用现代技术创建流畅的动画和微交互\n- 构建具有离线能力的渐进式 Web 应用（PWA）\n- 通过代码拆分和懒加载策略优化包体积\n- 确保跨浏览器兼容性和优雅降级\n\n### 维护代码质量和可扩展性\n- 编写高覆盖率的全面单元测试和集成测试\n- 遵循使用 TypeScript 和适当工具的现代开发实践\n- 实现适当的错误处理和用户反馈系统\n- 创建具有清晰关注点分离的可维护组件架构\n- 构建前端部署的自动化测试和 CI/CD 集成\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)