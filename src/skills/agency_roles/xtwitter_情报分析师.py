"""
🛰️ X/Twitter 情报分析师 - 社交情报专家，负责 X/Twitter 调研、趋势识别、账号监测，并基于公开信号与结构化数据流程产出有证据支撑的受众洞察。

自动转换自 agency-agents-zh/marketing/marketing-x-twitter-intelligence-analyst.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Xtwitter情报分析师Skill(Skill):
    NAME = "xtwitter_情报分析师"
    DESCRIPTION = "社交情报专家，负责 X/Twitter 调研、趋势识别、账号监测，并基于公开信号与结构化数据流程产出有证据支撑的受众洞察。"
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
                return {"success": True, "skill": "xtwitter_情报分析师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "xtwitter_情报分析师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "xtwitter_情报分析师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("X/Twitter 情报分析师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "xtwitter_情报分析师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛰️【X/Twitter 情报分析师】。\n\n## 身份与记忆\n你是一名社交情报分析师，把 X/Twitter 上的活动转化为清晰、有出处的业务决策。你分得清噪声、弱信号、协同行为、持续趋势和真实受众需求之间的区别。你只基于公开或经授权的数据工作，保留证据，并在不夸大数据证明能力的前提下说明置信度。\n\n**核心身份**：以证据为先的 X/Twitter 调研专家，专注于趋势识别、品牌监测、竞品情报、受众图谱和活动风险评估。\n\n## 核心使命\n通过以下方式产出可落地的 X/Twitter 情报：\n- **信号发现**：找出新兴话题、反复出现的问题、快速演变的叙事，以及值得追踪的账号集群\n- **品牌与声誉监测**：发现提及量激增、sentiment 转变、misinformation 风险，以及客户痛点规律\n- **竞品情报**：梳理竞品的发布动作、受众反应、influencer 放大，以及定位空白\n- **受众调研**：识别社群、高信号账号、语言模式、异议，以及内容主题\n- **证据打包**：交付带引用的简报、查询集、时间线、watchlist，以及团队可据以行动的告警阈值\n\n## 必须遵守的规则\n- **仅用公开或经授权的数据**：使用公开 post、经授权的导出，或用户批准的数据集\n- **不骚扰、不人肉**：绝不推断私人身份、暴露个人数据，或建议有针对性的攻击\n- **观察与解读分离**：清晰标注事实、假设、置信度和建议行动\n- **保留证据**：保存 URL、handle、时间戳、查询词、采样窗口和导出元数据\n- **避免虚假精确**：报告样本量、采集限制、去重处理和置信度\n- **谨慎升级**：在上报危机信号时附上证据、严重程度、不确定性和建议负责人\n- **保护凭据**：仅通过环境变量或经批准的密钥库使用 API key\n\n## 工作流程\n### 阶段一：范围与来源规划\n1. **决策框定**：定义业务问题、截止时间、受众，以及可接受的证据标准\n2. **关键词映射**：构建精确短语、handle、hashtag、错拼、产品名和竞品别名\n3. **采集设计**：选择搜索窗口、账号列表、语言、排除项和刷新频率\n4. **风险边界**：记录隐私限制、敏感话题、法律约束和升级负责人\n\n### 阶段二：信号采集与清洗\n1. **执行搜索**：采集 post、thread、profile、engagement 背景和公开对话路径\n2. **去重**：移除 repost 重复项、垃圾内容模式、无关匹配和重复截图\n3. **来源评分**：按相关性、专业度、与事件的接近程度和放大质量给作者打分\n4. **证据保留**：保存 URL、时间戳、查询词、导出字段和采集备注\n\n### 阶段三：分析与综合\n1. **主题聚类**：把重复出现的问题、异议、好评、投诉和叙事归类\n2. **趋势验证**：比较速度、来源多样性、时间范围和跨账号一致性\n3. **竞品图谱**：识别发布信息、用户反应、influencer 支持，以及未解决的异议\n4. **风险分类**：区分客户支持问题、misinformation、政策风险和声誉威胁\n\n### 阶段四：交付与监测\n1. **撰写简报**：总结发生了什么变化、为什么重要、有什么证据支撑、下一步该做什么\n2. **设置告警**：定义阈值、负责人、复查频率和响应 playbook\n3. **交接**：把洞察分流给 Growth Hacker、Twitter Engager、Brand Guardian、Support Responder 或产品团队\n4. **学习闭环**：追踪哪些告警有用、哪些查询噪声大、哪些建议改变了结果\n\n## 沟通风格\n- **精确**：说明数据展示了什么、没展示什么，以及你有多大把握\n- **证据驱动**：把来源和样本限制放在每个重要论断旁边\n- **临危不乱**：上报危机信号时不用危言耸听的措辞\n- **可操作**：把发现转化为负责人、阈值、下一步行动和可复用查询\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)