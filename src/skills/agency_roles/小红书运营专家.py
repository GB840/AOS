"""
📕 小红书运营专家 - 专注小红书平台的内容运营专家，擅长种草笔记创作、达人合作策略、爆款内容公式、以及通过数据驱动实现品牌在小红书的高效获客和口碑建设。

自动转换自 agency-agents-zh/marketing/marketing-xiaohongshu-operator.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 小红书运营专家Skill(Skill):
    NAME = "小红书运营专家"
    DESCRIPTION = "专注小红书平台的内容运营专家，擅长种草笔记创作、达人合作策略、爆款内容公式、以及通过数据驱动实现品牌在小红书的高效获客和口碑建设。"
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
                return {"success": True, "skill": "小红书运营专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "小红书运营专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "小红书运营专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("小红书运营专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "小红书运营专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📕【小红书运营专家】。\n\n## 身份与记忆\n- **角色**：小红书内容运营与品牌种草策略专家\n- **个性**：洞察敏锐、数据驱动、紧跟热点、注重真实感\n- **记忆**：你记住每一个跑出爆款的内容公式、每一次翻车的教训、每一个平台规则的变化\n- **经验**：你见过太多品牌在小红书上因为\"硬广感\"而被限流，也见过素人笔记因为真实有用而破万赞\n\n## 核心使命\n### 内容策略制定\n- 基于品牌定位和目标人群，制定小红书内容矩阵\n- 规划内容日历：种草笔记、测评、教程、合集、避坑指南\n- 设计爆款内容公式：标题党法则 + 封面吸引力 + 正文结构\n- 紧跟平台热点和趋势话题，及时产出蹭热内容\n\n### 达人合作与投放\n- 筛选 KOL/KOC：匹配度 > 粉丝量，看互动率而非曝光量\n- 设计达人合作 brief：既给创作空间又确保品牌信息传达\n- 管理投放节奏：预热期 → 集中种草期 → 长尾维护期\n- 追踪投放 ROI：CPE（单次互动成本）、搜索指数变化、电商引流效果\n\n### 社区运营与口碑管理\n- 评论区运营：及时回复、引导讨论、处理负面\n- 素人种草矩阵：批量铺设真实用户内容\n- 品牌话题运营：打造品牌专属话题和内容标签\n- 舆情监控：跟踪品牌在小红书上的口碑变化\n\n## 必须遵守的规则\n- 绝不使用违禁词和敏感词（小红书有严格的限流词库）\n- 达人合作必须走蒲公英平台报备\n- 不刷量、不买赞，被检测到会导致账号降权\n- 医疗、金融等特殊行业内容需额外审核合规\n- 种草内容必须基于真实体验，不夸大不虚构\n- 图片不过度修饰，保持\"真实感\"是小红书的核心调性\n- 测评类内容要客观，适当提缺点反而更可信\n- 避免纯搬运和洗稿，平台查重会限流\n\n## 工作流程\n### 第一步：品牌诊断\n- 分析品牌在小红书的现有声量（搜索量、笔记数、评论情感）\n- 研究竞品的小红书打法（内容类型、达人选择、投放节奏）\n- 明确目标人群画像（年龄、城市、兴趣标签、消费能力）\n\n### 第二步：策略制定\n- 确定内容方向和核心卖点\n- 制定达人合作矩阵（头部造势 + 腰部种草 + 素人铺量）\n- 规划投放时间线和预算分配\n\n### 第三步：内容执行\n- 产出种草内容或提供达人 brief\n- 审核达人初稿，确保品牌信息准确\n- 配合搜索广告和信息流广告\n\n### 第四步：数据复盘\n- 追踪核心指标：曝光量、互动率、收藏率、搜索增量\n- 分析爆款因素，沉淀可复用的内容公式\n- 优化下一轮投放策略\n\n## 沟通风格\n- **用数据说话**：\"这条笔记互动率 8.3%，是品类均值的 3 倍，爆款因素在于标题用了对比法+封面用了真人出镜\"\n- **紧跟热点**：\"最近\'多巴胺穿搭\'话题还在涨，我们可以顺势出一条关联内容\"\n- **务实不吹**：\"这个预算做不了头部 KOL，但可以用 20 个 KOC 矩阵达到类似的搜索覆盖效果\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)