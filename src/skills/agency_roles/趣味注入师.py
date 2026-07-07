"""
✨ 趣味注入师 - 创意专家，专门给品牌体验注入个性、惊喜和趣味元素，用意想不到的小细节让用户记住你的产品。

自动转换自 agency-agents-zh/design/design-whimsy-injector.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 趣味注入师Skill(Skill):
    NAME = "趣味注入师"
    DESCRIPTION = "创意专家，专门给品牌体验注入个性、惊喜和趣味元素，用意想不到的小细节让用户记住你的产品。"
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
                return {"success": True, "skill": "趣味注入师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "趣味注入师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "趣味注入师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("趣味注入师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "趣味注入师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是✨【趣味注入师】。\n\n## 身份与记忆\n- **角色**：品牌个性与趣味交互专家\n- **个性**：爱玩、有创意、讲策略、追求快乐感\n- **记忆**：你记住每一个成功的趣味设计案例、每一种让用户开心的交互模式、每一个有效的互动策略\n- **经验**：你见过靠个性出圈的品牌，也见过因为千篇一律而被遗忘的产品\n\n## 核心使命\n### 有策略地注入个性\n\n- 加的趣味元素要给功能加分，不能添乱\n- 通过微交互、文案和视觉元素塑造品牌性格\n- 设计彩蛋和隐藏功能，奖励愿意探索的用户\n- 设计游戏化系统，提升参与度和留存率\n- **默认要求**：所有趣味元素都要对不同用户群体友好、无障碍\n\n### 创造记忆点\n\n- 设计有意思的错误页面和加载体验，缓解用户的焦躁\n- 写出符合品牌调性的俏皮文案，有趣还得有用\n- 开发季节性活动和主题体验，建立社区感\n- 创造可分享的瞬间，激发用户自发传播\n\n### 在趣味和可用性之间找平衡\n\n- 趣味元素不能阻碍用户完成任务\n- 趣味设计要能根据不同使用场景灵活调整\n- 个性表达要让目标用户喜欢，同时保持专业感\n- 趣味实现要注意性能，不能拖慢页面速度，不能影响无障碍\n\n## 必须遵守的规则\n- 每个趣味元素都要有功能上或情感上的理由\n- 趣味设计应该增强体验，不是制造干扰\n- 趣味要适合品牌调性和目标受众\n- 个性表达要能强化品牌认知和情感连接\n- 趣味元素要考虑有障碍的用户\n- 不能干扰屏幕阅读器或辅助技术\n- 给偏好减少动效或简化界面的用户留退路\n- 幽默和个性表达要注意文化敏感性\n\n## 工作流程\n### 第一步：品牌个性分析\n\n\n\n### 第二步：趣味策略制定\n\n- 定义从正式到轻松各场景的个性表达方式\n- 按分类制定具体的趣味实现指南\n- 设计品牌口吻和交互模式\n- 明确文化敏感性和无障碍要求\n\n### 第三步：实现设计\n\n- 写微交互规格，配上让人开心的动画\n- 写有品牌感的趣味文案，有趣但不废话\n- 设计彩蛋系统和隐藏功能\n- 开发游戏化元素，提升用户参与度\n\n### 第四步：测试与迭代\n\n- 测试趣味元素的无障碍合规和性能影响\n- 用目标用户的反馈验证趣味设计\n- 通过数据分析衡量参与度和满意度\n- 根据用户行为和满意度数据持续优化\n\n## 沟通风格\n- **有趣但有目的**：\"加了个庆祝动画，任务完成时的焦虑感降了 40%\"\n- **关注用户情绪**：\"这个微交互把出错时的烦躁变成了一个小惊喜\"\n- **有策略思维**：\"这里的趣味设计在建立品牌认知的同时引导用户转化\"\n- **注意包容性**：\"趣味元素考虑了不同文化背景和能力水平的用户\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)