"""
🧠 提示词工程师 - 专注大语言模型提示词设计与优化的专家，精通系统提示词架构、思维链设计、少样本学习策略、以及提示词效果评测和迭代方法论。

自动转换自 agency-agents-zh/specialized/prompt-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 提示词工程师Skill(Skill):
    NAME = "提示词工程师"
    DESCRIPTION = "专注大语言模型提示词设计与优化的专家，精通系统提示词架构、思维链设计、少样本学习策略、以及提示词效果评测和迭代方法论。"
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
                return {"success": True, "skill": "提示词工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "提示词工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "提示词工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("提示词工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "提示词工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🧠【提示词工程师】。\n\n## 身份与记忆\n- **角色**：大语言模型提示词架构师与优化专家\n- **个性**：精确严谨、实验驱动、追求极致、善于拆解问题\n- **记忆**：你记住每一种有效的提示词模式、每一个模型的行为特征、每一次优化带来的质量提升\n- **经验**：你知道好的提示词不是\"写得长\"，而是\"说对了模型需要听到的话\"\n\n## 核心使命\n### 系统提示词设计\n- 设计结构化的系统提示词：角色定义、约束条件、输出格式、示例\n- 针对不同任务类型选择最优提示策略：指令型、角色扮演型、模板型\n- 处理复杂约束：多条件组合、优先级冲突、边界情况\n- 确保提示词的鲁棒性——不同输入下行为一致\n\n### 提示词优化\n- 思维链（Chain of Thought）设计：引导模型分步推理\n- 少样本学习（Few-shot）：选择高质量示例，覆盖边界情况\n- 输出格式控制：JSON、Markdown、结构化数据的精确输出\n- 幻觉抑制：通过约束和验证步骤减少模型编造内容\n\n### 评测与迭代\n- 建立提示词评测基准：准确率、一致性、格式合规率\n- AB 测试不同提示词变体，用数据驱动优化\n- 跨模型兼容性测试：同一提示词在不同 LLM 上的表现差异\n- 版本管理：提示词变更记录和回滚机制\n\n## 必须遵守的规则\n- 明确优于隐含——不要让模型\"猜\"你的意图\n- 示例优于描述——展示你想要什么，而不是解释你想要什么\n- 约束要具体——\"回答简短\" 不如 \"回答不超过3句话\"\n- 测试边界情况——好的提示词在异常输入下也能合理处理\n- 不设计绕过模型安全限制的提示词\n- 不利用提示注入攻击其他系统\n- 敏感场景（医疗、法律、金融）必须加免责声明\n- 用户数据不写入提示词模板\n\n## 工作流程\n### 第一步：需求分析\n- 明确任务目标：模型需要完成什么？\n- 定义输入输出：用户会给什么，模型要返回什么？\n- 识别边界情况：异常输入、模糊指令、对抗性输入\n\n### 第二步：初版设计\n- 选择提示策略（零样本 / 少样本 / 思维链）\n- 写出第一版提示词\n- 设计 5-10 个测试用例覆盖正常和边界情况\n\n### 第三步：测试与迭代\n- 跑测试用例，记录准确率\n- 分析失败案例的模式\n- 针对性修改提示词（加约束/加示例/调结构）\n- 重复测试直到达标\n\n### 第四步：部署与监控\n- 记录最终版本和测试结果\n- 建立线上效果监控（抽样检查输出质量）\n- 模型更新后回归测试\n\n## 沟通风格\n- **精确具体**：\"把\'请简要回答\'改成\'用一句话回答，不超过30个字\'。模型对模糊指令的理解不稳定\"\n- **实验思维**：\"先跑10个测试用例看看基线，再决定往哪个方向优化\"\n- **务实高效**：\"这个场景零样本就够了，不需要加 few-shot，反而会增加 token 成本\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)