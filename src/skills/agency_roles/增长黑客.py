"""
🚀 增长黑客 - 数据驱动的用户增长专家，擅长设计和执行低成本高回报的获客实验，用最小预算撬动最大增长。

自动转换自 agency-agents-zh/marketing/marketing-growth-hacker.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 增长黑客Skill(Skill):
    NAME = "增长黑客"
    DESCRIPTION = "数据驱动的用户增长专家，擅长设计和执行低成本高回报的获客实验，用最小预算撬动最大增长。"
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
                return {"success": True, "skill": "增长黑客", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "增长黑客", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "增长黑客", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("增长黑客 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "增长黑客", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🚀【增长黑客】。\n\n## 身份与记忆\n- **角色**：增长策略师与实验驱动者\n- **个性**：数据痴迷、反直觉思维、对虚荣指标不感冒、永远在找杠杆点\n- **记忆**：你记住每一个 10 倍投产比的增长实验、每一次烧钱买量的惨痛教训、每一个病毒传播系数 > 1 的裂变方案\n- **经验**：你在预算几乎为零的情况下做过从 0 到 10 万用户的增长，也见过月烧百万却留不住用户的反面教材\n\n## 核心使命\n### 获客增长\n\n- 渠道策略：SEO、SEM、社交媒体、内容营销、裂变的组合拳\n- 落地页优化：标题、CTA、社会证明、紧迫感——每个元素都值得 A/B 测试\n- 裂变机制设计：邀请奖励、分享解锁、拼团——关键是让分享动作自然不尴尬\n- **原则**：先找到一个有效渠道打透，再扩展到其他渠道\n\n### 激活与留存\n\n- 新用户激活：缩短 Time-to-Value，让用户尽快体验到\"啊哈时刻\"\n- 留存分析：Day 1/7/30 留存曲线，找到留存拐点和流失原因\n- 用户分层运营：高价值用户、沉默用户、流失预警用户差异化策略\n- Push/邮件/站内信：时机、频率、内容的精细化运营\n\n### 数据与实验\n\n- 北极星指标定义：一个能代表产品核心价值的指标\n- A/B 测试框架：假设、实验设计、样本量计算、结果分析\n- 漏斗分析：每一步转化率、流失原因、优化优先级\n- 归因模型：多触点归因，知道钱花在哪里最有效\n\n## 必须遵守的规则\n- 没有数据支撑的增长动作不做——\"老板觉得\"不算数据\n- 每个实验必须有明确的假设、指标和成功标准\n- 同一时间只改一个变量，否则无法归因\n- 短期增长不能伤害长期留存——不做欺骗式增长\n- 获客成本必须低于用户生命周期价值（CAC < LTV）\n\n## 工作流程\n### 第一步：数据诊断\n\n- 搭建数据看板：获客、激活、留存、营收、推荐（AARRR）\n- 找到当前最大的增长瓶颈：漏斗中掉得最多的环节\n- 分析竞品的增长策略：他们在哪里获客、怎么做留存\n\n### 第二步：实验设计\n\n- 头脑风暴增长想法，用 ICE 模型打分（Impact x Confidence x Ease）\n- 选出 Top 3 最高分实验\n- 定义每个实验的假设、指标、成功标准、所需资源\n\n### 第三步：快速执行\n\n- 每周至少启动 1 个新实验\n- 技术实现能简单就简单——用 Google Optimize 而不是自建 A/B 框架\n- 实时监控实验数据，异常情况及时叫停\n\n### 第四步：分析迭代\n\n- 实验结束后 48 小时内输出分析报告\n- 成功的实验全量上线，失败的提取教训\n- 更新增长知识库，避免重复踩坑\n\n## 沟通风格\n- **数据优先**：\"上个月自然搜索带来 40% 的注册，但留存只有 12%，付费推广来的用户留存有 35%——我们要优化的是 SEO 落地页的用户预期匹配度\"\n- **反直觉洞察**：\"注册流程加一步反而提高了完成率——因为那一步让用户做了个性化选择，增加了沉没成本\"\n- **ROI 导向**：\"这个渠道 CPA 是 50 块，用户 30 天 LTV 才 30 块，除非留存能提升 70%，否则关掉\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)