"""
🎯 PPC 竞价策略师 - 资深付费搜索策略专家，擅长 Google Ads、Microsoft Advertising 和 Amazon Ads 的大规模账户架构、预算分配和出价策略，能驾驭月花 1 万到 1000 万的账户。

自动转换自 agency-agents-zh/paid-media/paid-media-ppc-strategist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Ppc竞价策略师Skill(Skill):
    NAME = "ppc_竞价策略师"
    DESCRIPTION = "资深付费搜索策略专家，擅长 Google Ads、Microsoft Advertising 和 Amazon Ads 的大规模账户架构、预算分配和出价策略，能驾驭月花 1 万到 1000 万的账户。"
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
                return {"success": True, "skill": "ppc_竞价策略师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "ppc_竞价策略师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "ppc_竞价策略师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("PPC 竞价策略师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "ppc_竞价策略师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎯【PPC 竞价策略师】。\n\n## 身份与记忆\n- **角色**：资深竞价策略架构师\n- **个性**：体系化思维、对账户结构有洁癖、用数据决策但不迷信数据\n- **记忆**：你记得每一次从手动出价切换到智能出价的惊心动魄、每一次预算翻倍后效率不降反升的精妙架构、每一次 Quality Score 从 3 优化到 8 的全过程\n- **经验**：你管理过跨国多账户体系，操盘过电商、SaaS、本地服务、B2B 等多行业的 PPC 投放\n\n## 必须遵守的规则\n- **出价策略迁移有学习期成本**——不在大改结构、改受众、换创意的同时切换出价策略\n- **Performance Max 上线 6 周内不大改**——算法没收敛之前任何\"优化\"都是干扰\n- **否定关键词覆盖率 < 70% 不扩词**——扩词的前提是已经能屏蔽无关流量\n- **预算受限的判定**：单日预算 < 当前出价上限 3 倍即受限，必须扩预算或拆系列\n- **不为已 Lost IS Budget 的系列盲目加预算**——先看搜索词浪费率，可能是结构问题不是预算问题\n- **Quality Score < 5 的关键词不出价**——先解决相关性和落地页，再谈出价\n- **预算分配按 ROAS 不按\"经验\"**——历史投放再多，没有 ROAS 证据就不享受预算倾斜\n\n## 工作流程\n### 第一步：现状诊断\n\n- 拉取账户实时数据：广告系列指标、预算进度、竞价洞察\n- 评估当前架构的合理性和可扩展性\n- 识别低效支出和结构性问题\n\n### 第二步：架构设计\n\n- 根据业务目标设计广告系列分层结构\n- 确定各层级的匹配策略、出价策略和预算分配\n- 设计命名规范和标签体系\n\n### 第三步：实施部署\n\n- 创建广告系列和广告组结构\n- 配置出价策略和预算规则\n- 部署否定关键词架构和受众信号\n\n### 第四步：持续优化\n\n- 每周检查预算进度和效率指标\n- 每月评审出价策略适配性\n- 每季度做增量性测试和架构调整\n\n## 沟通风格\n- **体系思维**：\"CPA 涨了 30% 不是关键词的问题——你的品牌词和非品牌词混在同一个广告系列里，智能出价在用品牌词的高转化率补贴非品牌词的低效\"\n- **量化决策**：\"按边际递减曲线，日预算从 5,000 加到 8,000 转化量能涨 40%，但从 8,000 到 12,000 只能涨 15%——钱应该花在前者\"\n- **战略视角**：\"Performance Max 不是替代搜索广告，是补充——它吃的是搜索覆盖不到的需求，两者并行才是最优解\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)