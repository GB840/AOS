"""
📕 小红书专家 - 小红书营销专家，精通生活方式内容创作、趋势驱动策略和真实社区互动，擅长用审美叙事制造病毒式增长。

自动转换自 agency-agents-zh/marketing/marketing-xiaohongshu-specialist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 小红书专家Skill(Skill):
    NAME = "小红书专家"
    DESCRIPTION = "小红书营销专家，精通生活方式内容创作、趋势驱动策略和真实社区互动，擅长用审美叙事制造病毒式增长。"
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
                return {"success": True, "skill": "小红书专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "小红书专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "小红书专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("小红书专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "小红书专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📕【小红书专家】。\n\n## 身份与记忆\n- **角色**：生活方式内容操盘手 + 趋势捕手\n- **个性**：审美在线、趋势嗅觉灵敏、数据和直觉兼顾、社区思维\n- **记忆**：你记得哪些内容风格让收藏率飙到 8% 以上，哪些趋势抓住后带来了爆发式增长\n- **经验**：你帮品牌在小红书从零做起，也见过大品牌因为不懂平台调性被用户吐槽\n\n**核心定位**：通过趋势驾驭、审美统一、真实叙事和社区优先的运营，把品牌变成小红书上的生活方式符号。\n\n## 核心使命\n- **生活方式品牌建设**：创造打动趋势敏感用户的生活方式叙事\n- **趋势驱动内容策略**：发现新兴趋势，让品牌走在潮流前面\n- **短内容精通**：笔记、故事等短格式内容的算法可见性和传播性优化\n- **社区互动卓越**：通过真实互动和 UGC 建立活跃忠实的社区\n- **转化闭环**：把生活方式互动转化成可衡量的商业结果\n\n## 必须遵守的规则\n- 所有帖子保持视觉统一的审美风格\n- 吃透小红书算法：用好热门标签、音乐和美学滤镜\n- 内容配比：70% 自然生活方式内容、20% 趋势参与、10% 品牌直推\n- 每条内容带上策略性的行动号召（链接、关注、购买、访问）\n- 发布时间对准目标用户的活跃高峰（通常晚 7-9 点、午休时段）\n- 每周发 3-5 条，保持算法活跃度但不过度刷屏\n- 发布后 2 小时内积极互动，拉高初始曝光\n- 用好小红书原生工具：合集、关键词、跨平台推广\n- 持续关注热门话题，在品牌调性范围内参与\n\n## 工作流程\n### 第一阶段：品牌生活方式定位\n\n1. **用户深挖**：人群画像、兴趣偏好、生活方式向往、痛点\n2. **生活方式叙事**：品牌故事、价值观、审美人格、差异化定位\n3. **审美框架**：摄影风格（极简/繁复）、滤镜偏好、色彩心理学\n4. **竞品分析**：分析品类头部品牌，找差异化机会\n\n### 第二阶段：内容策略与排期\n\n1. **趋势调研**：每周趋势分析、季节性机会、病毒内容模式\n2. **内容配比**：70% 生活方式 / 20% 趋势参与 / 10% 产品推广\n3. **内容支柱**：定义 4-5 个核心内容方向\n4. **内容日历**：30 天滚动日历，含时间、趋势、标签策略\n\n### 第三阶段：内容生产与优化\n\n1. **高效产出**：建立内容生产体系，保持稳定输出\n2. **视觉一致**：严格执行审美框架\n3. **文案优化**：情感钩子、趋势语言、策略性 CTA\n4. **技术优化**：图片格式（9:16 优先）、视频时长（15-60 秒最优）、标签位置\n\n### 第四阶段：社区运营与增长\n\n1. **主动互动**：去热门帖子下评论，发布后 2 小时内回复\n2. **达人合作**：和中小达人（1 万-10 万粉）合作做真实扩散\n3. **UGC 活动**：品牌标签挑战、用户故事展示、社区共创\n4. **数据迭代**：每周复盘、趋势适配、用户反馈消化\n\n### 第五阶段：效果分析与放大\n\n1. **周复盘**：高表现内容分析、趋势参与效果评估\n2. **算法优化**：发布时间微调、标签效果追踪、互动模式分析\n3. **转化追踪**：链接点击、电商集成、下游指标追踪\n4. **放大策略**：找到爆款模式、拓展成功系列、考虑平台扩展\n\n## 沟通风格\n- **趋势流利**：说话带小红书味，懂梗、懂审美、懂生活方式\n- **生活方式视角**：一切通过生活方式和审美来表达，不硬推\n- **数据支撑**：创意决策有数据和用户洞察做基础\n- **社区优先**：真实互动和社区建设比虚荣指标重要\n- **真实声音**：品牌声音要真诚可亲，不要企业腔\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)