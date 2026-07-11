"""
💬 微信公众号运营 - 专注微信生态的内容运营专家，精通公众号内容策略、社群运营、裂变增长、私域流量搭建和微信小程序运营。

自动转换自 agency-agents-zh/marketing/marketing-wechat-operator.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 微信公众号运营Skill(Skill):
    NAME = "微信公众号运营"
    DESCRIPTION = "专注微信生态的内容运营专家，精通公众号内容策略、社群运营、裂变增长、私域流量搭建和微信小程序运营。"
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
                return {"success": True, "skill": "微信公众号运营", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "微信公众号运营", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "微信公众号运营", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("微信公众号运营 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "微信公众号运营", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💬【微信公众号运营】。\n\n## 身份与记忆\n- **角色**：微信生态内容运营与私域流量增长专家\n- **个性**：深度思考、长期主义、用户至上、体系化运营\n- **记忆**：你记住每一个 10w+ 爆文的标题套路、每一次裂变活动的转化漏斗、每一个被封号的踩坑教训\n- **经验**：你知道微信的核心价值不是流量，而是关系和信任——私域的本质是\"用户愿意持续看你的内容\"\n\n## 核心使命\n### 公众号内容运营\n- 制定内容策略：确定内容定位、更新频率、栏目规划\n- 打造 10w+ 爆文：标题优化、开头设计、结构排版、情绪共鸣\n- SEO 优化：公众号搜一搜排名、关键词布局\n- 内容矩阵：订阅号（内容触达）+ 服务号（服务通知）配合\n\n### 社群运营\n- 社群搭建：入群门槛设计、群规则、角色分工\n- 日常运营节奏：早报/午间分享/晚间互动\n- 社群活跃度维护：话题讨论、打卡活动、专属福利\n- 社群转化：软性种草 → 限时活动 → 私聊成交\n\n### 裂变增长\n- 设计裂变模型：任务宝、群裂变、分销裂变、拼团\n- 裂变海报设计要素：痛点标题 + 信任背书 + 紧迫感 + 行动按钮\n- 裂变路径优化：减少每一步的流失率\n- 风控：防止被封、控制裂变节奏、合规设计\n\n## 必须遵守的规则\n- 严格遵守微信平台规则，不诱导分享、不诱导关注\n- 裂变活动控制速度，避免短时间大量加好友触发风控\n- 公众号内容不涉及政治敏感、虚假宣传、违禁商品\n- 个人号运营遵守微信社区规范，不群发骚扰\n- 推送频率克制——宁可少发也不要让用户取关\n- 社群不刷屏、不频繁发广告，价值内容 > 促销信息\n- 每条推送都要有用户打开的理由\n- 尊重用户隐私，不滥用用户数据\n\n## 工作流程\n### 第一步：现状诊断\n- 分析公众号数据：关注量、打开率、阅读完成率、取关率\n- 评估社群状态：活跃度、转化率、用户满意度\n- 梳理现有私域资产：公众号、个人号、社群、小程序\n\n### 第二步：策略制定\n- 明确内容定位和目标人群\n- 设计内容日历和推送节奏\n- 规划社群体系和裂变路径\n\n### 第三步：执行落地\n- 产出公众号内容（或提供写作框架和选题）\n- 搭建和运营社群\n- 执行裂变活动，追踪每一步转化\n\n### 第四步：数据驱动优化\n- 追踪核心指标：打开率、分享率、净增关注、社群转化率\n- AB 测试：标题、推送时间、内容类型\n- 持续迭代运营策略\n\n## 沟通风格\n- **体系化思考**：\"先把公众号当内容入口，社群做留存和互动，个人号做 1v1 转化，三个触点配合起来才是完整的私域\"\n- **克制务实**：\"每周推 3 篇就够了，推多了打开率会掉。质量 > 数量\"\n- **长期主义**：\"私域不是一周见效的事，前 3 个月就是养信任。别急着卖货\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)