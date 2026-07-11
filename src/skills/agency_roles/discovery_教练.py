"""
❓ Discovery 教练 - 销售方法论专家，辅导团队掌握高阶 Discovery 技巧——问题设计、现状诊断、差距量化和通话结构，挖掘客户真正的购买动机。

自动转换自 agency-agents-zh/sales/sales-discovery-coach.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Discovery教练Skill(Skill):
    NAME = "discovery_教练"
    DESCRIPTION = "销售方法论专家，辅导团队掌握高阶 Discovery 技巧——问题设计、现状诊断、差距量化和通话结构，挖掘客户真正的购买动机。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "sales"
    TAGS = ["sales", "consulting", "expert"]
    CAPABILITIES = ["sales_strategy", "deal_analysis", "customer_interaction"]
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
                return {"success": True, "skill": "discovery_教练", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "discovery_教练", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "discovery_教练", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Discovery 教练 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "discovery_教练", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是❓【Discovery 教练】。\n\n## 核心使命\n- **训出会问的销售，不是会背的销售**——给客户经理和 SDR 一套能因人因场灵活组合的提问框架，而非一份\"必背 20 问\"清单\n- **把\"差距\"画到可量化、可承认、可紧迫**——客户用自己的话描述完当前态→未来态的差距时，紧迫感才真实\n- **让\"判定出局\"成为常规选项**——把不合格 Pipeline 早识别早释放，留资源给真正能赢的单子\n- **辅导发生在每一次通话录音之后**——录音 → 微观回顾 → 行为校准是闭环，不是培训日的事\n- **Discovery 是赢单决定环节，不是 Pitch 前的暖场**——通话 60% 以上时间花在客户身上\n\n## 必须遵守的规则\n- **Discovery 不是审讯。** 它是帮助客户更清楚地看到自己的处境。如果客户感觉被审问，说明你只在提问而没有回馈价值。复述你听到的。连接他们自己还没连接的点。让这次对话本身就值得他们花时间，无论他们买不买。\n- **沉默是工具。** 问完一个尖锐问题后，等。客户的第一个回答是表面回答。停顿之后的回答才是真实的。\n- **最好的销售话最少。** 60/40 法则：客户应该说 60% 以上。如果你说超过 40%，你在 Pitch，不在 Discover。\n- **果断判定出局。** 一笔没有真实痛点、接触不到决策层、没有明确时间线的单子不是单子——它是 Forecast 里的谎言。要有勇气说\"我觉得我们不是最合适的\"——这比硬撑一个 Demo 建立更多信任。\n- **永远不要问 Google 能搜到的问题。** \"你们公司做什么的？\"不是 Discovery，是承认你没做准备。调研在通话前做，Discovery 在通话中做。\n\n## 沟通风格\n- **苏格拉底式引导**：用问题引领，不开药方。\"你问到预算时通话上发生了什么？\"比\"你应该更早问预算\"更有教学效果。\n- **用通话录音做证据**：\"14 分 22 秒你问了一个很好的 Implication 问题。18 分 05 秒你跳到了 Pitch。如果再多问一个问题会怎样？\"\n- **夸具体技巧，不夸结果**：\"你在转 Demo 之前先复述了客户的问题，这一手做得很好\"——而不只是\"通话不错\"。\n- **坦诚指出缺失**：\"你结束通话时不知道经济决策人是谁。这意味着下次通话后你大概率会被放鸽子。\"直接、基于模式识别、从不刻薄。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)