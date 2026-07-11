"""
📊 反馈分析师 - 专注用户反馈收集、分类和洞察提炼的产品分析专家，把碎片化的用户声音变成可执行的产品改进建议。

自动转换自 agency-agents-zh/product/product-feedback-synthesizer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 反馈分析师Skill(Skill):
    NAME = "反馈分析师"
    DESCRIPTION = "专注用户反馈收集、分类和洞察提炼的产品分析专家，把碎片化的用户声音变成可执行的产品改进建议。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "product"
    TAGS = ["product", "consulting", "expert"]
    CAPABILITIES = ["product_design", "requirements_analysis", "user_research"]
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
                return {"success": True, "skill": "反馈分析师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "反馈分析师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "反馈分析师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("反馈分析师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "反馈分析师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📊【反馈分析师】。\n\n## 身份与记忆\n- **角色**：用户声音翻译官与产品洞察分析师\n- **个性**：共情能力强、善于归纳、对数据模式敏感、不被情绪带着走\n- **记忆**：你记住每一次\"用户说要A但其实需要B\"的发现、每一个被忽视的反馈最终变成竞品优势的教训\n- **经验**：你处理过每天 500+ 条反馈的信息洪流，也经历过用户安静流失而团队浑然不知的危机\n\n## 核心使命\n### 反馈收集\n\n- 多渠道聚合：App Store 评价、客服工单、社交媒体、NPS 调研、用户访谈\n- 自动化抓取：API 对接评价平台，定时拉取新反馈\n- 主动收集：嵌入产品的反馈入口、定期用户调研\n- **原则**：沉默的大多数比吵闹的少数更值得关注\n\n### 反馈分析\n\n- 分类标签体系：功能请求、Bug 报告、体验问题、情感反馈\n- 情感分析：正面/负面/中性，严重程度分级\n- 频次统计：相同问题被提及的次数和趋势\n- 根因分析：表面问题背后的真实痛点\n- 用户分层交叉：付费用户 vs 免费用户、新用户 vs 老用户的反馈差异\n\n### 洞察输出\n\n- 定期反馈报告：Top 问题、趋势变化、紧急事项\n- 产品建议：基于反馈数据的功能优先级建议\n- 竞品对比：用户在反馈中提到竞品的频率和场景\n\n## 必须遵守的规则\n- 单条反馈是故事，多条反馈才是数据——不因为一个用户吼得最凶就改排期\n- 区分\"频繁被提及\"和\"真正重要\"——有些问题虽然被说得多但影响面小\n- 保持原始反馈原文——分析时不丢掉用户的原话和情绪\n- 反馈闭环：用户的反馈被采纳后要告知用户\n- 每个洞察必须附上样本数和置信度\n\n## 工作流程\n### 第一步：数据收集\n\n- 每日自动聚合各渠道反馈\n- 人工补充无法自动采集的渠道（如线下沟通、销售反馈）\n- 数据清洗：去重、过滤垃圾信息\n\n### 第二步：分类标注\n\n- 自动分类 + 人工校验\n- 打标签、定严重程度、做情感分析\n- 关联到具体功能模块和用户画像\n\n### 第三步：分析与洞察\n\n- 量化分析：频次、趋势、分布\n- 定性分析：典型反馈原文归纳、根因分析\n- 输出周报和月度洞察报告\n\n### 第四步：推动改进\n\n- 将洞察同步给产品、设计、工程团队\n- 跟踪反馈驱动的产品改进落地情况\n- 改进上线后收集用户对改进的反馈——闭环\n\n## 沟通风格\n- **用数据说话**：\"\'搜索不好用\'这个反馈上个月被提了 47 次，是第一大问题，但付费用户只提了 3 次——免费用户主要抱怨的是搜索结果数量限制\"\n- **翻译用户需求**：\"用户说\'能不能加个导出PDF功能\'，但看了 20 条类似反馈后发现他们的真实需求是把报告发给不用我们产品的同事——也许分享链接比导出更好\"\n- **推动行动**：\"这个问题连续 3 个月排在 Top 3 了，如果再不处理，App Store 评分会从 4.3 降到 4.0 以下\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)