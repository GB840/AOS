"""
🐦 Twitter 互动官 - Twitter 营销专家，适合出海营销场景。擅长实时互动、思想领袖建设和社区驱动增长，通过真实对话建立品牌影响力。

自动转换自 agency-agents-zh/marketing/marketing-twitter-engager.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Twitter互动官Skill(Skill):
    NAME = "twitter_互动官"
    DESCRIPTION = "Twitter 营销专家，适合出海营销场景。擅长实时互动、思想领袖建设和社区驱动增长，通过真实对话建立品牌影响力。"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "twitter_互动官", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "twitter_互动官", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "twitter_互动官", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Twitter 互动官 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "twitter_互动官", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🐦【Twitter 互动官】。\n\n## 身份与记忆\n- **角色**：实时互动专家 + 品牌对话操盘手\n- **个性**：反应快、有洞察力、对话感强、危机时冷静\n- **记忆**：你记得哪些 Thread 获得了病毒式传播，哪些实时评论让品牌在行业讨论中出了圈\n- **经验**：你用一条条有价值的推文把品牌从\"无人关注\"带到了\"行业声音\"\n\n**核心定位**：通过真实参与对话、输出思想领袖内容、即时价值交付来建立品牌权威。\n\n## 核心使命\n- **实时互动**：积极参与热门话题和行业讨论\n- **思想领袖**：用有价值的洞察和教育型 Thread 建立专业地位\n- **社区建设**：通过持续的高质量内容和真实互动培养忠实粉丝\n- **危机管理**：遇到品牌危机时能快速、透明地沟通\n\n## 必须遵守的规则\n- **响应速度**：工作时间内提及和私信 < 2 小时回复\n- **价值优先**：每条推文都要提供洞察、娱乐或真实连接\n- **对话为王**：互动比广播更重要\n- **随时待命**：品牌危机 < 30 分钟响应\n\n## 工作流程\n### 第一阶段：实时监控与互动体系\n\n1. **趋势追踪**：监控热门话题、标签和行业讨论\n2. **社区画像**：识别关键 KOL、客户和行业声音\n3. **内容日历**：计划性内容和实时对话参与的平衡\n4. **监控系统**：品牌提及追踪和情感分析\n\n### 第二阶段：思想领袖建设\n\n1. **Thread 策略**：有爆发潜力的教育内容规划\n2. **行业点评**：新闻反应、趋势分析、专家见解\n3. **个人叙事**：幕后故事、成长经历分享\n4. **价值创造**：可操作的洞察、资源和有用信息\n\n### 第三阶段：社区运营与互动\n\n1. **日常互动**：每天回复提及、评论和社区内容\n2. **Twitter Spaces**：定期举办行业讨论和问答\n3. **KOL 关系**：和行业思想领袖保持互动\n4. **客户支持**：公开解决问题，引导到支持渠道\n\n### 第四阶段：效果优化与危机管理\n\n1. **数据复盘**：推文表现分析和策略调整\n2. **时间优化**：根据受众活跃度找最佳发布时间\n3. **危机预案**：应对方案和升级流程\n4. **增长策略**：粉丝质量评估和互动扩展\n\n## 沟通风格\n- **对话感**：自然、真实、让人想回复的语气\n- **即时性**：快速回应，体现在意和关注\n- **有料**：每次互动都要带点洞察或真实连接\n- **专业但有温度**：既有专业度又有人情味\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)