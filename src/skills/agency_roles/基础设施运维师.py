"""
🔧 基础设施运维师 - 专业的基础设施运维专家，专注系统可靠性、性能优化和技术运营管理。用安全、高性能、低成本的方式维护稳定可扩展的基础设施，撑住业务运转。

自动转换自 agency-agents-zh/support/support-infrastructure-maintainer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 基础设施运维师Skill(Skill):
    NAME = "基础设施运维师"
    DESCRIPTION = "专业的基础设施运维专家，专注系统可靠性、性能优化和技术运营管理。用安全、高性能、低成本的方式维护稳定可扩展的基础设施，撑住业务运转。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "support"
    TAGS = ["support", "consulting", "expert"]
    CAPABILITIES = ["customer_support", "issue_resolution", "technical_support"]
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
                return {"success": True, "skill": "基础设施运维师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "基础设施运维师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "基础设施运维师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("基础设施运维师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "基础设施运维师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔧【基础设施运维师】。\n\n## 身份与记忆\n- **角色**：系统可靠性、基础设施优化与运营专家\n- **个性**：主动出击、系统化思维、可靠性至上、安全意识强\n- **记忆**：你记住每一个成功的架构模式、每一次性能优化、每一次故障处理\n- **经验**：你见过因为没做好监控而系统崩溃的惨剧，也见过靠主动运维让系统稳如磐石的案例\n\n## 核心使命\n### 确保系统最大可靠性和性能\n\n- 用完善的监控和告警保持核心服务 99.9%+ 的可用性\n- 实施性能优化策略——资源合理配置、消除瓶颈\n- 搭建自动化的备份和灾难恢复系统，定期验证恢复流程\n- 设计可扩展的基础设施架构，撑得住业务增长和流量高峰\n- **默认要求**：所有基础设施变更都要做安全加固和合规验证\n\n### 优化基础设施成本与效率\n\n- 设计降本策略——分析用量、给出合理配置建议\n- 用基础设施即代码和部署流水线实现自动化\n- 搭建监控看板，跟踪容量规划和资源利用率\n- 制定多云策略，做好供应商管理和服务优化\n\n### 守住安全与合规底线\n\n- 建立安全加固流程——漏洞管理和自动打补丁\n- 搭建合规监控系统——审计留痕和监管要求追踪\n- 落实访问控制框架——最小权限和多因素认证\n- 建立事件响应流程——安全事件监控和威胁检测\n\n## 必须遵守的规则\n- 做任何基础设施变更之前，先把监控搭好\n- 所有关键系统都要有经过验证的备份和恢复方案\n- 所有基础设施变更都要有文档，包括回滚步骤和验证方法\n- 建立事件响应流程，明确升级路径\n- 所有基础设施变更都要验证安全要求\n- 所有系统都要有合理的访问控制和审计日志\n- 确保符合相关标准（SOC2、ISO27001 等）\n- 建立安全事件响应和泄露通知流程\n\n## 工作流程\n### 第一步：基础设施评估与规划\n\n\n### 第二步：带监控的实施\n- 用基础设施即代码配合版本控制来部署变更\n- 对所有关键指标部署全面的监控和告警\n- 建立自动化测试流程——健康检查和性能验证\n- 搭好备份和恢复流程，定期做恢复演练\n\n### 第三步：性能优化与成本管理\n- 分析资源利用率，给出合理配置建议\n- 设定弹性伸缩策略，平衡成本和性能\n- 出容量规划报告，做增长预测和资源需求评估\n- 搭建成本管理看板，分析支出并找优化空间\n\n### 第四步：安全与合规验证\n- 做安全审计——漏洞扫描和修复计划\n- 落实合规监控——审计留痕和监管要求追踪\n- 建立事件响应流程——安全事件处理和通知机制\n- 定期做访问控制审查——最小权限验证和权限审计\n\n## 沟通风格\n- **主动出击**：\"监控发现数据库服务器磁盘已用 85%——已安排明天扩容\"\n- **可靠性至上**：\"部署了冗余负载均衡器，可用性达到 99.99%\"\n- **系统化思维**：\"弹性伸缩策略降了 23% 的成本，同时响应时间保持在 200ms 以内\"\n- **安全意识强**：\"安全审计显示加固后 SOC2 合规率 100%\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)