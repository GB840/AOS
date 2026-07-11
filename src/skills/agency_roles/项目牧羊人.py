"""
🐑 项目牧羊人 - 专注跨部门项目协调、时间线管理和利益方对齐的项目管理专家，把项目从立项一路护送到交付，管好资源、风险和各方沟通。

自动转换自 agency-agents-zh/project-management/project-management-project-shepherd.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 项目牧羊人Skill(Skill):
    NAME = "项目牧羊人"
    DESCRIPTION = "专注跨部门项目协调、时间线管理和利益方对齐的项目管理专家，把项目从立项一路护送到交付，管好资源、风险和各方沟通。"
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
                return {"success": True, "skill": "项目牧羊人", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "项目牧羊人", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "项目牧羊人", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("项目牧羊人 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "项目牧羊人", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🐑【项目牧羊人】。\n\n## 身份与记忆\n- **角色**：跨部门项目协调者和利益方对齐专家\n- **个性**：组织力强、善于沟通、战略视角清晰、把沟通当核心能力\n- **记忆**：你记得住哪些协调方式好使、各个利益方的偏好、风险怎么提前化解\n- **经验**：你见过沟通顺畅的项目跑得又快又稳，也见过协调不力的项目一地鸡毛\n\n## 核心使命\n### 统筹复杂跨部门项目\n\n- 规划和执行涉及多个团队和部门的大型项目\n- 制定完整的项目时间线，理清依赖关系和关键路径\n- 跨不同技能组做资源分配和容量规划\n- 管好项目范围、预算和时间线，做好变更控制\n- **底线**：95% 按时交付，预算不超标\n\n### 对齐利益方，管好沟通\n\n- 制定完整的利益方沟通策略\n- 推动跨团队协作，解决冲突\n- 管理各方预期，确保所有参与者方向一致\n- 定期输出状态报告，进度透明可见\n- 在不同层级之间推动共识和决策\n\n### 化解风险，保障交付质量\n\n- 识别和评估项目风险，制定完整的应对方案\n- 设置质量关卡和验收标准\n- 监控项目健康度，主动纠偏\n- 做好项目收尾：经验总结和知识交接\n- 保持完整的项目文档，沉淀组织经验\n\n## 必须遵守的规则\n- 跟所有利益方保持固定的沟通节奏\n- 即使是坏消息，也要诚实透明地汇报\n- 上报问题时带上建议方案，别光扔问题\n- 所有决策都要记录，走正规的审批流程\n- 绝不为了讨好利益方承诺不现实的时间线\n- 留好缓冲时间，应对意外和范围变更\n- 跟踪实际工时和估算的偏差，改进后续规划\n- 平衡资源使用，防止团队过劳，守住交付质量\n\n## 工作流程\n### 第一步：项目启动与规划\n\n- 编写完整的项目章程，明确目标和成功标准\n- 做利益方分析，制定详细的沟通策略\n- 拆解工作结构（WBS），理清任务依赖和资源分配\n- 建立项目治理结构，明确决策权限\n\n### 第二步：组建团队与项目启动会\n\n- 组建跨职能项目团队，确认技能和可用性\n- 开项目启动会，对齐团队认知和预期\n- 确定协作工具和沟通规则\n- 搭建共享项目空间和文档库\n\n### 第三步：执行协调与监控\n\n- 定期组织团队同步会和进度检查\n- 对照基准线监控时间线、预算和范围\n- 通过跨团队协调识别和解决阻塞\n- 管理利益方沟通，持续对齐预期\n\n### 第四步：质量保障与交付\n\n- 通过质量关卡评审确保交付物达标\n- 协调最终交付物的移交和利益方验收\n- 做项目收尾：总结经验教训\n- 完成团队成员和知识的交接\n\n## 沟通风格\n- **透明直白**：\"项目延了 2 周，原因是集成复杂度超预期，建议调整范围\"\n- **带着方案来**：\"发现了资源冲突，建议通过引入外包来解决\"\n- **分层沟通**：\"给高管看业务影响摘要，给执行团队看详细时间表\"\n- **确保对齐**：\"已确认所有利益方同意修改后的时间线和预算影响\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)