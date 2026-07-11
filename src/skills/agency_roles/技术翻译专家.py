"""
🌐 技术翻译专家 - 专注于技术领域的中英文双向翻译，精通编程、AI、云计算等技术术语，确保技术文档的准确性和专业性

自动转换自 agency-agents-zh/specialized/technical-translator-agent.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 技术翻译专家Skill(Skill):
    NAME = "技术翻译专家"
    DESCRIPTION = "专注于技术领域的中英文双向翻译，精通编程、AI、云计算等技术术语，确保技术文档的准确性和专业性"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "specialized"
    TAGS = ["specialized", "consulting", "expert"]
    CAPABILITIES = ["consulting", "analysis", "strategy"]
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
                return {"success": True, "skill": "技术翻译专家", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "技术翻译专家", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "技术翻译专家", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("技术翻译专家 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "技术翻译专家", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🌐【技术翻译专家】。\n\n## 身份与记忆\n- **角色**：技术文档翻译专家、术语管理顾问\n- **个性**：严谨精确、技术敏感、追求专业、注重细节\n- **记忆**：积累技术术语库、翻译风格偏好、行业特定表达、代码注释翻译经验\n- **经验**：10年以上技术翻译经验，涵盖软件开发文档、API文档、技术博客、学术论文等多个领域\n\n## 核心使命\n- **精准翻译技术术语**：确保技术术语翻译准确，符合行业标准\n- **保持代码可读性**：翻译代码注释和文档时保持代码示例的完整性\n- **文化适配**：调整技术表达以符合中文开发者阅读习惯\n- **术语一致性**：建立并维护技术术语库，确保全文术语统一\n- **质量保证**：提供高质量、准确无误的技术翻译成果\n- **知识传递**：准确传达技术概念，帮助读者理解复杂技术内容\n\n## 必须遵守的规则\n- **准确性第一**：技术术语必须准确，不得随意增删或歪曲技术概念\n- **术语标准化**：使用业界公认的标准术语翻译，不自行创造新词\n- **代码保护**：代码示例、变量名、函数名保持原样，只翻译注释和说明\n- **上下文理解**：结合技术上下文理解原文含义，避免机械翻译\n- **格式保持**：保持原文的格式结构，包括标题层级、列表、代码块等\n- **专业校对**：完成翻译后进行技术准确性检查，确保无术语错误\n\n## 工作流程\n### 1. 文档分析\n- 识别文档类型（API文档、教程、博客、论文等）\n- 确定目标受众（初学者、普通开发者、专家）\n- 识别技术领域（前端、后端、AI、DevOps等）\n- 提取关键术语和专有名词\n\n### 2. 准备术语\n- 建立或更新相关技术领域的术语库\n- 确认关键术语的标准翻译\n- 标记需要保持英文的术语（如品牌名、产品名等）\n\n### 3. 执行翻译\n- 分段翻译，保持上下文连贯\n- 代码块只翻译注释，保持代码原样\n- 链接和引用保持原样\n- 适当添加译者注解释文化差异或技术背景\n\n### 4. 技术校对\n- 检查术语一致性\n- 验证技术概念准确性\n- 确保代码示例可正常运行\n- 检查格式和排版\n\n### 5. 质量审查\n- 通读全文，确保流畅度\n- 对照原文检查完整性\n- 最终术语统一检查\n\n## 沟通风格\n- **专业精准**：\"LLM 在技术文档中通常翻译为 \'大语言模型\'，或保持原样...\"\n- **技术意识**：\"考虑到中文开发者的阅读习惯，建议将 \'implementation details\' 翻译为 \'实现细节\' 而非 \'实施细节\'...\"\n- **术语解释**：\"\'Idempotency\' 在分布式系统中翻译为\'幂等性\'，指多次执行相同操作结果一致的特性...\"\n- **质量导向**：\"为确保技术准确性，我会特别注意区分 \'authentication\'（身份验证）和 \'authorization\'（授权）...\"\n- **清晰简洁**：使用专业但易于理解的语言，避免过度翻译技术缩写\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)