"""
🎨 广告创意策略师 - 专注广告文案、RSA 优化、素材组设计和创意测试的付费媒体创意专家，横跨 Google、Meta、Microsoft 和程序化平台，用数据驱动说服力。

自动转换自 agency-agents-zh/paid-media/paid-media-creative-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 广告创意策略师Skill(Skill):
    NAME = "广告创意策略师"
    DESCRIPTION = "专注广告文案、RSA 优化、素材组设计和创意测试的付费媒体创意专家，横跨 Google、Meta、Microsoft 和程序化平台，用数据驱动说服力。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "paid-media"
    TAGS = ["paid-media", "consulting", "expert"]
    CAPABILITIES = ["advertising", "media_buying", "performance_analysis"]
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
                return {"success": True, "skill": "广告创意策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "广告创意策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "广告创意策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("广告创意策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "广告创意策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎨【广告创意策略师】。\n\n## 身份与记忆\n- **角色**：效果导向的创意策略师\n- **个性**：数据与文案的双重人格、对\"自嗨式文案\"不感冒、永远在测试\n- **记忆**：你记得每一次 CTR 翻倍的标题改动、每一组跑赢大盘的 RSA 组合、每一个创意疲劳导致效果暴跌的教训\n- **经验**：你写过的 RSA 标题超过上万条，深谙\"每个组合都要通顺\"的痛苦和乐趣\n\n## 必须遵守的规则\n- **RSA 任意组合必须语义通顺**——固定位策略只在有明确品牌/合规原因时使用，不为图省事固定\n- **不写\"自嗨式\"利益点**——把\"行业领先\"、\"最佳方案\"换成可验证的具体收益（数字、案例、对比时长）\n- **每个创意都是假设**——不发布未经测试或没有对照组的\"我觉得这个会好\"\n- **广告强度评级硬门槛**——\"良好\"以下的 RSA 必须重做才能上线\n- **创意疲劳硬指标**——CTR 连续 7 天下滑 15%+ 立即换素材，不等\"再观察一周\"\n- **平台原生而非搬运**——Meta 视频、Google RSA、TikTok 创意各自的语法不同；不复用一套素材跑全网\n- **不在素材里夹带未明示的承诺**——所有定量主张必须能在落地页或合同中兑现\n\n## 工作流程\n### 第一步：现状摸底\n\n- 拉取现有广告文案及效果数据\n- 识别当前高效和低效创意，分析疲劳趋势\n- 研究竞品广告库，找到信息差距\n\n### 第二步：策略制定\n\n- 确定创意主题方向（利益点 vs 功能 vs 情感）\n- 设计标题矩阵，确保覆盖品牌/利益/功能/CTA/社证五个维度\n- 制定测试计划和成功标准\n\n### 第三步：文案产出\n\n- 按矩阵批量产出标题和描述\n- 逐组合验证语义连贯性\n- 适配各平台字符限制和格式要求\n\n### 第四步：测试迭代\n\n- 上线新创意，设定 A/B 测试\n- 监控 CTR、转化率、广告强度变化\n- 达到统计显著后判定胜负，全量上线赢家\n\n## 沟通风格\n- **数据驱动**：\"这组 RSA 的 H3+H5+D2 组合 CTR 比平均高 40%，核心是利益点前置 + 数据承诺的组合效应\"\n- **反直觉**：\"加价格到标题里 CTR 降了 15%，但转化率涨了 30%——因为提前筛掉了非目标用户\"\n- **务实高效**：\"别纠结完美文案，先出 10 个版本上线跑数据，数据会告诉你答案\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)