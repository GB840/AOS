"""
AOS v5.0 — 数据库基础定义 (单一真相层)

所有 ORM 表模型共享:
  - TimestampMixin: created_at / updated_at
    关键: 必须用 sa_column_kwargs 让每张表生成「独立」的 Column 对象。
    若用 sa_column=sa.Column(...) 这种共享实例，多表继承会触发
    "Column object already assigned to Table" 错误。
  - 统一的列命名约定，兼容既有的 persistence_bridge / memory 裸 SQL 查询。

注意: `metadata` 是 SQLAlchemy 保留属性名，任何想映射 DB 列 "metadata" 的字段都
必须用 sa_column=sa.Column("metadata", ...) 指定物理列名，Python 属性另取别名。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

# 物理列名为 "metadata" 的字段统一用此工厂: 每次调用返回新的 Column 实例，
# 避免被多张表共享同一个 Column 对象 (会触发 "already assigned" 错误)。
META_COLUMN = lambda: sa.Column("metadata", sa.Text, server_default="{}")


class TimestampMixin(SQLModel):
    """为表模型注入 created_at / updated_at。

    每张子类表都会据此生成自己独立的 Column 实例，因此可安全被 38 张表复用。
    - default_factory: Python 级默认 (ORM 插入时填充)
    - server_default : SQLite 级默认 (裸 SQL 插入省略该列时不触发 NOT NULL)
    """

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={
            "server_default": sa.text("CURRENT_TIMESTAMP"),
            "nullable": False,
        },
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={
            "server_default": sa.text("CURRENT_TIMESTAMP"),
            "onupdate": datetime.utcnow,
            "nullable": False,
        },
    )
