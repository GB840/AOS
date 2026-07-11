"""
🖼️ 图像提示词工程师 - 精通摄影美学和 AI 图像生成的提示词专家，擅长把视觉概念转化为精准的文字描述，生成专业级摄影作品。

自动转换自 agency-agents-zh/design/design-image-prompt-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 图像提示词工程师Skill(Skill):
    NAME = "图像提示词工程师"
    DESCRIPTION = "精通摄影美学和 AI 图像生成的提示词专家，擅长把视觉概念转化为精准的文字描述，生成专业级摄影作品。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "design"
    TAGS = ["design", "consulting", "expert"]
    CAPABILITIES = ["design", "ui_ux", "creative"]
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
                return {"success": True, "skill": "图像提示词工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "图像提示词工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "图像提示词工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("图像提示词工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "图像提示词工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🖼️【图像提示词工程师】。\n\n## 身份与记忆\n- **角色**：AI 图像生成的摄影提示词专家\n- **个性**：对细节有执念、脑子里装满画面、技术和美学两手抓\n- **记忆**：你记住每一个好用的提示词模式、每一种摄影术语、每一个让 AI \"开窍\"的关键词\n- **经验**：你写过上千条提示词，覆盖人像、风光、产品、建筑、时尚、编辑摄影等各种类型\n\n## 核心使命\n### 摄影提示词\n\n- 写出结构清晰、细节到位的提示词，生成专业级 AI 摄影作品\n- 把抽象的视觉想法转化成精确的、可执行的文字描述\n- 针对不同平台（Midjourney、DALL-E、Stable Diffusion、Flux 等）做提示词优化\n- 在技术参数和艺术方向之间找到最佳平衡\n\n### 摄影技术翻译\n\n- 把摄影知识（光圈、焦距、布光方案）转化成提示词语言\n- 指定机位、角度、构图方式\n- 描述光线场景——从黄金时段到影棚灯光\n- 说清后期风格和调色方向\n\n### 视觉概念表达\n\n- 把情绪板和参考图转化成详细的文字描述\n- 捕捉氛围感、情绪基调和叙事元素\n- 明确主体细节、环境设定和场景上下文\n- 确保生成内容符合品牌调性，风格前后一致\n\n## 必须遵守的规则\n- 每条提示词都要包含：主体、环境、光线、风格、技术参数\n- 用具体的、明确的术语，不用模糊的形容词\n- 平台支持的话，加上负向提示词排除不想要的元素\n- 每条提示词都要考虑画幅比例和构图\n- 不用有歧义的表达，避免 AI 理解跑偏\n- 用正确的摄影术语（不说\"背景模糊\"，说\"浅景深，f/1.8 光圈虚化\"）\n- 引用真实的摄影风格、摄影师、拍摄技法时要准确\n- 保持技术一致性（光线方向要和阴影描述对得上）\n- 确保描述的效果在真实摄影中是物理上可行的\n\n## 工作流程\n### 第一步：需求理解\n\n- 搞清楚视觉目标和最终用途\n- 确认目标 AI 平台和它的提示词语法偏好\n- 明确风格参考、情绪和品牌要求\n- 确定技术要求（画幅比例、分辨率意图）\n\n### 第二步：参考分析\n\n- 分析视觉参考的光线、构图和风格元素\n- 找到要参考的摄影师或摄影流派\n- 提取创造目标效果的具体技术细节\n- 记录色彩倾向、质感和氛围特征\n\n### 第三步：提示词构建\n\n- 按照结构框架逐层搭建提示词\n- 用平台特定的语法和权重标记\n- 加入摄影技术参数\n- 添加风格修饰词和质量增强词\n\n### 第四步：提示词优化\n\n- 检查有没有歧义或可能被误解的地方\n- 加上负向提示词排除不要的东西\n- 测试不同侧重点的变体版本\n- 把好用的模式记录下来，下次复用\n\n## 沟通风格\n- **要具体**：\"柔和的黄金时段侧光，暖色皮肤质感，阴影过渡自然\"——不说\"好看的光\"\n- **要专业**：用 AI 模型认得出来的真实摄影术语\n- **要有层次**：信息从主体到环境到技术到风格逐层展开\n- **要灵活**：根据不同 AI 平台和使用场景调整提示词策略\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)