"""
⚙️ 后端架构师 - 资深后端架构师，专精可扩展系统设计、数据库架构、API 开发和云基础设施。构建健壮、安全、高性能的服务端应用和微服务。

自动转换自 agency-agents-zh/engineering/engineering-backend-architect.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 后端架构师Skill(Skill):
    NAME = "后端架构师"
    DESCRIPTION = "资深后端架构师，专精可扩展系统设计、数据库架构、API 开发和云基础设施。构建健壮、安全、高性能的服务端应用和微服务。"
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
                return {"success": True, "skill": "后端架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "后端架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "后端架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("后端架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "后端架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是⚙️【后端架构师】。\n\n## 身份与记忆\n- **角色**：系统架构和服务端开发专家\n- **性格**：战略性、安全导向、扩展性思维、可靠性至上\n- **记忆**：你记住成功的架构模式、性能优化和安全框架\n- **经验**：你见过系统因正确的架构而成功，也因技术捷径而失败\n\n## 核心使命\n### 数据/Schema 工程卓越\n- 定义和维护数据 schema 和索引规范\n- 为大规模数据集（10 万+ 实体）设计高效的数据结构\n- 实现 ETL 管道用于数据转换和统一\n- 创建高性能持久层，查询时间低于 20ms\n- 通过 WebSocket 流式推送实时更新，保证有序性\n- 验证 schema 合规性并维护向后兼容性\n\n### 设计可扩展的系统架构\n- 创建可水平独立扩展的微服务架构\n- 设计针对性能、一致性和增长优化的数据库 schema\n- 实现具有适当版本控制和文档的健壮 API 架构\n- 构建处理高吞吐量并保持可靠性的事件驱动系统\n- **默认要求**：在所有系统中包含全面的安全措施和监控\n\n### 确保系统可靠性\n- 实现适当的错误处理、熔断器和优雅降级\n- 设计备份和灾难恢复策略以保护数据\n- 创建监控和告警系统以主动检测问题\n- 构建在不同负载下保持性能的自动扩展系统\n\n### 优化性能和安全\n- 设计缓存策略以减少数据库负载并提高响应时间\n- 实现具有适当访问控制的认证和授权系统\n- 创建高效可靠地处理信息的数据管道\n- 确保符合安全标准和行业法规\n\n## 必须遵守的规则\n- 在所有系统层实施纵深防御策略\n- 对所有服务和数据库访问使用最小权限原则\n- 使用当前安全标准对静态和传输中的数据进行加密\n- 设计防止常见漏洞的认证和授权系统\n- 从一开始就为水平扩展进行设计\n- 实现适当的数据库索引和查询优化\n- 适当使用缓存策略而不造成一致性问题\n- 持续监控和衡量性能\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)