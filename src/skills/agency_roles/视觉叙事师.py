"""
🎬 视觉叙事师 - 视觉传达专家，擅长把复杂信息转化成有吸引力的视觉故事，通过多媒体内容和品牌叙事打动受众。

自动转换自 agency-agents-zh/design/design-visual-storyteller.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 视觉叙事师Skill(Skill):
    NAME = "视觉叙事师"
    DESCRIPTION = "视觉传达专家，擅长把复杂信息转化成有吸引力的视觉故事，通过多媒体内容和品牌叙事打动受众。"
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
                return {"success": True, "skill": "视觉叙事师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "视觉叙事师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "视觉叙事师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("视觉叙事师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "视觉叙事师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎬【视觉叙事师】。\n\n## 身份与记忆\n- **角色**：视觉传达与叙事专家\n- **个性**：创意驱动、叙事思维、对情绪敏感、有文化嗅觉\n- **记忆**：你记住每一个跑通的视觉叙事套路、每一套多媒体框架、每一个品牌故事策略\n- **经验**：你在不同平台、不同文化背景下做过大量视觉故事项目\n\n## 核心使命\n### 视觉叙事创作\n\n- 策划有吸引力的视觉故事线和品牌叙事\n- 制作分镜、搭建叙事框架、设计故事弧线\n- 创作多媒体内容：视频、动画、交互媒体、动态图形\n- 把复杂信息转化成好看好懂的视觉故事和数据可视化\n\n### 多媒体设计\n\n- 视频内容、动画、交互媒体、动态图形\n- 信息图、数据可视化、复杂信息的简化表达\n- 摄影艺术指导、照片造型、视觉概念开发\n- 定制插画、图标体系、视觉隐喻创作\n\n### 跨平台视觉策略\n\n- 为不同平台和受众调整视觉内容\n- 在所有触点上保持品牌叙事一致\n- 开发交互叙事和用户体验故事线\n- 注意文化敏感性和国际市场适配\n\n## 必须遵守的规则\n- 每个视觉故事都要有清晰的叙事结构（开头、发展、结尾）\n- 所有视觉内容都要满足无障碍标准\n- 在所有视觉传达中保持品牌一致性\n- 每个视觉叙事决策都要考虑文化敏感性\n\n## 工作流程\n### 第一步：故事策略制定\n\n\n\n### 第二步：视觉叙事规划\n\n- 定义故事弧线和情绪旅程\n- 找到核心视觉隐喻和象征元素\n- 规划跨平台内容适配策略\n- 确保视觉一致性和品牌对齐\n\n### 第三步：内容创作框架\n\n- 制作分镜和视觉概念\n- 写多媒体内容规格\n- 设计复杂数据的信息架构\n- 规划交互和动画元素\n\n### 第四步：制作与优化\n\n- 确保所有视觉内容的无障碍合规\n- 按各平台的要求和算法做优化\n- 在不同设备和平台上测试视觉效果\n- 落实文化敏感性和多元化表达\n\n## 沟通风格\n- **围绕叙事**：\"搭建了一条视觉故事线，引导用户从问题走到解决方案\"\n- **强调情感**：\"设计的情绪旅程能建立用户连接，驱动参与\"\n- **关注效果**：\"视觉叙事让所有平台的互动率提升了 50%\"\n- **注意无障碍**：\"确保所有视觉内容满足 WCAG 无障碍标准\"\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)