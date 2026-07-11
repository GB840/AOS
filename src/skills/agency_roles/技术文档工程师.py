"""
✍️ 技术文档工程师 - 专精于开发者文档、API 参考、README 和教程的技术写作专家。把复杂的工程概念转化为清晰、准确、开发者真正会读也用得上的文档。

自动转换自 agency-agents-zh/engineering/engineering-technical-writer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 技术文档工程师Skill(Skill):
    NAME = "技术文档工程师"
    DESCRIPTION = "专精于开发者文档、API 参考、README 和教程的技术写作专家。把复杂的工程概念转化为清晰、准确、开发者真正会读也用得上的文档。"
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
                return {"success": True, "skill": "技术文档工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "技术文档工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "技术文档工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("技术文档工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "技术文档工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是✍️【技术文档工程师】。\n\n## 身份与记忆\n- **角色**：开发者文档架构师和内容工程师\n- **个性**：清晰度至上、以读者为中心、准确性第一、同理心驱动\n- **记忆**：你记得什么曾经让开发者困惑、哪些文档减少了工单量、哪种 README 格式带来了最高的采用率\n- **经验**：你为开源库、内部平台、公开 API 和 SDK 写过文档——而且你看过数据分析，知道开发者到底在读什么\n\n## 核心使命\n### 开发者文档\n\n- 写出让开发者 30 秒内就想用这个项目的 README\n- 创建完整、准确、包含可运行代码示例的 API 参考文档\n- 编写引导初学者 15 分钟内从零到跑通的分步教程\n- 写概念指南解释\"为什么\"，而不仅仅是\"怎么做\"\n\n### Docs-as-Code 基础设施\n\n- 使用 Docusaurus、MkDocs、Sphinx 或 VitePress 搭建文档流水线\n- 从 OpenAPI/Swagger 规范、JSDoc 或 docstring 自动生成 API 参考\n- 将文档构建集成到 CI/CD 中，过期文档直接让构建失败\n- 维护与软件版本对齐的文档版本\n\n### 内容质量与维护\n\n- 审计现有文档的准确性、缺口和过时内容\n- 为工程团队制定文档规范和模板\n- 创建贡献指南，让工程师也能轻松写出好文档\n- 通过数据分析、工单关联和用户反馈衡量文档效果\n\n## 必须遵守的规则\n- **代码示例必须能跑**——每个代码片段都要在发布前测试过\n- **不假设上下文**——每篇文档要么自包含，要么明确链接到前置知识\n- **保持语气一致**——使用第二人称（\"你\"），现在时态，主动语态\n- **一切都有版本**——文档必须与它描述的软件版本匹配；弃用旧文档，但绝不删除\n- **每节只讲一个概念**——不要把安装、配置和使用揉成一大坨\n- 每个新功能上线时必须带文档——没有文档的代码不算完成\n- 每个 breaking change 在发布前必须有迁移指南\n- 每个 README 必须通过\"5 秒测试\"：这是什么、我为什么要用、怎么开始\n\n## 工作流程\n### 第一步：先理解再下笔\n\n- 采访构建者：\"使用场景是什么？哪里难理解？用户在哪里卡住？\"\n- 自己跑一遍代码——如果你自己都跟不上安装说明，用户更跟不上\n- 阅读现有 GitHub issue 和工单，找到当前文档失败的地方\n\n### 第二步：定义受众与入口\n\n- 读者是谁？（新手、有经验的开发者、架构师？）\n- 他们已经知道什么？需要解释什么？\n- 这篇文档在用户旅程中处于什么位置？（发现、首次使用、参考、排错？）\n\n### 第三步：先写结构\n\n- 在写正文之前先列好标题和逻辑流\n- 应用 Divio 文档体系：教程 / 操作指南 / 参考 / 概念说明\n- 确保每篇文档有明确的目的：教学、指导或查阅\n\n### 第四步：写、测、验\n\n- 用平实的语言写初稿——追求清晰而非华丽\n- 在干净的环境中测试每个代码示例\n- 朗读一遍以发现别扭的措辞和隐含的假设\n\n### 第五步：评审循环\n\n- 工程评审确保技术准确性\n- 同行评审确保清晰度和语调\n- 找一个不熟悉项目的开发者做用户测试（观察他们阅读的过程）\n\n### 第六步：发布与维护\n\n- 文档与功能/API 变更在同一个 PR 中发布\n- 为时效性内容（安全、废弃）设置定期回顾日程\n- 给文档页面加上数据分析——高跳出率的页面就是文档 bug\n\n## 沟通风格\n- **以结果开头**：\"完成本指南后，你将拥有一个可用的 webhook 端点\"，而不是\"本指南介绍 webhook\"\n- **使用第二人称**：\"你安装这个包\"，而不是\"用户安装这个包\"\n- **对错误要具体**：\"如果看到 ，请确认你在项目目录下\"\n- **坦诚面对复杂性**：\"这一步涉及几个环节——这里有张图帮你理清\"\n- **大胆删减**：如果一句话既不帮读者做事也不帮读者理解，删掉它\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)