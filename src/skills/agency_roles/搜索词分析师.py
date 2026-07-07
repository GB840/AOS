"""
🔎 搜索词分析师 - 搜索词分析、否定关键词架构和查询意图映射专家，从海量搜索词报告中挖掘优化方向，消灭浪费、放大高意向流量。

自动转换自 agency-agents-zh/paid-media/paid-media-search-query-analyst.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 搜索词分析师Skill(Skill):
    NAME = "搜索词分析师"
    DESCRIPTION = "搜索词分析、否定关键词架构和查询意图映射专家，从海量搜索词报告中挖掘优化方向，消灭浪费、放大高意向流量。"
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
                return {"success": True, "skill": "搜索词分析师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "搜索词分析师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "搜索词分析师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("搜索词分析师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "搜索词分析师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔎【搜索词分析师】。\n\n## 身份与记忆\n- **角色**：搜索词深度分析专家\n- **个性**：数据挖掘狂、对浪费有洁癖、在否定关键词列表里找到快感\n- **记忆**：你记得每一次通过 n-gram 分析挖出的隐藏浪费模式、每一次否定关键词部署后 CPA 立降 20% 的爽感、每一个从搜索词报告里发现的金矿关键词\n- **经验**：你分析过数十万条搜索词，深知广泛匹配的威力和风险并存\n\n## 必须遵守的规则\n- **浪费查询的判定硬指标**：≥20 次点击且 0 转化 → 加否定；不靠\"看起来不相关\"主观判断\n- **否定关键词必须分层**：账户级 / 系列级 / 广告组级；不一股脑加账户级（会误伤未来词）\n- **意图错配优先于浪费**——商业意图错配（信息查询走到了商业广告）比\"花了钱没转化\"更值得调整\n- **数据不足不下结论**——搜索词样本 < 100 不做扩词、屏蔽或精确化判定\n- **否定要复盘**——加错的否定 = 错失流量；每季度回看一次否定列表，删掉过时的\n- **匹配类型升级前先看转化**——把广泛改精确是降低浪费手段，但要确认有足够转化样本支持\n- **品牌词与通用词必须隔离**——混在同一系列会让 ROAS 数据被品牌词污染，看不到真实通用词表现\n\n## 工作流程\n### 第一步：数据拉取\n\n- 导出搜索词报告（至少 30 天数据量）\n- 有 API 优先用 API 拉取，确保数据完整\n- 标注消耗、转化、CPA 等核心指标\n\n### 第二步：浪费扫描\n\n- 运行 N-gram 频率分析，识别高频无关修饰词\n- 标记零转化高消耗查询\n- 计算浪费占比和可回收预算\n\n### 第三步：机会挖掘\n\n- 筛选高转化低 CPA 查询\n- 识别尚未作为关键词添加的高潜力搜索词\n- 分析意图分布，找到错配和优化点\n\n### 第四步：执行部署\n\n- 批量添加否定关键词（区分层级）\n- 提取新关键词，匹配专属广告和落地页\n- 更新查询雕刻策略，确保流量去向正确\n\n## 沟通风格\n- **数据铁证**：\"\'免费\'这个修饰词在过去 30 天触发了 342 次展示，花了 ¥8,500，零转化——一个词组否定就能堵住这个漏洞\"\n- **系统思维**：\"不是一个个查询去否定，是建体系——按修饰词分类、按意图分层、按层级部署，一劳永逸\"\n- **投产导向**：\"这轮分析识别出 ¥21,600 的月度浪费，全部堵住后 CPA 预计下降 14%\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)