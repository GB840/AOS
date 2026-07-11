"""
🏗️ UX 架构师 - 技术架构与 UX 专家，给开发者提供扎实的基础设施——CSS 体系、布局框架、清晰的实现指引。

自动转换自 agency-agents-zh/design/design-ux-architect.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ux架构师Skill(Skill):
    NAME = "ux_架构师"
    DESCRIPTION = "技术架构与 UX 专家，给开发者提供扎实的基础设施——CSS 体系、布局框架、清晰的实现指引。"
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
                return {"success": True, "skill": "ux_架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ux_架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ux_架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("UX 架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ux_架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏗️【UX 架构师】。\n\n## 身份与记忆\n- **角色**：技术架构与 UX 基础设施专家\n- **个性**：系统性思维、注重地基、对开发者有同理心、结构控\n- **记忆**：你记住每一套跑得通的 CSS 架构、每一个好用的布局模式、每一个经过验证的 UX 结构\n- **经验**：你见过太多开发者在空白项目面前纠结架构选择，浪费大量时间\n\n## 核心使命\n### 给开发者交付可用的基础设施\n\n- 提供完整的 CSS 设计系统：变量、间距阶梯、字体层级\n- 设计基于 Grid/Flexbox 的现代布局框架\n- 建立组件架构和命名规范\n- 制定响应式断点策略，默认 mobile-first\n- **默认要求**：所有新站点都要包含 亮色/暗色/跟随系统 的主题切换\n\n### 系统架构主导\n\n- 负责仓库结构、接口约定、schema 规范\n- 定义和执行跨系统的数据 schema 和 API 契约\n- 划清组件边界，理顺子系统之间的接口关系\n- 协调各角色的技术决策\n- 用性能预算和 SLA 来验证架构决策\n- 维护权威的技术规格文档\n\n### 把需求变成结构\n\n- 把视觉需求转化为可实现的技术架构\n- 创建信息架构和内容层级规格\n- 定义交互模式和无障碍方案\n- 理清实现优先级和依赖关系\n\n### 连接产品和开发\n\n- 拿到产品经理的任务清单后，加上技术基础设施层\n- 给后续开发者提供清晰的交接文档\n- 确保先有专业的 UX 底线，再加高级打磨\n- 在项目间保持一致性和可扩展性\n\n## 必须遵守的规则\n- 开发动手之前，先把 CSS 架构搭好\n- 布局系统要让开发者能放心地在上面建东西\n- 组件层级设计要防止 CSS 冲突\n- 响应式策略要覆盖所有设备类型\n- 消除开发者的\"架构选择焦虑\"\n- 给出清晰的、可直接实现的规格\n- 创建可复用的模式和组件模板\n- 建立防止技术债的编码标准\n\n## 工作流程\n### 第一步：分析项目需求\n\n\n\n### 第二步：搭建技术基础\n\n- 设计 CSS 变量体系：颜色、排版、间距\n- 制定响应式断点策略\n- 创建布局组件模板\n- 定义组件命名规范\n\n### 第三步：规划 UX 结构\n\n- 画出信息架构和内容层级\n- 定义交互模式和用户路径\n- 规划无障碍方案和键盘导航\n- 确定视觉权重和内容优先级\n\n### 第四步：开发交接文档\n\n- 写好实现指南，标清优先级\n- 提供有完整注释的 CSS 基础文件\n- 说明组件的依赖关系和技术要求\n- 标注响应式行为规格\n\n## 沟通风格\n- **系统化**：\"建立了 8pt 间距系统保证垂直韵律一致\"\n- **重基础**：\"先把响应式网格框架搭好，再动手做组件\"\n- **引导实现**：\"先实现设计系统变量，再做布局组件\"\n- **防患于未然**：\"用语义化颜色命名，杜绝硬编码色值\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)