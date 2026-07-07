"""
AOS v5.0 — 生态层 (10 表)

覆盖技能市场、工具注册、MCP 连接器、成本-精度策略(AgentCARD)、子智能体、
知识图谱(cognee)、机构角色与能力声明。
"""

from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from core.database.base import META_COLUMN, TimestampMixin


class Skill(TimestampMixin, table=True):
    __tablename__ = "skills"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    version: str = Field(default="0.1.0", sa_column=sa.Column(sa.Text, server_default="0.1.0"))
    kind: str = Field(default="python", sa_column=sa.Column(sa.Text, server_default="python"))
    entry: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    enabled: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))


class SkillVersion(TimestampMixin, table=True):
    """技能演进版本历史。"""
    __tablename__ = "skill_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(sa_column=sa.Column(sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), index=True))
    version: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    changelog: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    artifact_path: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))


class ToolRegistry(TimestampMixin, table=True):
    """可调用工具注册表。"""
    __tablename__ = "tool_registry"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    kind: str = Field(default="function", sa_column=sa.Column(sa.Text, server_default="function"))
    entry: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    schema_def: str = Field(default="{}", sa_column=sa.Column("schema_json", sa.Text, server_default="{}"))
    enabled: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))


class McpConnector(TimestampMixin, table=True):
    """MCP 服务器连接器。"""
    __tablename__ = "mcp_connectors"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    transport: str = Field(default="stdio", sa_column=sa.Column(sa.Text, server_default="stdio"))
    endpoint: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    status: str = Field(default="disconnected", sa_column=sa.Column(sa.Text, server_default="disconnected"))
    config_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class AgentCard(TimestampMixin, table=True):
    """成本-精度优化策略 (AgentCARD: 初稿小模型 -> 定稿大模型)。"""
    __tablename__ = "agent_cards"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    strategy_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    model_draft: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    model_final: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))


class SubagentRegistry(TimestampMixin, table=True):
    """子智能体注册 (8+ 子智能体)。"""
    __tablename__ = "subagent_registry"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    display_name: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    capabilities: str = Field(default="[]", sa_column=sa.Column(sa.Text, server_default="[]"))


class KnowledgeGraphNode(TimestampMixin, table=True):
    """知识图谱节点 (cognee)。"""
    __tablename__ = "knowledge_graph_nodes"

    id: Optional[int] = Field(default=None, primary_key=True)
    label: str = Field(sa_column=sa.Column(sa.Text, index=True))
    type: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    properties_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class KnowledgeGraphEdge(TimestampMixin, table=True):
    """知识图谱边。"""
    __tablename__ = "knowledge_graph_edges"

    id: Optional[int] = Field(default=None, primary_key=True)
    from_node_id: int = Field(sa_column=sa.Column(sa.Integer, sa.ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), index=True))
    to_node_id: int = Field(sa_column=sa.Column(sa.Integer, sa.ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), index=True))
    relation: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    weight: float = Field(default=1.0, sa_column=sa.Column(sa.Float, server_default="1.0"))


class AgencyRole(TimestampMixin, table=True):
    """机构角色定义 (Agency Roles)。"""
    __tablename__ = "agency_roles"

    id: Optional[int] = Field(default=None, primary_key=True)
    role_name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    permissions_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class CapabilityRegistry(TimestampMixin, table=True):
    """能力声明。"""
    __tablename__ = "capability_registry"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    owner_agent_id: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id")))
