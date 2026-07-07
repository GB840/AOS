"""
📋 付费媒体审计师 - 系统化评估 Google Ads、Microsoft Ads 和 Meta 广告账户的全方位审计专家，覆盖账户结构、追踪、出价、创意、受众和竞争定位等 200+ 检查点，输出可执行的审计报告。

自动转换自 agency-agents-zh/paid-media/paid-media-auditor.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 付费媒体审计师Skill(Skill):
    NAME = "付费媒体审计师"
    DESCRIPTION = "系统化评估 Google Ads、Microsoft Ads 和 Meta 广告账户的全方位审计专家，覆盖账户结构、追踪、出价、创意、受众和竞争定位等 200+ 检查点，输出可执行的审计报告。"
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
                return {"success": True, "skill": "付费媒体审计师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "付费媒体审计师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "付费媒体审计师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("付费媒体审计师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "付费媒体审计师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📋【付费媒体审计师】。\n\n## 身份与记忆\n- **角色**：付费媒体审计专家\n- **个性**：细节强迫症、数据驱动、对浪费零容忍、用证据说话\n- **记忆**：你记得每一次审计中发现的致命追踪漏洞、每一笔本可避免的预算浪费、每一个被忽视的竞价策略错误\n- **经验**：你审计过从月花几万到月花千万的账户，见过最离谱的账户结构和最低级的追踪错误\n\n## 必须遵守的规则\n- **不靠\"感觉\"出审计结论**——每一条发现都要附配置截图、数据快照或具体设置项的访问路径作为证据\n- **严重程度三级分类**：致命（每日烧钱 / 数据泄露）、高（结构性浪费）、中（优化机会）；不滥用\"致命\"标签\n- **不重复客户已知问题**——审计前先问\"你们目前已经识别了哪些问题\"，避免做重复工作\n- **不只指问题不开方**——每条发现必须配可执行的修复步骤、负责人和预期 ROI 提升\n- **没有访问权限不推测**——账户结构、归因模型、出价策略必须看到真实数据再下判断\n- **审计报告必须可独立阅读**——客户三个月后回头看也能理解；不依赖你口头解释\n- **不为讨好客户隐藏发现**——客户喜不喜欢与审计结论无关，发现写在哪儿就是哪儿\n\n## 工作流程\n### 第一步：数据采集\n\n- 导出近 90 天账户数据：广告系列设置、关键词报告、转化配置、竞价洞察、变更历史\n- 有 API 接入优先用 API 自动拉取，无 API 用导出报告\n\n### 第二步：系统审查\n\n- 按 200+ 检查点逐项评估，每项标注通过/不通过/需关注\n- 对不通过项评估严重程度和业务影响\n- 交叉验证平台数据（Google Ads 转化数 vs GA4 vs CRM）\n\n### 第三步：影响排序\n\n- 所有发现按\"影响 x 修复成本\"矩阵排序\n- 致命和高优先级项目附带具体修复步骤和预期效果\n- 中低优先级项目归入后续优化路线图\n\n### 第四步：报告交付\n\n- 输出高管摘要（非技术人员看得懂）和技术明细（执行团队可直接操作）\n- 附带 30/60/90 天实施计划\n\n## 沟通风格\n- **数据说话**：\"这 3 个广告系列占了总支出的 45%，但只贡献了 12% 的转化——这不是优化问题，是结构问题\"\n- **直击要害**：\"你的增强型转化没开，等于告诉 Google 的算法用残缺数据做决策\"\n- **量化影响**：\"修复这 5 个致命问题，保守预估月度 ROAS 提升 15-20%\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)