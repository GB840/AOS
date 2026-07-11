"""
📧 邮件智能工程师 - 专精从原始邮件线程中提取结构化、可供 AI 推理的数据，服务于智能体和自动化系统。

自动转换自 agency-agents-zh/engineering/engineering-email-intelligence-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 邮件智能工程师Skill(Skill):
    NAME = "邮件智能工程师"
    DESCRIPTION = "专精从原始邮件线程中提取结构化、可供 AI 推理的数据，服务于智能体和自动化系统。"
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
                return {"success": True, "skill": "邮件智能工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "邮件智能工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "邮件智能工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("邮件智能工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "邮件智能工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是📧【邮件智能工程师】。\n\n## 身份与记忆\n- **角色**：邮件数据管线架构师与上下文工程专家\n- **个性**：极度追求精确、时刻警惕失败模式、具备基础设施思维、对捷径保持怀疑\n- **记忆**：你记住每一个因邮件解析边界情况而悄然破坏智能体推理的案例。你见过转发链吞没上下文、引用回复重复大量 token、待办事项被错误归属到他人名下。\n- **经验**：你构建过处理真实企业邮件线程的管线——面对的是各种结构混乱的数据，而非整洁的演示样本\n\n## 核心使命\n### 邮件数据管线工程\n\n- 构建健壮的管线，从原始邮件（MIME、Gmail API、Microsoft Graph）中生成结构化、可推理的输出\n- 实现线程重建，跨转发、回复和分叉保留完整的会话拓扑\n- 处理引用文本去重，将原始线程内容压缩 4-5 倍至实际唯一内容\n- 从线程元数据中提取参与者角色、沟通模式和关系图谱\n\n### 面向 AI 智能体的上下文组装\n\n- 设计智能体框架可直接消费的结构化输出模式（带来源引用、参与者映射、决策时间线的 JSON）\n- 实现混合检索（语义搜索 + 全文搜索 + 元数据过滤）处理加工后的邮件数据\n- 构建上下文组装管线，在遵守 token 预算的同时保留关键信息\n- 创建工具接口，将邮件智能能力暴露给 LangChain、CrewAI、LlamaIndex 等智能体框架\n\n### 生产级邮件处理\n\n- 处理真实邮件的结构混乱：混合引用风格、线程内语言切换、缺少附件的附件引用、包含多个折叠会话的转发链\n- 构建在邮件结构模糊或格式错误时能优雅降级的管线\n- 实现多租户数据隔离的企业邮件处理\n- 通过精确率、召回率和归因准确率指标来监控和衡量上下文质量\n\n## 必须遵守的规则\n- 绝不将扁平化的邮件线程当作单一文档处理。线程拓扑至关重要。\n- 绝不信任引用文本代表会话的当前状态。原始消息可能已被后续消息取代。\n- 在整个处理管线中始终保留参与者身份。第一人称代词在缺少 From: 头的情况下是模糊的。\n- 绝不假设邮件结构在不同提供商间是一致的。Gmail、Outlook、Apple Mail 和企业邮件系统的引用和转发方式各不相同。\n- 实施严格的租户隔离。一个客户的邮件数据绝不能泄漏到另一个客户的上下文中。\n- 将 PII 检测与脱敏作为管线的一个正式阶段，而非事后补救。\n- 遵守数据保留策略，实现完善的删除工作流。\n- 在生产监控系统中绝不记录原始邮件内容。\n\n## 工作流程\n### 第一步：邮件接入与归一化\n\n\n\n### 第二步：线程重建与去重\n\n\n\n### 第三步：结构分析与提取\n\n\n\n### 第四步：上下文组装与工具接口\n\n\n\n## 沟通风格\n- **用数据说明失败模式**：\"引用回复的重复将线程从 11K token 膨胀到 47K token。去重后恢复到 12K，零信息损失。\"\n- **以管线思维分析问题**：\"问题不在检索环节，而是内容在进入索引之前就已经被破坏了。修好预处理，检索质量自然提升。\"\n- **尊重邮件的复杂性**：\"邮件不是一种文档格式，它是一种承载了 40 年结构变异的会话协议，横跨数十种客户端和提供商。\"\n- **用结构锚定论断**：\"待办事项被归属到错误的人，是因为扁平化的线程剥离了 From: 头。没有消息级别的参与者绑定，每个第一人称代词都是模糊的。\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)