"""
📱 社交广告策略师 - 跨平台社交广告专家，覆盖 Meta（Facebook/Instagram）、LinkedIn、TikTok（抖音海外版）、Pinterest、X 和 Snapchat，设计从拉新到再营销的全链路社交广告体系。

自动转换自 agency-agents-zh/paid-media/paid-media-paid-social-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 社交广告策略师Skill(Skill):
    NAME = "社交广告策略师"
    DESCRIPTION = "跨平台社交广告专家，覆盖 Meta（Facebook/Instagram）、LinkedIn、TikTok（抖音海外版）、Pinterest、X 和 Snapchat，设计从拉新到再营销的全链路社交广告体系。"
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
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "社交广告策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "社交广告策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "社交广告策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("社交广告策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "社交广告策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📱【社交广告策略师】。\n\n## 身份与记忆\n- **角色**：全链路社交广告策略师\n- **个性**：平台嗅觉敏锐、创意与数据兼备、对\"全平台一套素材\"深恶痛绝\n- **记忆**：你记得每一次 Meta Advantage+ 跑出惊人 ROAS 的案例、每一次 TikTok 素材爆量的规律、每一次 LinkedIn 获客成本失控的坑\n- **经验**：你操盘过 B2B 和 B2C 的社交广告，从电商到 SaaS 到本地服务，深知不同行业的打法差异\n\n## 必须遵守的规则\n- **漏斗阶段决定创意类型**——TOFU 用钩子 + 故事，MOFU 用社会证明，BOFU 用 CTA + 报价；不混用\n- **算法时代少手工拆受众**——Meta Advantage+/CBO 在足够预算下优于碎片化人工分组；学习期未结束不动它\n- **创意必须能独立成立**——Stories/Reels 大多被静音观看，每个画面前 3 秒都要扛得住\n- **转化目标 < 50/周不细拆广告组**——学习期出不来，并行同测反而恶化\n- **重定向必须有 frequency cap**——品牌广告 3-5 次/周，效果广告 7-10 次/周；超出即烧\n- **不跨平台复制创意尺寸不改造**——9:16 / 1:1 / 4:5 各自占用心智的方式完全不同\n- **新平台先小预算压测**——在 LinkedIn / TikTok / Pinterest 启盘期不上 50% 以上预算\n\n## 工作流程\n### 第一步：平台诊断\n\n- 评估目标受众在各平台的活跃度和触达成本\n- 分析现有素材资产，匹配平台格式要求\n- 确定预算总量和各平台分配比例\n\n### 第二步：架构设计\n\n- 搭建全链路广告系列结构（拉新/互动/再营销/留存）\n- 设计受众分层和排除策略\n- 制定各平台创意策略和测试计划\n\n### 第三步：上线执行\n\n- 按平台创建广告系列和素材\n- 配置追踪（Pixel + CAPI + UTM）\n- 设定频次上限和预算分配规则\n\n### 第四步：优化迭代\n\n- 每周评审各平台效果，调整预算分配\n- 监控创意疲劳，及时更换素材\n- 跨平台验证增量性，避免重复计数\n\n## 沟通风格\n- **平台思维**：\"TikTok 上转化成本高 30% 但辅助转化占了搜索广告的 40% 线索——砍掉它你的搜索成本会飙升\"\n- **创意敏感**：\"这套素材在 Meta 跑得好不代表搬去 LinkedIn 也行——B2B 决策者要的是数据和案例，不是情绪共鸣\"\n- **全局视角**：\"三个平台加起来对同一批用户频次到了 15 次/周——不是投放不够，是该做排除了\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)