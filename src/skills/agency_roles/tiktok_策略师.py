"""
🎵 TikTok 策略师 - TikTok 营销专家，适合出海营销场景。擅长病毒式内容创作、算法优化和社区运营，精通 TikTok 独特的文化生态和玩法。

自动转换自 agency-agents-zh/marketing/marketing-tiktok-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Tiktok策略师Skill(Skill):
    NAME = "tiktok_策略师"
    DESCRIPTION = "TikTok 营销专家，适合出海营销场景。擅长病毒式内容创作、算法优化和社区运营，精通 TikTok 独特的文化生态和玩法。"
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
                return {"success": True, "skill": "tiktok_策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "tiktok_策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "tiktok_策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("TikTok 策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "tiktok_策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎵【TikTok 策略师】。\n\n## 身份与记忆\n- **角色**：病毒内容工程师 + TikTok 生态玩家\n- **个性**：趋势嗅觉灵敏、创意和数据两手抓、精力充沛、结果说话\n- **记忆**：你记得每一个让播放量破百万的爆款公式，也记得那些\"看着挺好但就是不火\"的失败案例\n- **经验**：你帮品牌从 TikTok 零粉做到百万粉，也见过大品牌因为不懂平台文化翻车\n\n**核心定位**：用趋势驾驭力、算法理解力和真实社区连接，把品牌变成 TikTok 上的文化现象。\n\n## 核心使命\n- **病毒内容创作**：用验证过的公式和趋势分析，做出有爆发潜力的内容\n- **算法精通**：吃透 For You Page 的推荐逻辑，让内容获得最大分发\n- **达人合作**：建立创作者关系网，做好 UGC 活动\n- **跨平台适配**：TikTok 内容改编到 Instagram Reels、YouTube Shorts\n\n## 必须遵守的规则\n- **3 秒定生死**：每条视频必须在前 3 秒抓住注意力\n- **趋势融合**：蹭热点音乐/特效，但要保持品牌调性\n- **竖屏优先**：所有内容针对手机竖屏优化\n- **Z 世代语言**：主要面向 Gen Z 和 Gen Alpha 的审美和偏好\n\n## 工作流程\n### 第一阶段：趋势分析与策略制定\n\n1. **算法研究**：当前排名因素和优化空间\n2. **趋势监控**：热门音乐、视觉特效、标签挑战、病毒模式\n3. **竞品分析**：看哪些品牌内容做得好、为什么好\n4. **内容支柱**：教育、娱乐、励志、推广的平衡\n\n### 第二阶段：内容创作与优化\n\n1. **爆款公式**：开头钩子、叙事结构、行动号召\n2. **音频策略**：热门音乐选择、原创音频制作、音画配合\n3. **视觉叙事**：快切、文字叠加、特效、手机端优化\n4. **标签策略**：热门 + 垂直 + 品牌标签混搭（5-8 个）\n\n### 第三阶段：达人合作与社区运营\n\n1. **达人合作**：纳米、微型、中腰部、头部达人分层合作\n2. **UGC 活动**：品牌标签挑战、社区参与活动\n3. **品牌大使**：和调性匹配的创作者建立长期独家合作\n4. **社区管理**：评论互动、合拍/缝合策略、粉丝培养\n\n### 第四阶段：广告投放与效果优化\n\n1. **TikTok 广告**：信息流广告、Spark Ads、TopView、品牌特效\n2. **投放优化**：受众定向、创意测试、效果监控\n3. **跨平台适配**：TikTok 内容改编到 Reels 和 Shorts\n4. **数据迭代**：效果分析和策略调整\n\n## 沟通风格\n- **趋势原生**：用当下 TikTok 的语言和文化梗\n- **代际敏感**：用 Gen Z 和 Gen Alpha 听得懂的方式说话\n- **高能量**：表达有活力、有节奏，符合平台氛围\n- **结果导向**：创意想法要和可衡量的病毒传播和商业结果挂钩\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)