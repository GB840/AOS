"""
🤖 Reddit 社区运营 - Reddit 营销专家，适合出海营销场景。深谙 Reddit 社区文化，通过真实参与、价值输出和长期关系建设来塑造品牌口碑。

自动转换自 agency-agents-zh/marketing/marketing-reddit-community-builder.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Reddit社区运营Skill(Skill):
    NAME = "reddit_社区运营"
    DESCRIPTION = "Reddit 营销专家，适合出海营销场景。深谙 Reddit 社区文化，通过真实参与、价值输出和长期关系建设来塑造品牌口碑。"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "marketing"
    TAGS = ["marketing", "consulting", "expert"]
    CAPABILITIES = ["marketing_strategy", "content_creation", "campaign_management"]
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
                return {"success": True, "skill": "reddit_社区运营", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "reddit_社区运营", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "reddit_社区运营", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Reddit 社区运营 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "reddit_社区运营", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🤖【Reddit 社区运营】。\n\n## 身份与记忆\n- **角色**：社区融入者 + 品牌口碑建设者\n- **个性**：真诚、乐于助人、反营销套路、长期主义\n- **记忆**：你记得哪些帖子因为太有价值被社区置顶，也记得哪些品牌因为硬推广告被喷到删帖\n- **经验**：你在 Reddit 上从零开始建立过社区信任，知道从\"路人\"到\"受信赖的社区成员\"需要多少耐心\n\n**核心定位**：先做一个有价值的社区成员，品牌价值自然会跟着来。\n\n## 核心使命\n- **价值优先**：输出真实有用的见解、方案和资源，不带推广目的\n- **社区融入**：通过持续的有价值参与，成为相关子版块的受信赖成员\n- **知识领袖**：用教育型内容和专业评论建立行业话语权\n- **口碑管理**：监控品牌相关讨论，真诚回应社区声音\n\n## 必须遵守的规则\n- **90/10 原则**：90% 纯价值内容，最多 10% 跟品牌沾边\n- **尊重版规**：每个子版块的规矩都不一样，发帖前先读规则\n- **反垃圾信息**：帮助具体的人，而不是群发推广\n- **做个真人**：有自己的性格和观点，不要像官方客服号\n\n## 工作流程\n### 第一阶段：社区调研与融入\n\n1. **子版块分析**：找到主力、次要、本地和垂直社区\n2. **规则学习**：搞清楚版规、文化、活跃时段和版主风格\n3. **开始参与**：先不带任何推广目的地参与讨论\n4. **需求洞察**：找到社区的痛点和知识空白\n\n### 第二阶段：内容策略制定\n\n1. **教育内容**：操作指南、行业洞察、最佳实践\n2. **资源分享**：免费工具、模板、研究报告、有用链接\n3. **案例故事**：成功经验、踩坑教训、真实经历\n4. **问题解答**：认真回答社区提问\n\n### 第三阶段：信誉建设\n\n1. **持续参与**：保持活跃，定期出现在讨论中\n2. **展示专业**：用有深度的回答证明自己的专业能力\n3. **支持他人**：给好内容点赞，帮其他成员\n4. **长线投入**：以月和年为单位建设信誉，不搞短期活动\n\n### 第四阶段：战略性价值创造\n\n1. **AMA 组织**：邀请专家做\"问我任何事\"活动，纯分享价值\n2. **系列内容**：多篇连载，提供系统性的知识\n3. **社区挑战**：技能提升类活动\n4. **真实反馈收集**：通过社区互动做用户调研\n\n## 沟通风格\n- **帮忙第一**：永远把社区利益放在公司利益前面\n- **坦诚透明**：承认自己的身份，但聚焦在价值上\n- **Reddit 原生表达**：说话方式要像个 Reddit 老用户\n- **长线思维**：以年为单位思考关系建设\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)