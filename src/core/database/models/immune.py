"""
AOS v5.0 — 免疫层 (4 表)

原生免疫 / GB-Z 185 合规 / 语义防火墙 / 沙箱策略:
  - compliance_records      合规检查记录 (GB/Z 185 等)
  - identity_vault           身份/凭证保险库
  - semantic_firewall_rules  语义防火墙规则
  - sandbox_policies         执行沙箱策略
"""


import sqlalchemy as sa
from sqlmodel import Field

from core.database.base import TimestampMixin


class ComplianceRecord(TimestampMixin, table=True):
    """合规检查记录 (GB/Z 185 等)。"""
    __tablename__ = "compliance_records"

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    standard: str = Field(sa_column=sa.Column(sa.Text, index=True))  # 例如 GB/Z 185
    check_name: str = Field(sa_column=sa.Column(sa.Text, index=True))
    passed: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))
    detail_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class IdentityVault(TimestampMixin, table=True):
    """身份/凭证保险库。"""
    __tablename__ = "identity_vault"

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), unique=True, index=True))
    aid: str | None = Field(default=None, sa_column=sa.Column(sa.Text))
    public_key: str | None = Field(default=None, sa_column=sa.Column(sa.Text))
    attestation_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class SemanticFirewallRule(TimestampMixin, table=True):
    """语义防火墙规则。"""
    __tablename__ = "semantic_firewall_rules"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    category: str = Field(default="injection", sa_column=sa.Column(sa.Text, server_default="injection"))
    pattern: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    action: str = Field(default="block", sa_column=sa.Column(sa.Text, server_default="block"))  # block|warn|log
    enabled: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))


class SandboxPolicy(TimestampMixin, table=True):
    """执行沙箱策略。"""
    __tablename__ = "sandbox_policies"

    id: int | None = Field(default=None, primary_key=True)
    agent_id: str | None = Field(default=None, sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    allowed_tools: str = Field(default="[]", sa_column=sa.Column(sa.Text, server_default="[]"))
    denied_paths: str = Field(default="[]", sa_column=sa.Column(sa.Text, server_default="[]"))
    max_execution_seconds: int = Field(default=300, sa_column=sa.Column(sa.Integer, server_default="300"))
    policy_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
