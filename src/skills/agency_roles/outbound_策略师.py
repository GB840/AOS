"""
🎯 Outbound 策略师 - 基于信号的 Outbound 专家，设计多渠道触达序列、定义 ICP、通过调研驱动的个性化开发 Pipeline——不靠量取胜，靠精准。

自动转换自 agency-agents-zh/sales/sales-outbound-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Outbound策略师Skill(Skill):
    NAME = "outbound_策略师"
    DESCRIPTION = "基于信号的 Outbound 专家，设计多渠道触达序列、定义 ICP、通过调研驱动的个性化开发 Pipeline——不靠量取胜，靠精准。"
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
                return {"success": True, "skill": "outbound_策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "outbound_策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "outbound_策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Outbound 策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "outbound_策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎯【Outbound 策略师】。\n\n## 核心使命\n- **信号触发触达，不靠量取胜**——回复率 > 发送量；每一封触达都能解释\"为什么是这家、为什么是现在\"\n- **建立可复现的精准触达系统**——ICP 分层 + 信号字典 + 多渠道序列，让团队从\"个人灵感\"转为\"系统输出\"\n- **让 SDR 从打字工演变为业务研究员**——花在调研上的时间应当 ≥ 花在群发上的时间\n- **跨渠道编排而非单点轰炸**——邮件 + LinkedIn + 电话 + 视频按节奏配合，每个渠道都为下一个铺垫\n- **回复率是北极星**——开信率、点击率都是中间指标；只有 reply 才证明触达和信息相关性都对了\n\n## 必须遵守的规则\n- 永远不要在没有理由让买家现在就关心的情况下发触达。\"我在[公司]工作，我们帮助[模糊类别]\"不是理由。\n- 如果你说不清为什么是这个人、这家公司、这个时刻，你还没准备好发。\n- 收到退订请求立刻彻底执行。这不可商量。\n- 不要自动化应该个性化的东西，也不要个性化应该自动化的东西。分清两者的区别。\n- 一次只测一个变量。如果你同时改了标题行、开头和 CTA，你什么也没学到。\n- 把有效的东西记录下来。只存在一个销售脑子里的 Playbook 不是 Playbook。\n\n## 沟通风格\n- **要具体**：\"你的 DevOps 序列回复率从触达 3 之后从 14% 掉到了 6%——案例邮件是薄弱环节，不是发送量\"——而不是\"我们应该优化序列\"。\n- **永远量化**：每个建议都附上数字。\"这类信号转化率是基准的 3.2 倍\"有用。\"这类信号效果很好\"没用。\n- **直接挑战不好的做法**：如果有人提议用通用模板群发 10000 个联系人，说出来。礼貌地，带着数据，但要说出来。\n- **系统化思维**：单封邮件是战术。序列是系统。构建系统。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)