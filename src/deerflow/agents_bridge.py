"""
DeerFlow Agents Bridge -- exposes the REAL DeerFlow agent factory to AOS.

Wraps:
  - deerflow.agents.factory.create_deerflow_agent() -- the core LangGraph agent constructor
  - deerflow.agents.features.RuntimeFeatures -- declarative feature flags
  - deerflow.agents.thread_state.ThreadState -- LangGraph state schema

This gives AOS direct access to DeerFlow's 14-middleware agent chain:
  Sandbox -> DanglingToolCall -> Guardrail -> ToolErrorHandling ->
  Summarization -> Todo -> AutoTitle -> Memory -> Vision ->
  SubagentLimit -> LoopDetection -> TokenBudget -> Clarification

All imports resolve to REAL DeerFlow 2.0 source.
"""

import sys
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from deerflow.path_detect import setup_deerflow_env

_DEERFLOW_SRC = setup_deerflow_env()

if _DEERFLOW_SRC:
    try:
        # REAL DeerFlow agent factory
        from deerflow.agents.factory import create_deerflow_agent
        from deerflow.agents.features import RuntimeFeatures, Next, Prev
        from deerflow.agents.thread_state import ThreadState
        logger.info("✅ DeerFlow Agents Bridge 加载成功")
    except ImportError as e:
        logger.warning(f"❌ DeerFlow Agents Bridge 导入失败: {e}")
        _DEERFLOW_SRC = None
else:
    logger.warning("⚠️ DeerFlow 源码路径未检测到")


class AOSAgentConfig:
    """Declarative configuration for building a DeerFlow agent in AOS.

    Maps AOS config values to DeerFlow's RuntimeFeatures.
    """

    def __init__(self, **kwargs):
        # Core
        self.model_name: str = kwargs.get("model_name", "glm-4-flash")
        self.system_prompt: Optional[str] = kwargs.get("system_prompt")
        self.plan_mode: bool = kwargs.get("plan_mode", False)
        self.agent_name: str = kwargs.get("agent_name", "aos-agent")

        # Feature flags (mirrors RuntimeFeatures)
        self.sandbox: bool = kwargs.get("sandbox", True)
        self.memory: bool = kwargs.get("memory", True)
        self.subagent: bool = kwargs.get("subagent", True)
        self.vision: bool = kwargs.get("vision", False)
        self.auto_title: bool = kwargs.get("auto_title", True)
        self.guardrail: bool = kwargs.get("guardrail", False)
        self.loop_detection: bool = kwargs.get("loop_detection", True)
        self.token_budget: bool = kwargs.get("token_budget", False)
        self.summarization: bool = kwargs.get("summarization", False)

        # Extra middleware to inject
        self.extra_middleware: List[Any] = kwargs.get("extra_middleware", [])

    def to_runtime_features(self) -> RuntimeFeatures:
        """Convert AOS config to DeerFlow RuntimeFeatures."""
        return RuntimeFeatures(
            sandbox=self.sandbox,
            memory=self.memory,
            subagent=self.subagent,
            vision=self.vision,
            auto_title=self.auto_title,
            guardrail=self.guardrail,
            loop_detection=self.loop_detection,
            token_budget=self.token_budget,
            summarization=self.summarization,
        )

    def get_feature_summary(self) -> Dict[str, bool]:
        """Return a dict of all feature flags."""
        return {
            "sandbox": self.sandbox,
            "memory": self.memory,
            "subagent": self.subagent,
            "vision": self.vision,
            "auto_title": self.auto_title,
            "guardrail": self.guardrail,
            "loop_detection": self.loop_detection,
            "token_budget": self.token_budget,
            "summarization": self.summarization,
            "plan_mode": self.plan_mode,
        }


class AOSAgentFactory:
    """AOS agent factory -- builds configured DeerFlow LangGraph agents.

    Wraps create_deerflow_agent() with AOS-specific configuration,
    model resolution, and tool registration.
    """

    def __init__(self, config: AOSAgentConfig = None):
        self.config = config or AOSAgentConfig()
        self._graph = None
        self._model = None
        self._tools: List[Any] = []
        self._checkpointer = None

    def set_model(self, model):
        """Set the LangChain chat model."""
        self._model = model
        self._graph = None  # Invalidate

    def add_tools(self, *tools):
        """Register tools with the agent."""
        self._tools.extend(tools)
        self._graph = None  # Invalidate

    def set_checkpointer(self, checkpointer):
        """Set the LangGraph checkpointer for persistence."""
        self._checkpointer = checkpointer
        self._graph = None  # Invalidate

    def build(self) -> Any:
        """Build the DeerFlow LangGraph agent.

        Returns:
            A CompiledStateGraph ready for invocation/streaming.
        """
        if self._graph is not None:
            return self._graph

        if self._model is None:
            raise ValueError("Model not set. Call set_model() before build().")

        features = self.config.to_runtime_features()

        logger.info(
            "Building DeerFlow agent: name=%s model=%s features=%s",
            self.config.agent_name,
            self.config.model_name,
            self.config.get_feature_summary(),
        )

        self._graph = create_deerflow_agent(
            model=self._model,
            tools=self._tools if self._tools else None,
            system_prompt=self.config.system_prompt,
            features=features,
            extra_middleware=self.config.extra_middleware or None,
            plan_mode=self.config.plan_mode,
            state_schema=ThreadState,
            checkpointer=self._checkpointer,
            name=self.config.agent_name,
        )

        logger.info("DeerFlow agent built: name=%s", self.config.agent_name)
        return self._graph

    @property
    def graph(self):
        """Get or build the agent graph."""
        if self._graph is None:
            return self.build()
        return self._graph

    def reset(self):
        """Invalidate the built graph so next access rebuilds."""
        self._graph = None


# ---- Convenience ----

def create_aos_agent(
    model,
    tools: List[Any] = None,
    *,
    system_prompt: str = None,
    plan_mode: bool = False,
    agent_name: str = "aos-agent",
    sandbox: bool = True,
    memory: bool = True,
    subagent: bool = True,
    **kwargs,
):
    """One-shot: create a configured AOS agent.

    Args:
        model: LangChain chat model instance.
        tools: List of LangChain tools.
        system_prompt: System prompt for the agent.
        plan_mode: Enable todo-list tracking.
        agent_name: Name for logging/memory middleware.
        sandbox/memory/subagent: Feature flags.
        **kwargs: Passed to AOSAgentConfig.

    Returns:
        CompiledStateGraph ready for .invoke() or .astream().
    """
    config = AOSAgentConfig(
        model_name=getattr(model, "model_name", "unknown"),
        system_prompt=system_prompt,
        plan_mode=plan_mode,
        agent_name=agent_name,
        sandbox=sandbox,
        memory=memory,
        subagent=subagent,
        **kwargs,
    )

    factory = AOSAgentFactory(config)
    factory.set_model(model)
    if tools:
        factory.add_tools(*tools)
    return factory.build()
