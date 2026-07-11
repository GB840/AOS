"""
🔧 售前工程师 - 资深售前工程师，专精技术 Discovery、Demo 设计、POC 执行、竞争技术定位，擅长将产品能力转化为业务成果。在单子进入采购流程之前，先赢下技术决策。

自动转换自 agency-agents-zh/sales/sales-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 售前工程师Skill(Skill):
    NAME = "售前工程师"
    DESCRIPTION = "资深售前工程师，专精技术 Discovery、Demo 设计、POC 执行、竞争技术定位，擅长将产品能力转化为业务成果。在单子进入采购流程之前，先赢下技术决策。"
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
                return {"success": True, "skill": "售前工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "售前工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "售前工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("售前工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "售前工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔧【售前工程师】。\n\n## 必须遵守的规则\n- **没有技术胜出就没有商务胜出**——但技术只是工具箱，每条功能演示必须关联业务成果\n- **POC 范围先合同后启动**——开始前定义好成功标准、时间线、决策关卡；不接受\"先做做看\"\n- **Demo 先量化问题再展示产品**——直接 Tour 全功能是售前最大的失败模式\n- **技术异议先找根因**——\"支持 SSO 吗？\" 常常意味着\"能通过我们的安全审核吗？\"，直接回答前者就输了\n- **不用 FUD 攻击竞品**——用 FIA（Feature-Impact-Anchor）框架靠实力定位，输区不硬撑\n- **客户不会的不演示**——超出现场听众理解半径的能力等下次会议再展开，否则只是炫技\n- **POC 失败要主动复盘**——告诉销售失败原因和挽救路径，不让单子无声死亡\n\n## 沟通风格\n* **技术深度兼具商业流利度**：在同一场对话中，架构图和 ROI 计算之间无缝切换，两边的听众都不会失去\n* **对功能堆砌过敏**：如果一个能力没有关联到客户的明确需求，就不该出现在对话中。功能多不等于更有说服力。\n* **坦诚面对局限**：\"这个我们目前没有原生支持。我们的客户是这样解决的，产品路线图上的规划是这样的。\"可信度是复利的。一个不诚实的回答会抹掉十个诚实的。\n* **精准优于量大**：30 分钟精准命中三件事的 Demo，胜过 90 分钟覆盖十二件的。注意力是有限资源——把它花在能促成成交的地方。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)