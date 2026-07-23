"""真正的 CrewAI 编排引擎集成。

使用 crewai.Agent / Task / Crew 实现 OPC 多岗位协作，
每个岗位是一个 Agent，每个 Playbook 步骤是一个 Task。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from crewai import Agent, Crew, Process, Task

from ..engine.playbook_library import PlaybookTemplate
from ..llm import LLMProvider, LangChainLLMAdapter, get_default_provider
from ..opc.roles import OPCRole

logger = logging.getLogger(__name__)


class CrewAIOrchestrator:
    """基于 CrewAI 的多智能体协作编排器。

    将 OPC 5 大岗位映射为 CrewAI Agent，
    将 Playbook 步骤映射为 CrewAI Task，
    通过 Crew 顺序/并行/层级流程执行。
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        process: str = "sequential",
        verbose: bool = True,
    ):
        self._llm = llm or get_default_provider()
        self._process = process
        self._verbose = verbose
        self._agent_cache: Dict[str, Agent] = {}

    def run_from_template(
        self,
        template: PlaybookTemplate,
        goal: str,
        tenant_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """从 PlaybookTemplate 创建并运行 Crew。

        Args:
            template: 工作流模板
            goal: 总体目标
            tenant_id: 租户 ID
            context: 额外上下文

        Returns:
            执行结果
        """
        agents: List[Agent] = []
        tasks: List[Task] = []

        for step in template.steps:
            agent = self._get_or_create_agent(step.opc_role, step.assigned_role)
            if agent not in agents:
                agents.append(agent)

            task = Task(
                description=(
                    f"总体目标：{goal}\n"
                    f"当前步骤：{step.name}\n"
                    f"步骤描述：{step.description}\n"
                    f"上下文：{context or {}}"
                ),
                expected_output=(
                    ", ".join(step.deliverables)
                    if step.deliverables
                    else "给出结构化、可执行的输出结果"
                ),
                agent=agent,
            )
            tasks.append(task)

        process_enum = self._map_process(self._process)

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=process_enum,
            verbose=self._verbose,
        )

        try:
            result = crew.kickoff()
            raw_output = str(result)
            success = True
        except Exception as e:
            logger.error("CrewAI 执行失败: %s", e, exc_info=True)
            raw_output = f"CrewAI 执行失败: {e}"
            success = False

        return {
            "success": success,
            "template_id": template.template_id,
            "goal": goal,
            "process": self._process,
            "agent_count": len(agents),
            "task_count": len(tasks),
            "completed_tasks": len(tasks) if success else 0,
            "failed_tasks": 0 if success else len(tasks),
            "raw_output": raw_output,
            "llm_provider": self._llm.name(),
        }

    def _get_or_create_agent(self, opc_role: Optional[OPCRole], assigned_role: str = None) -> Agent:
        """获取或创建 CrewAI Agent。"""
        role_key = f"{opc_role.value if opc_role else 'agent'}:{assigned_role or 'expert'}"

        if role_key in self._agent_cache:
            return self._agent_cache[role_key]

        role_name = opc_role.value if opc_role else "智能体"
        role_title = assigned_role or f"{role_name}专家"

        # 使用自定义 LLM（避免依赖 OPENAI_API_KEY）
        llm_adapter = LangChainLLMAdapter(
            llm_provider=self._llm,
            model=getattr(self._llm, "model", "danchuang-llm"),
        )

        agent = Agent(
            role=role_title,
            goal=f"作为单创OS的{role_name}岗位，高质量完成分配的{role_title}任务",
            backstory=(
                f"你是单创OS数字组织中的 {role_title}，"
                f"隶属于 {role_name} 部门。"
                "你擅长结构化思考、输出可落地的方案，并能与其他岗位协作。"
            ),
            allow_delegation=False,
            verbose=self._verbose,
            llm=llm_adapter,
        )

        self._agent_cache[role_key] = agent
        return agent

    @staticmethod
    def _map_process(process: str) -> Process:
        """映射流程类型。"""
        mapping = {
            "sequential": Process.sequential,
            "hierarchical": Process.hierarchical,
        }
        return mapping.get(process.lower(), Process.sequential)
