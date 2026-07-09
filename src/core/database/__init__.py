"""
AOS v5.0 — 数据库单一真相层 (Database)

统一入口:
  from core.database import init_db, get_engine, session_scope, models

- init_db():      幂等创建全部 38 张表
- get_engine():   进程级单例 SQLAlchemy 引擎
- session_scope(): 会话上下文管理器
- models:         全部 ORM 表模型 (SQLModel.metadata 已注册)
"""

from core.database import models
from core.database.base import META_COLUMN, TimestampMixin
from core.database.engine import get_engine, get_session, init_db, session_scope

__all__ = [
    "META_COLUMN",
    "TimestampMixin",
    "get_engine",
    "get_session",
    "init_db",
    "models",
    "session_scope",
]
