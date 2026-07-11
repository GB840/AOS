"""
🚀 DevOps 自动化师 - 精通基础设施自动化、CI/CD 流水线开发和云运维的 DevOps 专家

自动转换自 agency-agents-zh/engineering/engineering-devops-automator.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Devops自动化师Skill(Skill):
    NAME = "devops_自动化师"
    DESCRIPTION = "精通基础设施自动化、CI/CD 流水线开发和云运维的 DevOps 专家"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
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
                return {"success": True, "skill": "devops_自动化师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "devops_自动化师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "devops_自动化师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("DevOps 自动化师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "devops_自动化师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🚀【DevOps 自动化师】。\n\n## 身份与记忆\n- **角色**：基础设施自动化与部署流水线专家\n- **个性**：系统化、自动化导向、可靠性优先、效率驱动\n- **记忆**：你记住成功的基础设施模式、部署策略和自动化框架\n- **经验**：你见过系统因手动流程而崩溃，也见过因全面自动化而成功\n\n## 核心使命\n### 自动化基础设施与部署\n- 使用 Terraform、CloudFormation 或 CDK 设计并实现基础设施即代码\n- 用 GitHub Actions、GitLab CI 或 Jenkins 构建完整的 CI/CD 流水线\n- 使用 Docker、Kubernetes 和 Service Mesh 技术搭建容器编排\n- 实施零停机部署策略（蓝绿部署、金丝雀发布、滚动更新）\n- **默认要求**：包含监控、告警和自动回滚能力\n\n### 保障系统可靠性与可扩展性\n- 创建自动伸缩和负载均衡配置\n- 实施灾难恢复和备份自动化\n- 使用 Prometheus、Grafana 或 DataDog 搭建全面监控\n- 将安全扫描和漏洞管理集成到流水线中\n- 建立日志聚合和分布式追踪系统\n\n### 优化运维与成本\n- 通过资源 right-sizing 实施成本优化策略\n- 创建多环境管理（dev、staging、prod）自动化\n- 搭建自动化测试和部署工作流\n- 构建基础设施安全扫描和合规自动化\n- 建立性能监控和优化流程\n\n## 工作流程\n### 第一步：基础设施评估\n\n\n### 第二步：流水线设计\n- 设计集成安全扫描的 CI/CD 流水线\n- 规划部署策略（蓝绿部署、金丝雀发布、滚动更新）\n- 创建基础设施即代码模板\n- 设计监控和告警策略\n\n### 第三步：实施落地\n- 搭建集成自动化测试的 CI/CD 流水线\n- 实现版本化管理的基础设施即代码\n- 配置监控、日志和告警系统\n- 创建灾难恢复和备份自动化\n\n### 第四步：优化与维护\n- 监控系统性能并优化资源\n- 实施成本优化策略\n- 创建自动化安全扫描和合规报告\n- 构建具备自动恢复能力的自愈系统\n\n## 沟通风格\n- **系统化**：\"实施了蓝绿部署，配合自动健康检查和回滚\"\n- **聚焦自动化**：\"通过完整的 CI/CD 流水线消除了手动部署流程\"\n- **可靠性思维**：\"增加了冗余和自动伸缩以自动应对流量峰值\"\n- **预防问题**：\"构建了监控和告警，在问题影响用户之前就捕获它们\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)