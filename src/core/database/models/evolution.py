"""
AOS v5.0 — 进化层 (10 表)

三层进化 / 技能自演进相关:
  - task_fingerprints    记忆沉淀与复用
  - orchestration_specs  LEMON 自动生成的编排规格
  - workflow_definitions SwarmFlow 可控工作流
  - evolution_log        演进事件版本链
  - learning_experiences 经验回放缓冲
  - model_routing_history llm_router 决策记录
  - performance_metrics   组件性能
  - prompt_templates      优化提示模板
  - negotiation_sessions  L3 轻量协商
  - self_modification_proposals 元调度提出的自修改提案
"""

from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from core.database.base import META_COLUMN, TimestampMixin


class TaskFingerprint(TimestampMixin, table=True):
    """任务指纹: 记忆沉淀与模板匹配。"""
    __tablename__ = "task_fingerprints"

    id: Optional[int] = Field(default=None, primary_key=True)
    fingerprint_hash: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    intent_summary: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    template_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    hit_count: int = Field(default=0, sa_column=sa.Column(sa.Integer, server_default="0"))


class OrchestrationSpec(TimestampMixin, table=True):
    """LEMON 自动生成的编排规格。"""
    __tablename__ = "orchestration_specs"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    spec_name: str = Field(sa_column=sa.Column(sa.Text, index=True))
    spec_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    auto_generated: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))


class WorkflowDefinition(TimestampMixin, table=True):
    """SwarmFlow 可控工作流定义。"""
    __tablename__ = "workflow_definitions"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: Optional[int] = Field(default=None, sa_column=sa.Column(sa.Integer, sa.ForeignKey("skills.id", ondelete="SET NULL")))
    name: str = Field(sa_column=sa.Column(sa.Text, index=True))
    dag_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    enabled: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))


class EvolutionLog(TimestampMixin, table=True):
    """演进事件版本链。"""
    __tablename__ = "evolution_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    layer: str = Field(default="L1", sa_column=sa.Column(sa.Text, server_default="L1"))  # L1|L2|L3|L3.5
    event_type: str = Field(sa_column=sa.Column(sa.Text, index=True))
    from_version: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    to_version: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    payload_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class LearningExperience(TimestampMixin, table=True):
    """经验回放缓冲。"""
    __tablename__ = "learning_experiences"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_fingerprint_id: Optional[int] = Field(default=None, sa_column=sa.Column(sa.Integer, sa.ForeignKey("task_fingerprints.id", ondelete="CASCADE"), index=True))
    outcome: str = Field(default="success", sa_column=sa.Column(sa.Text, server_default="success"))
    reward: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    experience_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class ModelRoutingHistory(TimestampMixin, table=True):
    """llm_router 决策记录。"""
    __tablename__ = "model_routing_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    task_id: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, sa.ForeignKey("tasks.id")))
    requested_capability: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    selected_model: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, index=True))
    fallback_used: bool = Field(default=False, sa_column=sa.Column(sa.Boolean, server_default=sa.false()))
    latency_ms: Optional[int] = Field(default=None, sa_column=sa.Column(sa.Integer))


class PerformanceMetric(TimestampMixin, table=True):
    """组件性能度量。"""
    __tablename__ = "performance_metrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    component: str = Field(sa_column=sa.Column(sa.Text, index=True))
    metric_name: str = Field(sa_column=sa.Column(sa.Text, index=True))
    metric_value: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    meta_json: str = Field(default="{}", sa_column=META_COLUMN())


class PromptTemplate(TimestampMixin, table=True):
    """优化提示模板。"""
    __tablename__ = "prompt_templates"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    template: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    version: str = Field(default="1", sa_column=sa.Column(sa.Text, server_default="1"))


class NegotiationSession(TimestampMixin, table=True):
    """L3 轻量协商会话。"""
    __tablename__ = "negotiation_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    initiator_agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    role_assignment_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    status: str = Field(default="open", sa_column=sa.Column(sa.Text, server_default="open"))


class SelfModificationProposal(TimestampMixin, table=True):
    """元调度提出的自修改提案 (L3.5)。"""
    __tablename__ = "self_modification_proposals"

    id: Optional[int] = Field(default=None, primary_key=True)
    proposer_agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    target: str = Field(sa_column=sa.Column(sa.Text, index=True))  # 例如 skill:xxx / workflow:yyy
    rationale: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    diff_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    status: str = Field(default="proposed", sa_column=sa.Column(sa.Text, server_default="proposed"))  # proposed|approved|rejected|applied
