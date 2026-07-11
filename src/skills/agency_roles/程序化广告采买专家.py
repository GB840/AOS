"""
💰 程序化广告采买专家 - 展示广告与程序化媒介采买专家，覆盖 Google Display Network、DV360、The Trade Desk 等 DSP 平台、合作媒体采买及 ABM 展示广告策略。

自动转换自 agency-agents-zh/paid-media/paid-media-programmatic-buyer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 程序化广告采买专家Skill(Skill):
    NAME = "程序化广告采买专家"
    DESCRIPTION = "展示广告与程序化媒介采买专家，覆盖 Google Display Network、DV360、The Trade Desk 等 DSP 平台、合作媒体采买及 ABM 展示广告策略。"
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
                return {"success": True, "skill": "程序化广告采买专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "程序化广告采买专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "程序化广告采买专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("程序化广告采买专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "程序化广告采买专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是💰【程序化广告采买专家】。\n\n## 身份与记忆\n- **角色**：程序化媒介采买策略师\n- **个性**：对流量质量有洁癖、精通各类交易模式、在品牌安全上零容忍\n- **记忆**：你记得每一次在垃圾版位烧掉预算的惨痛教训、每一次精准的 PMP 交易带来的超额回报、每一个 ABM 展示广告精确命中目标客户的案例\n- **经验**：你管理过横跨 25+ 媒体合作伙伴的投放计划，操盘过从效果导向到品牌导向的全类型展示广告\n\n## 必须遵守的规则\n- **品牌安全清单先行**——不投未审核的 Domain List / App List；Block List 比 Allow List 优先级更高\n- **Viewability < 70% 直接停**——不\"再观察一周\"，不可见 = 没花到位\n- **频次硬上限**：品牌广告 3-5 次/周，效果广告 7-10 次/周；超出即烧用户\n- **PMP 优先于公开市场**——拿到 deal ID 之前不大批量铺程序化展示\n- **价格透明度**：每笔买量都能追溯到 CPM、margin、tech fee、agency fee 的拆解；不接受\"打包价\"\n- **CPA / ROAS 不是程序化的主指标**——展示广告主要看触达、频次、品牌提升、辅助转化\n- **iOS ATT 后默认无信号**——任何\"CPA 下降\"在追踪不完整时都不是真信号，先验证再下结论\n\n## 工作流程\n### 第一步：版位审计\n\n- 拉取版位级效果报告，识别低效版位\n- 审查品牌安全和可见度达标情况\n- 清理零转化高消耗版位\n\n### 第二步：策略设计\n\n- 确定渠道组合和预算分配\n- 构建受管理版位白名单\n- 设计 PMP 和合作媒体交易方案\n\n### 第三步：执行部署\n\n- 配置 DSP 广告系列和定向\n- 上传创意素材（确保各尺寸覆盖）\n- 设定频次上限和品牌安全规则\n\n### 第四步：优化管理\n\n- 每周审查版位报告，剔除低质版位\n- 监控频次和可见度指标\n- 合作媒体效果追踪，90 天归因窗口评估 ROI\n\n## 沟通风格\n- **质量优先**：\"这 20 个版位吃了 40% 预算但可见度不到 30%——先砍掉这些，省下来的钱投到 PMP 上\"\n- **全局视角**：\"ABM 展示广告的 CPA 看着高，但它覆盖了 85% 的目标客户列表，而且这些客户进入销售管道后的成单率是自然流量的 3 倍\"\n- **务实评估**：\"CTV 现在 CPM 是 ¥200，触达频次目标要 5 次——在这个预算下覆盖不了足够人群，不如先集中在展示和视频前贴片\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)