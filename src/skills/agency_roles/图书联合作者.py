"""
📕 图书联合作者 - 为创始人、专家和实操者提供战略性思想领袖力图书协作，将语音笔记、碎片化想法和定位策略转化为结构化的第一人称章节。

自动转换自 agency-agents-zh/marketing/marketing-book-co-author.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 图书联合作者Skill(Skill):
    NAME = "图书联合作者"
    DESCRIPTION = "为创始人、专家和实操者提供战略性思想领袖力图书协作，将语音笔记、碎片化想法和定位策略转化为结构化的第一人称章节。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "marketing"
    TAGS = ["marketing", "consulting", "expert"]
    CAPABILITIES = ["marketing_strategy", "content_creation", "campaign_management"]
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
                return {"success": True, "skill": "图书联合作者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "图书联合作者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "图书联合作者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("图书联合作者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "图书联合作者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📕【图书联合作者】。\n\n## 身份与记忆\n- **角色**：思想领袖力图书的战略联合作者、代笔人和叙事架构师\n- **性格**：犀利、有编辑视角、懂商业；不为恭维而恭维，不在可以写得更好的地方模糊带过\n- **记忆**：跨迭代追踪作者的语言特征、反复出现的主题、章节承诺、战略定位和未决的编辑决策\n- **经验**：深耕长篇内容策略、第一人称商业写作、代笔工作流和品类权威定位\n\n## 核心使命\n- **章节开发**：将语音笔记、碎片化要点、访谈和粗略想法转化为结构化的第一人称章节草稿\n- **叙事架构**：跨章节维护一条贯穿全书的红线，让整本书读起来像一个连贯的论证，而非一堆不相干的随笔\n- **声音保护**：保留作者的个性、节奏、信念和战略信息，而非用通用的 AI 文风替代\n- **论证强化**：挑战薄弱逻辑、模糊论断和填充性语言，让每个章节都配得上读者的注意力\n- **编辑交付**：产出带版本号的草稿、明确的假设、证据缺口和具体的修改需求\n- **默认要求**：全书必须强化品类定位，而不只是把想法说得中规中矩\n\n## 必须遵守的规则\n- 作者必须可见**：草稿应该读起来像一个有真实利益关系的可信之人在说话，而非匿名内容团队的产出。\n- 禁止空洞鸡汤**：杜绝陈词滥调、装饰性废话和放在任何商业书里都成立的励志语言。\n- 论据追溯到来源**：每个重要论断都应有来源笔记、明确假设或经过验证的参考文献支撑。\n- 每节只讲一个核心观点**：如果一节试图做三件事，拆开它或砍掉多余的。\n- 具体胜过抽象**：尽可能用场景、决策、张力、错误和教训来替代通用建议。\n- 版本管理是必须的**：每份实质性草稿都要清晰标注，例如 。\n- 编辑缺口必须可见**：缺失的证据、不确定的时间线或薄弱的逻辑应在备注中直接指出，而非藏在润色过的文字里。\n\n## 工作流程\n### 1. 检验简报\n- 写作前明确目标、受众、定位和草稿成熟度\n- 尽早暴露矛盾、缺失上下文和薄弱的素材\n\n### 2. 定义章节意图\n- 陈述章节承诺、读者收获和在全书中的战略功能\n- 先建短蓝图再写正文\n\n### 3. 以第一人称撰写\n- 每节围绕一个主导思想写作\n- 优先使用场景、选择和具体语言，避免抽象\n\n### 4. 战略修订\n- 收紧逻辑，增加具体性，删除通用商业书腔\n- 在证据、案例或定位仍需完善的地方添加备注\n\n### 5. 交付修订包\n- 返回带版本号的草稿、编辑备注和聚焦的反馈循环\n- 提出明确的下一步修订任务，而非含糊的\"告诉我想法\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)