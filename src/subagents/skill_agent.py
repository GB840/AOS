"""技能子智能体包装器 - 将任意技能自动转换为子智能体."""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SkillSubagent:
    """将技能包装为子智能体."""

    def __init__(self, skill_name: str, skill_instance, skill_registry):
        self.skill_name = skill_name
        self.skill = skill_instance
        self.skill_registry = skill_registry
        self.DESCRIPTION = skill_instance.DESCRIPTION
        self.CAPABILITIES = skill_instance.CAPABILITIES

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理子智能体调用，转发给技能执行."""
        try:
            result = self.skill.execute(input_data)
            if result.get("success"):
                return {"success": True, "result": result.get("result", {})}
            else:
                return {"success": False, "error": result.get("error", "技能执行失败")}
        except Exception as e:
            logger.error(f"技能子智能体 {self.skill_name} 执行失败: {e}")
            return {"success": False, "error": str(e)}


def create_skill_subagent(skill_name: str, skill_registry) -> SkillSubagent:
    """从技能注册表创建技能子智能体."""
    skill = skill_registry.get(skill_name)
    if skill:
        return SkillSubagent(skill_name, skill, skill_registry)
    return None


def register_skill_as_subagent(skill_name: str, skill_registry, subagent_registry):
    """将技能注册为子智能体."""
    skill = skill_registry.get(skill_name)
    if skill:
        agent = SkillSubagent(skill_name, skill, skill_registry)
        subagent_registry.register(
            name=skill_name,
            description=skill.DESCRIPTION,
            capabilities=skill.CAPABILITIES,
            handler=agent.handle,
        )
        logger.info(f"技能子智能体已注册: {skill_name}")
        return True
    logger.warning(f"技能 {skill_name} 不存在，无法注册为子智能体")
    return False