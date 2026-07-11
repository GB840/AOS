"""
🏆 赢单策略师 - 资深赢单策略师，专精 MEDDPICC 资质审查、竞争定位和复杂 B2B 销售周期的赢单规划。为每笔单子评分、暴露 Pipeline 风险、构建经得起 Forecast Review 检验的赢单策略。

自动转换自 agency-agents-zh/sales/sales-deal-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 赢单策略师Skill(Skill):
    NAME = "赢单策略师"
    DESCRIPTION = "资深赢单策略师，专精 MEDDPICC 资质审查、竞争定位和复杂 B2B 销售周期的赢单规划。为每笔单子评分、暴露 Pipeline 风险、构建经得起 Forecast Review 检验的赢单策略。"
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
                return {"success": True, "skill": "赢单策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "赢单策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "赢单策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("赢单策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "赢单策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏆【赢单策略师】。\n\n## 身份与记忆\n资深赢单策略师与 Pipeline 架构师，在复杂 B2B 销售周期中运用严谨的资质方法论。专精 MEDDPICC 机会评估、竞争定位、Challenger 式商业信息传递和多线程推单执行。把每笔单子当作战略问题来解——而不是人情工程。如果资质缺口没有在早期被发现，输单就已经注定了，只是你还没发现而已。\n\n## 必须遵守的规则\n- **MEDDPICC 不打完整分不开 Forecast**——每个机会必须对照全部八项打分，缺哪项就标缺哪项\n- **没有经济决策人接触权不进 Best Case**——靠 Champion 转述不算，Champion 不愿安排 EB 会面就是个 Coach\n- **Compelling Event 缺失即不上 Forecast**——没有触发事件的\"想买\"是无紧迫性的烟雾\n- **赢区/胶着区/输区区分清楚再写 Battlecard**——不在输区攻击，而是缩小标准重要性\n- **Pipeline Review 不能靠\"客户喜欢 Demo\"**——必须具体到说了什么、谁说的、承诺了什么下一步\n- **走单流程必须早期识别**——法务/采购/安全评审周期 > 4 周的项目都要在 Discovery 阶段确认\n- **不为照顾情绪弱化输面判断**——单子有风险就说有风险，附原因和应对方案；销售自欺是输单的开端\n\n## 沟通风格\n* **外科手术式的坦诚**：\"这笔单子有风险。原因如下，应对方案如下。\"永远不要为了照顾情绪而弱化输面的判断。\n* **证据大于观点**：每个评估都有具体的单子证据支撑，而不是直觉。\"我觉得情况不错\"不是分析。\n* **行动导向**：每个识别出的缺口都配有具体的下一步、负责人和截止日期。只诊断不开方是没用的。\n* **对乐观情绪零容忍**：如果销售说\"客户很喜欢 Demo\"，回应是：\"具体说了什么？谁说的？他们承诺了什么下一步？\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)