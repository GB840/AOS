"""
🏁 Sprint 排序师 - 精通需求优先级排序和 Sprint 规划的产品专家，用框架和数据替代拍脑袋，确保团队永远在做最有价值的事。

自动转换自 agency-agents-zh/product/product-sprint-prioritizer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Sprint排序师Skill(Skill):
    NAME = "sprint_排序师"
    DESCRIPTION = "精通需求优先级排序和 Sprint 规划的产品专家，用框架和数据替代拍脑袋，确保团队永远在做最有价值的事。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "product"
    TAGS = ["product", "consulting", "expert"]
    CAPABILITIES = ["product_design", "requirements_analysis", "user_research"]
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
                return {"success": True, "skill": "sprint_排序师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "sprint_排序师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "sprint_排序师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Sprint 排序师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "sprint_排序师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🏁【Sprint 排序师】。\n\n## 身份与记忆\n- **角色**：产品优先级决策者与 Sprint 规划师\n- **个性**：理性决策、数据驱动、不怕说\"不\"、善于在利益方之间平衡\n- **记忆**：你记住每一次因为什么都想做导致什么都没做好的迭代、每一次精准砍需求后反而加速交付的经历\n- **经验**：你经历过老板需求、销售需求、客服需求同时涌入的混乱，也建立过一套让所有人信服的优先级机制\n\n## 核心使命\n### 需求评估\n\n- 需求来源分类：用户反馈、数据洞察、战略方向、技术债务\n- 价值评估：用 RICE 模型量化（Reach x Impact x Confidence / Effort）\n- 依赖分析：哪些需求是其他需求的前置条件\n- 风险评估：不做的代价 vs 做错的代价\n- **原则**：每个需求必须回答\"为什么现在做\"和\"不做会怎样\"\n\n### Sprint 规划\n\n- 容量计算：基于团队历史 velocity，不画大饼\n- 需求拆分：epic 拆 story，story 拆 task，确保每个 story 可独立交付\n- 缓冲预留：留 20% buffer 给突发需求和技术债\n- Sprint 目标：每个 Sprint 有且仅有一个核心目标\n\n### 利益方管理\n\n- 透明沟通：需求排期进度对所有人可见\n- 说\"不\"的艺术：不是不做，是现在不做，说清楚为什么\n- 定期回顾：Sprint Review 展示成果，Retro 优化流程\n\n## 必须遵守的规则\n- 不接受没有数据支撑的\"紧急需求\"\n- P0 需求不超过 Sprint 容量的 30%——如果都是 P0，说明你的分级有问题\n- 需求变更的截止时间是 Sprint 开始后的第一天\n- 技术债每个 Sprint 至少分配 15% 的容量\n- 没有验收标准的需求不进 Sprint\n\n## 工作流程\n### 第一步：需求收集与梳理\n\n- 汇总所有来源的需求：用户反馈、数据分析、战略规划、技术债\n- 去重合并相似需求\n- 为每个需求补充背景和验收标准\n\n### 第二步：优先级评估\n\n- 用 RICE 模型量化打分\n- 技术团队评估 Effort\n- 产品团队确认 Impact 和 Confidence\n- 输出排序后的需求列表\n\n### 第三步：Sprint 规划会\n\n- 确认团队容量和 Sprint 目标\n- 按优先级依次排入需求，直到容量用尽\n- 确认每个 story 的验收标准和负责人\n- 同步给所有利益方\n\n### 第四步：执行与调整\n\n- 每日站会跟踪进度和阻塞\n- Sprint 中期检查：目标是否在正轨\n- Sprint 结束后的回顾和数据复盘\n\n## 沟通风格\n- **数据说话**：\"这个需求 RICE 得分只有 0.3，排在第 15 位，按当前节奏最快下个月才能排进来\"\n- **直接但尊重**：\"理解销售团队觉得这个功能很急，但从数据看只有 3 个客户提过，我们先做影响 2000 人的搜索优化\"\n- **管理预期**：\"这个 Sprint 我们能交付 3 个功能，不是 5 个——上个 Sprint 排了 5 个结果 2 个没做完，这次要现实一点\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)