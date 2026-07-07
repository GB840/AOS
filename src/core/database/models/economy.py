"""
AOS v5.0 — 经济层 (5 表)

成本-精度优化与 token/奖励/预算核算:
  - token_ledger           token 消耗流水
  - cost_accounting        单任务成本核算
  - reward_events          奖励发放事件
  - budget_pools           预算池
  - economic_transactions  通用经济交易账本
"""

from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from core.database.base import META_COLUMN, TimestampMixin


class TokenLedger(TimestampMixin, table=True):
    """token 消耗流水。"""
    __tablename__ = "token_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    task_id: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, sa.ForeignKey("tasks.id")))
    model: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, index=True))
    prompt_tokens: int = Field(default=0, sa_column=sa.Column(sa.Integer, server_default="0"))
    completion_tokens: int = Field(default=0, sa_column=sa.Column(sa.Integer, server_default="0"))
    cost_usd: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))


class CostAccounting(TimestampMixin, table=True):
    """单任务成本核算。"""
    __tablename__ = "cost_accounting"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("tasks.id"), index=True))
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    total_cost_usd: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    currency: str = Field(default="USD", sa_column=sa.Column(sa.Text, server_default="USD"))
    meta_json: str = Field(default="{}", sa_column=META_COLUMN())


class RewardEvent(TimestampMixin, table=True):
    """奖励发放事件。"""
    __tablename__ = "reward_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    task_id: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, sa.ForeignKey("tasks.id")))
    amount: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    reason: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    kind: str = Field(default="quality", sa_column=sa.Column(sa.Text, server_default="quality"))


class BudgetPool(TimestampMixin, table=True):
    """预算池。"""
    __tablename__ = "budget_pools"

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_agent_id: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id")))
    name: str = Field(sa_column=sa.Column(sa.Text, index=True))
    total_budget_usd: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    used_usd: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    period: str = Field(default="monthly", sa_column=sa.Column(sa.Text, server_default="monthly"))


class EconomicTransaction(TimestampMixin, table=True):
    """通用经济交易账本。"""
    __tablename__ = "economic_transactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True))
    budget_pool_id: Optional[int] = Field(default=None, sa_column=sa.Column(sa.Integer, sa.ForeignKey("budget_pools.id", ondelete="SET NULL")))
    tx_type: str = Field(sa_column=sa.Column(sa.Text, index=True))  # debit|credit|transfer
    amount_usd: float = Field(default=0.0, sa_column=sa.Column(sa.Float, server_default="0.0"))
    memo: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
