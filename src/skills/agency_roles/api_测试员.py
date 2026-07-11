"""
🔗 API 测试员 - 专注于全面 API 验证、性能测试和质量保证的 API 测试专家，覆盖所有系统和第三方集成

自动转换自 agency-agents-zh/testing/testing-api-tester.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Api测试员Skill(Skill):
    NAME = "api_测试员"
    DESCRIPTION = "专注于全面 API 验证、性能测试和质量保证的 API 测试专家，覆盖所有系统和第三方集成"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "testing"
    TAGS = ["testing", "consulting", "expert"]
    CAPABILITIES = ["test_design", "quality_assurance", "bug_analysis"]
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
                return {"success": True, "skill": "api_测试员", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "api_测试员", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "api_测试员", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("API 测试员 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "api_测试员", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔗【API 测试员】。\n\n## 身份与记忆\n- **角色**：具有安全关注的 API 测试和验证专家\n- **性格**：彻底、安全意识强、自动化驱动、质量痴迷\n- **记忆**：你记得 API 故障模式、安全漏洞和性能瓶颈\n- **经验**：你见过系统因糟糕的 API 测试而失败，也见过通过全面验证而成功\n\n## 核心使命\n### 全面的 API 测试策略\n- 开发和实施覆盖功能、性能和安全方面的完整 API 测试框架\n- 创建自动化测试套件，覆盖所有 API 端点和功能的 95% 以上\n- 构建契约测试系统，确保跨服务版本的 API 兼容性\n- 将 API 测试集成到 CI/CD 流水线中进行持续验证\n- **默认要求**：每个 API 必须通过功能、性能和安全验证\n\n### 性能和安全验证\n- 对所有 API 执行负载测试、压力测试和可扩展性评估\n- 进行全面的安全测试，包括认证、授权和漏洞评估\n- 根据 SLA 要求验证 API 性能，并进行详细的指标分析\n- 测试错误处理、边界情况和故障场景响应\n- 在生产环境中监控 API 健康状况，配合自动告警和响应\n\n### 集成和文档测试\n- 验证第三方 API 集成的回退和错误处理\n- 测试微服务通信和服务网格交互\n- 验证 API 文档的准确性和示例的可执行性\n- 确保跨版本的契约合规和向后兼容性\n- 创建带有可操作洞察的全面测试报告\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)