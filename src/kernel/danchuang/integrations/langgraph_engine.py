"""真正的 LangGraph 工作流引擎集成。

使用 langgraph.StateGraph 将 PlaybookTemplate 编译为可执行图，
每个步骤作为一个节点，通过 LLM 执行并更新全局状态。
支持持久化检查点（MemorySaver）和时间旅行调试。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ..engine.playbook_library import PlaybookTemplate
from ..llm import LLMProvider, get_default_provider
from ..opc.roles import OPCRole

logger = logging.getLogger(__name__)


class WorkflowState(TypedDict, total=False):
    """LangGraph 工作流状态类型。"""

    workflow_id: str
    tenant_id: str
    goal: str
    current_step: str
    step_results: Dict[str, Any]
    context: Dict[str, Any]
    completed_steps: List[str]
    failed_steps: List[str]
    final_output: str


class LangGraphWorkflowEngine:
    """基于 LangGraph 的工作流执行引擎。

    将 PlaybookTemplate 编译为 StateGraph 并执行，
    每个步骤调用 LLM 生成真实执行结果。
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        checkpointer: Optional[Any] = None,
    ):
        self._llm = llm or get_default_provider()
        self._checkpointer = checkpointer or MemorySaver()
        self._compiled_graphs: Dict[str, Callable] = {}

    def compile(self, template: PlaybookTemplate, workflow_id: str = None) -> Callable:
        """将 PlaybookTemplate 编译为 LangGraph 可执行图。

        Args:
            template: 工作流模板
            workflow_id: 工作流实例 ID

        Returns:
            编译后的 StateGraph 调用函数
        """
        graph = StateGraph(WorkflowState)

        # 添加每个步骤节点
        for step in template.steps:
            node_name = self._safe_node_name(step.step_id)
            graph.add_node(node_name, self._make_step_node(step))

        # 起始节点：进入第一个步骤
        first_node = self._safe_node_name(template.steps[0].step_id)
        graph.add_edge(START, first_node)

        # 步骤间路由
        for i, step in enumerate(template.steps):
            current_node = self._safe_node_name(step.step_id)

            if i + 1 < len(template.steps):
                next_node = self._safe_node_name(template.steps[i + 1].step_id)
                graph.add_edge(current_node, next_node)
            else:
                graph.add_edge(current_node, END)

        return graph.compile(checkpointer=self._checkpointer)

    def run(
        self,
        template: PlaybookTemplate,
        goal: str,
        tenant_id: str,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行工作流。

        Args:
            template: 工作流模板
            goal: 工作目标
            tenant_id: 租户 ID
            workflow_id: 工作流实例 ID
            context: 初始上下文

        Returns:
            执行结果
        """
        app = self.compile(template, workflow_id)

        initial_state: WorkflowState = {
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
            "goal": goal,
            "current_step": "",
            "step_results": {},
            "context": context or {"goal": goal},
            "completed_steps": [],
            "failed_steps": [],
            "final_output": "",
        }

        config = {"configurable": {"thread_id": workflow_id}}
        final_state = app.invoke(initial_state, config=config)

        return {
            "workflow_id": workflow_id,
            "template_id": template.template_id,
            "goal": goal,
            "completed_steps": final_state.get("completed_steps", []),
            "failed_steps": final_state.get("failed_steps", []),
            "step_results": final_state.get("step_results", {}),
            "final_output": final_state.get("final_output", ""),
            "llm_provider": self._llm.name(),
        }

    def _make_step_node(self, step) -> Callable:
        """创建步骤执行节点。"""

        def step_node(state: WorkflowState) -> WorkflowState:
            logger.info("执行步骤: %s (%s)", step.name, step.step_id)

            goal = state.get("goal", "")
            context = state.get("context", {})

            # 构建 system prompt（基于 OPC 角色 + 步骤职责）
            role_name = step.opc_role.value if step.opc_role else "智能体"
            system_prompt = (
                f"你是单创OS的数字员工，担任【{role_name}】岗位。\n"
                f"你的专业角色是：{step.assigned_role or '领域专家'}\n"
                f"任务名称：{step.name}\n"
                f"任务描述：{step.description}\n"
                "请给出结构化、可执行、包含具体数据和结论的输出。"
            )

            user_prompt = (
                f"总体目标：{goal}\n"
                f"当前上下文：{context}\n"
                f"请完成以下交付物：{', '.join(step.deliverables) if step.deliverables else '给出执行结果'}"
            )

            try:
                response = self._llm.invoke(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                )
                result_text = response.content
                failed = False
            except Exception as e:
                logger.error("步骤 %s LLM 调用失败: %s", step.step_id, e)
                result_text = f"执行失败: {e}"
                failed = True

            # 更新状态
            step_results = dict(state.get("step_results", {}))
            step_results[step.step_id] = {
                "name": step.name,
                "output": result_text,
                "role": role_name,
                "failed": failed,
            }

            completed = list(state.get("completed_steps", []))
            failed_steps = list(state.get("failed_steps", []))

            if failed:
                failed_steps.append(step.step_id)
            else:
                completed.append(step.step_id)

            return {
                **state,
                "current_step": step.step_id,
                "step_results": step_results,
                "completed_steps": completed,
                "failed_steps": failed_steps,
                "final_output": result_text,
            }

        return step_node

    @staticmethod
    def _safe_node_name(step_id: str) -> str:
        """生成 LangGraph 安全的节点名。"""
        return step_id.replace("-", "_").replace(".", "_")
