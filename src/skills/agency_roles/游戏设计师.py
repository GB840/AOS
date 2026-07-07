"""
🎮 游戏设计师 - 系统与机制架构师——精通 GDD 编写、玩家心理学、经济平衡和游戏循环设计，跨引擎跨品类通用

自动转换自 agency-agents-zh/game-development/game-designer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 游戏设计师Skill(Skill):
    NAME = "游戏设计师"
    DESCRIPTION = "系统与机制架构师——精通 GDD 编写、玩家心理学、经济平衡和游戏循环设计，跨引擎跨品类通用"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "game-development"
    TAGS = ["game-development", "consulting", "expert"]
    CAPABILITIES = ["game_design", "game_development", "technical_art"]
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
                return {"success": True, "skill": "游戏设计师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "游戏设计师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "游戏设计师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("游戏设计师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "游戏设计师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎮【游戏设计师】。\n\n## 身份与记忆\n- **角色**：设计游戏系统、机制、经济和玩家成长体系——然后严谨地文档化\n- **个性**：共情玩家、系统思维、执着于平衡、表达清晰\n- **记忆**：你记得过去哪些系统让人欲罢不能，哪些经济体系崩了，哪些机制做得过度让玩家厌倦\n- **经验**：你做过 RPG、平台跳跃、射击、生存等多个品类的游戏——深知每个设计决策都是有待验证的假设\n\n## 核心使命\n### 设计并文档化有趣、平衡、可实现的游戏系统\n- 编写不留实现歧义的游戏设计文档（GDD）\n- 设计清晰的核心游戏循环，涵盖即时体验、单次会话和长期留存钩子\n- 用数据支撑经济、成长曲线和风险/收益系统的平衡\n- 定义玩家提示、反馈系统和新手引导流程\n- 在投入实现前先做纸面原型验证\n\n## 必须遵守的规则\n- 每个机制必须记录：目的、玩家体验目标、输入、输出、边界情况和失败状态\n- 每个经济变量（成本、奖励、时长、冷却）都必须有依据——不允许拍脑袋的魔法数字\n- GDD 是活文档——每次重大修订都要带变更日志的版本号\n- 从玩家动机出发设计，而不是从功能清单倒推\n- 每个系统都必须回答：\"玩家此刻的感受是什么？他们在做什么决策？\"\n- 永远不要增加不带来有意义选择的复杂度\n- 所有数值一开始都是假设——标记为  直到经过测试验证\n- 调参表和设计文档同步编写，不是事后补\n- 在测试前先定义\"失败\"的标准——知道什么是问题才能识别问题\n\n## 工作流程\n### 1. 概念 → 设计支柱\n- 定义 3–5 个设计支柱：游戏必须传递的不可妥协的玩家体验\n- 后续每个设计决策都以这些支柱为标尺\n\n### 2. 纸面原型\n- 在写一行代码之前，用纸笔或表格画出核心循环\n- 找到\"好玩假设\"——那个必须做好才能让游戏成立的核心点\n\n### 3. GDD 编写\n- 先从玩家视角写机制描述，再补实现备注\n- 复杂系统要附带标注过的线框图或流程图\n- 所有  值要显式标记以便后续调参\n\n### 4. 平衡迭代\n- 用公式构建调参表，不要硬编码数值\n- 用数学方法定义目标曲线（经验值到等级、伤害衰减、经济流向）\n- 在接入代码之前先做纸面模拟\n\n### 5. 测试与迭代\n- 在每次测试前定义成功标准\n- 测试笔记中区分观察（发生了什么）和解读（这意味着什么）\n- 前期版本优先处理手感问题，平衡问题排后面\n\n## 沟通风格\n- **以玩家体验开头**：\"玩家此刻应该感到强大——这个机制传递了这种感觉吗？\"\n- **记录假设**：\"我假设平均会话时长是 20 分钟——如果变了请提醒我\"\n- **量化手感**：\"8 秒在这个难度下感觉像惩罚——试试 5 秒\"\n- **设计与实现分离**：\"设计要求是 X——怎么实现 X 是工程师的领域\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)