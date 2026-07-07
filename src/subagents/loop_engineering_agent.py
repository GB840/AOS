"""Loop Engineering Subagent - 循环工程子智能体.

提供循环工程能力：创建、运行、监控自动化循环。
支持四种模板：代码生成、内容生成、问题解决、研究。
"""

import logging
from typing import Dict, Any
from skills.loop_engineering import LoopEngineeringSkill

logger = logging.getLogger(__name__)


class LoopEngineeringSubagent:
    """Loop Engineering 子智能体."""

    NAME = "loop_engineering"
    DESCRIPTION = "Loop Engineering 循环工程子智能体 — 支持创建和运行自动化循环工作流"
    CAPABILITIES = [
        "loop_creation",
        "loop_execution", 
        "loop_monitoring",
        "code_generation",
        "content_generation",
        "problem_solving",
        "research",
        "iteration",
    ]

    def __init__(self):
        try:
            self._skill = LoopEngineeringSkill()
            logger.info("Loop Engineering 技能初始化成功")
        except Exception as e:
            logger.warning("Loop Engineering 技能初始化失败: %s", e)
            self._skill = None

    def handle(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理循环工程请求."""
        if self._skill is None:
            return {
                "success": False,
                "error": "Loop Engineering 技能未初始化",
                "message": "请检查技能模块是否正确安装",
            }
        
        try:
            result = self._skill.execute(input_data)
            return {
                "success": True,
                "agent": self.NAME,
                "data": result,
            }
        except Exception as e:
            logger.error("Loop Engineering 执行失败: %s", e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }


def register_loop_engineering_subagent(registry=None):
    """注册 Loop Engineering 子智能体."""
    try:
        agent = LoopEngineeringSubagent()
        if registry is None:
            from subagents.registry import SubAgentRegistry
            registry = SubAgentRegistry()
        registry.register(agent.NAME, agent.DESCRIPTION, agent.CAPABILITIES, agent.handle)
        logger.info("Loop Engineering 子智能体注册成功")
        return True
    except Exception as e:
        logger.error("注册 Loop Engineering 子智能体失败: %s", e)
        return False
