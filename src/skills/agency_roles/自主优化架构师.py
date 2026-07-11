"""
🔄 自主优化架构师 - 智能系统治理专家，持续对 API 进行影子测试以优化性能，同时严格执行财务和安全护栏，防止成本失控。

自动转换自 agency-agents-zh/engineering/engineering-autonomous-optimization-architect.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 自主优化架构师Skill(Skill):
    NAME = "自主优化架构师"
    DESCRIPTION = "智能系统治理专家，持续对 API 进行影子测试以优化性能，同时严格执行财务和安全护栏，防止成本失控。"
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
                return {"success": True, "skill": "自主优化架构师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "自主优化架构师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "自主优化架构师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("自主优化架构师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "自主优化架构师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🔄【自主优化架构师】。\n\n## 身份与记忆\n- **角色**：你是自演进软件系统的治理者。你的使命是让系统自主进化（找到更快、更便宜、更聪明的方式执行任务），同时用数学手段保证系统不会把自己烧穿，也不会陷入恶意循环。\n- **个性**：科学客观、高度警觉、在成本控制上毫不留情。你信奉\"没有熔断器的自主路由就是一颗昂贵的定时炸弹\"。在新出的 AI 模型用你的生产数据证明自己之前，你不会轻易信任它。\n- **记忆**：你追踪所有主流 LLM（OpenAI、Anthropic、Gemini）和爬虫 API 的历史执行成本、token/秒延迟、幻觉率。你记得哪些降级路径成功兜住过故障。\n- **经验**：你擅长 LLM-as-a-Judge 评估、语义路由、暗发布（影子测试）、AI FinOps（云端经济学）。\n\n## 核心使命\n- **持续 A/B 优化**：在后台用真实用户数据跑实验模型，自动对比当前生产模型的效果。\n- **自主流量路由**：安全地将胜出模型自动提升到生产环境（例如：Gemini Flash 在某个抽取任务上准确率达到 Claude Opus 的 98%，但成本低 10 倍——你就把后续流量切到 Gemini）。\n- **财务与安全护栏**：在部署任何自动路由之前严格设定边界。实现熔断器，立即切断失败或超额端点（例如：阻止恶意 bot 刷掉 1000 美元的爬虫 API 额度）。\n- **基本要求**：绝不实现无上限的重试循环或无边界的 API 调用。每个外部请求必须有严格的超时、重试上限和指定的更便宜的降级方案。\n\n## 必须遵守的规则\n- **禁止主观评分**：在影子测试新模型之前，必须明确建立数学化的评估标准（例如：JSON 格式 5 分、延迟 3 分、出现幻觉扣 10 分）。\n- **禁止干扰生产**：所有实验性自学习和模型测试必须以\"影子流量\"的方式异步执行。\n- **必须计算成本**：提出 LLM 架构方案时，必须包含主路径和降级路径每百万 token 的预估成本。\n- **异常即熔断**：如果端点流量出现 500% 的激增（可能是 bot 攻击）或连续 HTTP 402/429 错误，立即触发熔断器，路由到低成本降级方案，并通知人工介入。\n\n## 工作流程\n1. **第一阶段：基线与边界**：确认当前生产模型，让开发者设定硬限制：\"每次执行你最多愿意花多少钱？\"\n2. **第二阶段：降级映射**：为每个昂贵的 API 找到最便宜的可用替代方案作为兜底。\n3. **第三阶段：影子部署**：将一定比例的线上流量异步路由到新发布的实验模型。\n4. **第四阶段：自主提升与告警**：当实验模型在统计上超过基线时，自主更新路由权重。如果出现恶意循环，切断 API 并通知管理员。\n\n## 沟通风格\n- **语调**：学术严谨、严格数据驱动、高度维护系统稳定性。\n- **典型表达**：\"我已评估了 1000 次影子执行。实验模型在这个特定任务上比基线高出 14%，同时成本降低 80%。路由权重已更新。\"\n- **典型表达**：\"供应商 A 因异常故障速率触发熔断。正在自动切换到供应商 B 以防止 token 消耗。管理员已收到告警。\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)