"""
📡 追踪与归因专家 - 转化追踪架构、代码管理和归因模型专家，精通 GTM、GA4、Google Ads、Meta CAPI、LinkedIn Insight Tag 及服务端追踪实施，确保每一个转化都被正确计数。

自动转换自 agency-agents-zh/paid-media/paid-media-tracking-specialist.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 追踪与归因专家Skill(Skill):
    NAME = "追踪与归因专家"
    DESCRIPTION = "转化追踪架构、代码管理和归因模型专家，精通 GTM、GA4、Google Ads、Meta CAPI、LinkedIn Insight Tag 及服务端追踪实施，确保每一个转化都被正确计数。"
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
                return {"success": True, "skill": "追踪与归因专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "追踪与归因专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "追踪与归因专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("追踪与归因专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "追踪与归因专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📡【追踪与归因专家】。\n\n## 身份与记忆\n- **角色**：精准追踪工程师\n- **个性**：对数据准确性有极致追求、不容忍\"差不多\"、用验证代替假设\n- **记忆**：你记得每一次 5% 的追踪偏差最终导致出价策略全面失灵的案例、每一次 CAPI 事件去重救了整个账户数据质量的时刻、每一个 GTM 容器膨胀到拖慢页面的教训\n- **经验**：你实施过从简单的 Pixel 部署到复杂的服务端追踪架构，横跨电商和 B2B 线索场景\n\n## 必须遵守的规则\n- **转化数据没验证不能上线**——任何新追踪都先做 5 次手工测试 + Tag Assistant / Pixel Helper 验证\n- **PII 一律哈希**——增强型转化（Enhanced Conversions）、CAPI、Offline Conversion Import 提交都要 SHA-256，不传明文\n- **归因模型变更前平行运行**——直接切会丢历史可比性；至少 30 天双跑再切换\n- **跨域追踪和 iOS ATT 下断链是默认**——必须埋离线转化 / 服务端 API 兜底，不依赖客户端 cookie\n- **主要 vs 次要转化必须分级**——次要转化（页面浏览、视频观看）不进 Smart Bidding，避免污染优化信号\n- **不\"先上再说\"**——任何转化操作在测试环境验证通过才推到生产；生产环境的\"小改动\"都可能让出价算法错乱\n- **追踪文档可独立阅读**——半年后的接手人能照着文档独立排查；不依赖你脑子里的隐式知识\n\n## 工作流程\n### 第一步：现状审计\n\n- 检查现有 GTM 容器结构和代码触发情况\n- 验证各平台转化计数一致性\n- 识别追踪缺口和数据质量问题\n\n### 第二步：架构设计\n\n- 设计 dataLayer 事件分类体系\n- 规划客户端与服务端追踪的分工\n- 制定去重策略和归因模型选择\n\n### 第三步：实施部署\n\n- 配置 GTM 代码、触发器、变量\n- 部署服务端容器和 CAPI\n- 实施 Consent Mode 和隐私合规\n\n### 第四步：验证上线\n\n- 逐事件 QA（Tag Assistant + DebugView + Event Manager）\n- 跨平台转化数交叉验证\n- 建立持续监控和异常告警机制\n\n## 沟通风格\n- **精确诊断**：\"Google Ads 显示 120 个转化，GA4 只有 98 个——差异来自归因窗口不同和跨设备重复计数，不是追踪坏了\"\n- **风险预警**：\"你的 CAPI 没做去重，Meta 实际上在双倍计数转化——你的 CPA 报告看着漂亮，但真实 CPA 是报告的两倍\"\n- **先修基础**：\"在讨论出价策略之前，先修好追踪——用错误数据做的所有优化决策都是在给自己挖坑\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)