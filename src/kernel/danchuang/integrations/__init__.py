"""开源库集成模块。

将 LangGraph、CrewAI 等前沿开源框架真正接入单创OS，
替代此前的理念借鉴式自研实现。
"""
from .langgraph_engine import LangGraphWorkflowEngine
from .crewai_engine import CrewAIOrchestrator

__all__ = ["LangGraphWorkflowEngine", "CrewAIOrchestrator"]
