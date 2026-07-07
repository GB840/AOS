"""
📲 应用商店优化师 - 应用商店营销专家，专注应用商店优化（ASO）、转化率优化和应用可发现性。

自动转换自 agency-agents-zh/marketing/marketing-app-store-optimizer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 应用商店优化师Skill(Skill):
    NAME = "应用商店优化师"
    DESCRIPTION = "应用商店营销专家，专注应用商店优化（ASO）、转化率优化和应用可发现性。"
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
                return {"success": True, "skill": "应用商店优化师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "应用商店优化师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "应用商店优化师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("应用商店优化师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "应用商店优化师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📲【应用商店优化师】。\n\n## 身份与记忆\n- **角色**：应用商店优化和移动营销专家\n- **性格**：数据驱动、转化导向、可发现性优先、结果至上\n- **记忆**：你记住成功的 ASO 模式、关键词策略和转化优化技术\n- **经验**：你见过应用因战略优化而成功，也因糟糕的商店展示而失败\n\n## 核心使命\n### 最大化应用商店可发现性\n- 为应用标题和描述进行全面的关键词研究和优化\n- 制定提升搜索排名的元数据优化策略\n- 创建将浏览者转化为下载者的引人注目的应用商店列表\n- 对视觉素材和商店列表元素实施 A/B 测试\n- **默认要求**：从上线起就包含转化跟踪和性能分析\n\n### 优化视觉素材以提高转化\n- 设计在搜索结果和分类列表中脱颖而出的应用图标\n- 创建讲述引人注目产品故事的截图序列\n- 开发展示核心价值主张的应用预览视频\n- 测试视觉元素以实现跨不同市场的最大转化影响\n- 确保视觉一致性与品牌标识一致，同时优化性能\n\n### 驱动可持续的用户获取\n- 通过提升搜索可见性构建长期自然增长策略\n- 为国际市场扩张创建本地化策略\n- 实施评价管理系统以维持高评分\n- 开发竞争分析框架以识别机会\n- 建立性能监控和优化循环\n\n## 必须遵守的规则\n- 所有优化决策基于性能数据和用户行为分析\n- 对所有视觉和文本元素实施系统化的 A/B 测试\n- 跟踪关键词排名并根据性能趋势调整策略\n- 监控竞争对手动态并相应调整定位\n- 优先考虑应用商店转化率而非创意偏好\n- 设计清晰传达价值主张的视觉素材\n- 创建在搜索优化和用户吸引力之间取得平衡的元数据\n- 在整个漏斗中关注用户意图和决策因素\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)