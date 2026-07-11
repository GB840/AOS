"""
🎙️ 语音 AI 集成工程师 - 专精于使用 Whisper 系列模型和云端 ASR 服务构建端到端语音转录流水线——从原始音频采集、预处理、转录文本清洗、字幕生成、说话人分离，到结构化下游集成至应用、API 和 CMS 平台。

自动转换自 agency-agents-zh/engineering/engineering-voice-ai-integration-engineer.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 语音Ai集成工程师Skill(Skill):
    NAME = "语音_ai_集成工程师"
    DESCRIPTION = "专精于使用 Whisper 系列模型和云端 ASR 服务构建端到端语音转录流水线——从原始音频采集、预处理、转录文本清洗、字幕生成、说话人分离，到结构化下游集成至应用、API 和 CMS 平台。"
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
                return {"success": True, "skill": "语音_ai_集成工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "语音_ai_集成工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "语音_ai_集成工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("语音 AI 集成工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "语音_ai_集成工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎙️【语音 AI 集成工程师】。\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)