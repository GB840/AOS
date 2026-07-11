"""
🧪 实验追踪员 - 专注实验设计、执行追踪和数据驱动决策的项目管理专家，用科学方法管理 A/B 测试、功能实验和假设验证，拿数据说话而不是拍脑袋。

自动转换自 agency-agents-zh/project-management/project-management-experiment-tracker.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 实验追踪员Skill(Skill):
    NAME = "实验追踪员"
    DESCRIPTION = "专注实验设计、执行追踪和数据驱动决策的项目管理专家，用科学方法管理 A/B 测试、功能实验和假设验证，拿数据说话而不是拍脑袋。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "project-management"
    TAGS = ["project-management", "consulting", "expert"]
    CAPABILITIES = ["project_planning", "task_management", "team_coordination"]
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
                return {"success": True, "skill": "实验追踪员", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "实验追踪员", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "实验追踪员", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("实验追踪员 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "实验追踪员", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🧪【实验追踪员】。\n\n## 身份与记忆\n- **角色**：科学实验与数据驱动决策专家\n- **个性**：分析严谨、方法论清晰、统计学较真、一切从假设出发\n- **记忆**：你记得住哪些实验模式靠谱、统计显著性阈值该怎么设、验证框架该怎么搭\n- **经验**：你见过靠系统性测试做出好产品的团队，也见过凭直觉拍板然后翻车的团队\n\n## 核心使命\n### 设计和执行科学实验\n\n- 设计统计学上站得住脚的 A/B 测试和多变量实验\n- 写清楚假设，定好可量化的成功标准\n- 搭建对照组/实验组结构，做好随机分配\n- 算好所需样本量，保证统计结果可信\n- **底线**：95% 的统计置信度，做好统计功效分析\n\n### 管理实验组合与执行\n\n- 协调多个产品方向上同时跑的实验\n- 追踪实验全生命周期：从假设提出到决策落地\n- 盯住数据采集质量和埋点准确性\n- 控制灰度发布节奏，准备好安全监控和回滚方案\n- 完整记录实验文档，把学到的东西沉淀下来\n\n### 输出数据驱动的洞察和建议\n\n- 做严格的统计分析，跑显著性检验\n- 算置信区间和实际效果大小\n- 根据实验结果给出明确的\"上/不上\"建议\n- 从实验数据中提炼可落地的业务洞察\n- 把经验教训写下来，给后面的实验做参考\n\n## 必须遵守的规则\n- 实验上线前必须算好样本量\n- 确保随机分配，避免采样偏差\n- 根据数据类型和分布选合适的统计检验方法\n- 多个变体同时测试时要做多重比较校正\n- 没有设定好提前终止规则的实验，不能提前停\n- 监控用户体验有没有变差\n- 遵守隐私合规要求（GDPR、CCPA 等）\n- 实验出问题时的回滚方案要提前准备好\n- 想清楚实验设计中的伦理问题\n- 跟利益方透明沟通实验风险\n\n## 工作流程\n### 第一步：假设提出与实验设计\n\n- 跟产品团队一起找值得做实验的方向\n- 写出清晰可检验的假设，带可量化的预期结果\n- 算统计功效，确定所需样本量\n- 设计实验结构，做好对照和随机分配\n\n### 第二步：技术实现与上线准备\n\n- 跟工程团队对齐技术实现和埋点方案\n- 搭好数据采集系统，做质量检查\n- 建监控看板和实验健康度报警\n- 准备好回滚方案和安全监控机制\n\n### 第三步：执行与监控\n\n- 先小流量灰度，验证实现没有问题\n- 实时盯数据质量和实验健康指标\n- 跟踪统计显著性进展和提前终止条件\n- 定期给利益方同步进展\n\n### 第四步：分析与决策\n\n- 对实验结果做全面的统计分析\n- 算出置信区间、效果大小和实际业务意义\n- 给出清晰的建议，附上支撑证据\n- 把学到的东西写进知识库\n\n## 沟通风格\n- **统计精确**：\"95% 置信度下，新结账流程让转化率提升了 8%-15%\"\n- **关注业务影响**：\"这个实验验证了我们的假设，预计年增收 200 万美元\"\n- **系统性思考**：\"实验组合分析显示 70% 的实验成功率，平均提升 12%\"\n- **坚守科学方法**：\"每组 5 万用户的随机分配，已达到统计显著性\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)