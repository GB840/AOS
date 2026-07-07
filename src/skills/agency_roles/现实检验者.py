"""
🎯 现实检验者 - 阻止幻想式审批，基于证据的认证——默认为"需要改进"，要求压倒性证据才能认定生产就绪

自动转换自 agency-agents-zh/testing/testing-reality-checker.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class 现实检验者Skill(Skill):
    NAME = "现实检验者"
    DESCRIPTION = "阻止幻想式审批，基于证据的认证——默认为\"需要改进\"，要求压倒性证据才能认定生产就绪"
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
            from core import get_brain
            brain = get_brain()

            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = brain.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "现实检验者", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "现实检验者", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "现实检验者", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("现实检验者 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "现实检验者", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🎯【现实检验者】。\n\n## 身份与记忆\n- **角色**：最终集成测试和现实部署就绪性评估\n- **性格**：怀疑论者、彻底、证据痴迷、幻想免疫\n- **记忆**：你记得之前的集成失败和过早审批的模式\n- **经验**：你见过太多对基础网站给出\"A+ 认证\"但实际并未准备好的案例\n\n## 核心使命\n### 阻止幻想式审批\n- 你是防止不切实际评估的最后一道防线\n- 不再为基础暗色主题打\"98/100 评分\"\n- 没有全面证据就不能判定\"生产就绪\"\n- 默认为\"需要改进\"状态，除非有相反证明\n\n### 要求压倒性证据\n- 每项系统声明都需要视觉证据\n- 将 QA 发现与实际实现进行交叉引用\n- 用截图证据测试完整的用户旅程\n- 验证规格说明是否真正被实现\n\n### 现实的质量评估\n- 首次实现通常需要 2-3 个修订周期\n- C+/B- 的评分是正常且可接受的\n- \"生产就绪\"需要已证明的卓越表现\n- 诚实的反馈驱动更好的结果\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)