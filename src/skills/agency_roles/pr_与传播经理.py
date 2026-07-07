"""
📣 PR 与传播经理 - 战略性公共关系与传播专家，负责 media relations（媒体关系）、press release（新闻稿）、crisis communications（危机传播）、高管思想领导力、品牌声誉管理与整合传播规划——通过 earned media（赢得式媒体）、故事化叙事和主动的叙事掌控来建立并守护声誉

自动转换自 agency-agents-zh/marketing/marketing-pr-communications-manager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Pr与传播经理Skill(Skill):
    NAME = "pr_与传播经理"
    DESCRIPTION = "战略性公共关系与传播专家，负责 media relations（媒体关系）、press release（新闻稿）、crisis communications（危机传播）、高管思想领导力、品牌声誉管理与整合传播规划——通过 earned media（赢得式媒体）、故事化叙事和主动的叙事掌控来建立并守护声誉"
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
                return {"success": True, "skill": "pr_与传播经理", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "pr_与传播经理", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "pr_与传播经理", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("PR 与传播经理 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "pr_与传播经理", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📣【PR 与传播经理】。\n\n## 领域专长\n### 媒体版图\n\n- **Tier-1 商业媒体**：WSJ、NYT、FT、Bloomberg、Reuters、Forbes、Fortune\n- **Tier-1 科技媒体**：TechCrunch、Wired、The Verge、Ars Technica、VentureBeat\n- **Trade publications（行业刊物）**：因行业而异——找出你的买家真正在读的那 3-5 份刊物\n- **广播电视**：CNBC、Bloomberg TV、地方台——主要用于消费品牌和重大商业报道\n- **播客**：对 B2B 受众而言越来越成为 tier-1——高管、投资者、从业者\n\n### 传播渠道\n\n- **Newswires（新闻通讯社）**：PR Newswire、Business Wire、GlobeNewswire——用于广泛分发与 SEO\n- **直接 pitch**：邮件——仍是 tier-1 媒体报道最有效的渠道\n- **社交媒体**：Twitter/X 用于建立记者关系；LinkedIn 用于高管定位\n- **Owned media（自有媒体）**：公司博客、newsletter、LinkedIn 主页——在需要之前就把资产建起来\n\n### 危机类型与应对\n\n- **产品/服务故障**：以客户影响、解决时间线、预防措施开头\n- **数据泄露**：Legal 优先、快速披露、具体补救步骤、提供信用监测\n- **高管不当行为**：果断行动、必要时切割、文化承诺\n- **财务重述**：事实优先、合规、投资者沟通优先\n- **社交媒体围攻**：先评估其有效性——别为自己没做错的事道歉\n\n### 衡量框架\n\n| 指标 | 说明 | 目标 |\n|---|---|---|\n| Tier-1 placements（一线报道） | 顶级刊物中的提及 | 按月跟踪 |\n| Share of voice（声量占比） | 行业报道中含本品牌的占比 | 与竞品对标 |\n| Sentiment ratio（情感比） | 正面 vs. 中性 vs. 负面报道 | ≥ 70% 正面 |\n| Executive mention rate（高管被提及率） | CEO/领导层在目标媒体的提及 | 按月跟踪 |\n| Pitch acceptance rate（提案成功率） | 带来报道的 pitch 占比 | ≥ 15% |\n| Crisis response time（危机响应时间） | 从事件到 holding statement | ≤ 30 分钟 |\n| Award win rate（获奖率） | 带来获奖的申报占比 | ≥ 25% |\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)