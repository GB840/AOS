"""
AOS v5.0 — 基础设施层 (9 表)

对应既有裸 SQL 模块的活跃表，列名严格对齐:
  - threads / messages / checkpoints / audit_log  -> deerflow.persistence_bridge
  - conversations / knowledge / tasks             -> memory.MemoryManager
  - users / agents                                -> 新增基线表

`metadata` 列名通过 sa_column 显式指定，避免与 SQLModel.metadata 冲突。
"""

from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from core.database.base import META_COLUMN, TimestampMixin


class User(TimestampMixin, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    display_name: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    role: str = Field(default="operator", sa_column=sa.Column(sa.Text, server_default="operator"))
    is_active: bool = Field(default=True, sa_column=sa.Column(sa.Boolean, server_default=sa.true()))


class Agent(TimestampMixin, table=True):
    __tablename__ = "agents"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(sa_column=sa.Column(sa.Text, unique=True, index=True))
    name: str = Field(sa_column=sa.Column(sa.Text))
    kind: str = Field(default="core", sa_column=sa.Column(sa.Text, server_default="core"))  # core | subagent | tool
    status: str = Field(default="inactive", sa_column=sa.Column(sa.Text, server_default="inactive"))
    endpoint: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    config_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class Thread(TimestampMixin, table=True):
    """对话线程 (来自 persistence_bridge)。"""
    __tablename__ = "threads"

    thread_id: str = Field(sa_column=sa.Column(sa.Text, primary_key=True))
    title: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    meta_json: str = Field(default="{}", sa_column=META_COLUMN())


class Message(TimestampMixin, table=True):
    """对话消息 (来自 persistence_bridge)。"""
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(
        sa_column=sa.Column(
            sa.Text, sa.ForeignKey("threads.thread_id", ondelete="CASCADE"), index=True
        )
    )
    role: str = Field(
        sa_column=sa.Column(
            sa.Text, sa.CheckConstraint("role IN ('user','assistant','system','tool')")
        )
    )
    content: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    tool_calls: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))


class Checkpoint(TimestampMixin, table=True):
    """LangGraph 状态快照 (来自 persistence_bridge)。"""
    __tablename__ = "checkpoints"

    thread_id: str = Field(sa_column=sa.Column(sa.Text, primary_key=True))
    checkpoint_ns: str = Field(default="", sa_column=sa.Column(sa.Text, primary_key=True))
    checkpoint_id: str = Field(sa_column=sa.Column(sa.Text, primary_key=True))
    parent_checkpoint_id: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    type: Optional[str] = Field(default=None, sa_column=sa.Column(sa.Text))
    checkpoint: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    meta_json: str = Field(default="{}", sa_column=META_COLUMN())


class Conversation(TimestampMixin, table=True):
    """记忆层对话记录 (来自 memory.MemoryManager)。"""
    __tablename__ = "conversations"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(sa_column=sa.Column(sa.Text, index=True))
    role: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    content: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    meta_json: str = Field(default="{}", sa_column=META_COLUMN())


class Knowledge(TimestampMixin, table=True):
    """知识库条目 (persistence_bridge + memory 共用，取超集列)。"""
    __tablename__ = "knowledge"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    content: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    source: str = Field(default="", sa_column=sa.Column(sa.Text, server_default=""))
    tags: str = Field(default="[]", sa_column=sa.Column(sa.Text, server_default="[]"))
    meta_json: str = Field(default="{}", sa_column=META_COLUMN())


class Task(TimestampMixin, table=True):
    """任务记录 (来自 memory.MemoryManager 口径: input/output)。"""
    __tablename__ = "tasks"

    id: str = Field(sa_column=sa.Column(sa.Text, primary_key=True))
    type: str = Field(sa_column=sa.Column(sa.Text, nullable=False))
    status: str = Field(default="pending", sa_column=sa.Column(sa.Text, server_default="pending", index=True))
    input: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    output: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    error: str = Field(default="", sa_column=sa.Column(sa.Text, server_default=""))


class AuditLog(TimestampMixin, table=True):
    """审计日志 (来自 persistence_bridge，物理列名 timestamp)。"""
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_type: str = Field(sa_column=sa.Column(sa.Text, nullable=False, index=True))
    user_id: str = Field(default="system", sa_column=sa.Column(sa.Text, server_default="system"))
    agent_id: str = Field(default="", sa_column=sa.Column(sa.Text, server_default=""))
    details: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    # 注意: 不要给 Python 侧 default (如 default="")，否则会遮蔽 server_default，
    # 导致 ORM 插入拿到空字符串而非真实时间戳 (与裸 SQL 路径行为不一致)。
    timestamp: Optional[str] = Field(
        default=None, sa_column=sa.Column(sa.Text, server_default=sa.text("CURRENT_TIMESTAMP"))
    )


class Notification(TimestampMixin, table=True):
    """站内通知 (蓝图 NOTIFY 的 in_app 通道落库)。"""
    __tablename__ = "notifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(
        default="", sa_column=sa.Column(sa.Text, sa.ForeignKey("agents.agent_id"), index=True)
    )
    channel: str = Field(default="in_app", sa_column=sa.Column(sa.Text, server_default="in_app"))
    payload_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))
    read: bool = Field(default=False, sa_column=sa.Column(sa.Boolean, server_default=sa.false()))


class EventStore(TimestampMixin, table=True):
    """追加式事件日志 (蓝图 EVENT_STORE)。每个聚合内 seq 单调递增。"""
    __tablename__ = "event_store"

    id: Optional[int] = Field(default=None, primary_key=True)
    aggregate_type: str = Field(sa_column=sa.Column(sa.Text, index=True))
    aggregate_id: str = Field(sa_column=sa.Column(sa.Text, index=True))
    seq: int = Field(default=0, sa_column=sa.Column(sa.Integer, server_default="0"))
    event_type: str = Field(sa_column=sa.Column(sa.Text, index=True))
    payload_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class Snapshot(TimestampMixin, table=True):
    """聚合快照 (事件溯源回放加速, 蓝图 EVENT_STORE 的快照部分)。"""
    __tablename__ = "snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    aggregate_type: str = Field(sa_column=sa.Column(sa.Text, index=True))
    aggregate_id: str = Field(sa_column=sa.Column(sa.Text, index=True))
    version: int = Field(default=0, sa_column=sa.Column(sa.Integer, server_default="0"))
    state_json: str = Field(default="{}", sa_column=sa.Column(sa.Text, server_default="{}"))


class ColdMemory(TimestampMixin, table=True):
    """冷记忆归档 (蓝图 COLD / PIPELINE)。原热数据压缩后存入, 释放主表。"""
    __tablename__ = "cold_memories"

    id: Optional[int] = Field(default=None, primary_key=True)
    original_id: str = Field(sa_column=sa.Column(sa.Text, index=True))
    kind: str = Field(default="conversation", sa_column=sa.Column(sa.Text, server_default="conversation"))
    data_blob: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    encoding: str = Field(default="zlib", sa_column=sa.Column(sa.Text, server_default="zlib"))
