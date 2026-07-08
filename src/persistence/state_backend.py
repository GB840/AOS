"""团队级状态后端可插拔 seam.

AOS 演进路线核心原则: 个人 -> 团队 -> 公司, **换后端实现、接口不变**.
状态层是第一个实战 seam:

  - 个人级:  SQLite (零运维, 单文件)
  - 团队级:  Postgres (高并发/多实例共享)  —— 仅改 config.STATE_BACKEND, 调用方零改动
  - 公司级:  可在 PostgresStateBackend 内接读写分离/分库, 仍不触碰调用方

所有状态读写都走 `StateBackend` 抽象契约; `get_state_backend()` 工厂按配置返回实现.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from utils.config import config

logger = logging.getLogger(__name__)


class StateBackend:
    """所有状态读写的统一契约. 换后端 = 换实现, 调用方代码不变."""

    def execute(self, sql: str, params: tuple = ()) -> Any:
        raise NotImplementedError

    def query(self, sql: str, params: tuple = (), fetch_all: bool = True):
        raise NotImplementedError

    def close(self) -> None:
        pass


class SQLiteStateBackend(StateBackend):
    """个人级默认实现: 单文件 SQLite, 零运维."""

    def __init__(self, path: str = config.SQLITE_DB_PATH):
        import sqlite3
        self._path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: tuple = ()):
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor

    def query(self, sql: str, params: tuple = (), fetch_all: bool = True):
        cursor = self.conn.execute(sql, params)
        return cursor.fetchall() if fetch_all else cursor.fetchone()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


class PostgresStateBackend(StateBackend):
    """团队/公司级实现: SQLAlchemy 连 Postgres, 同 StateBackend 契约.

    升级到团队级时只需把 config.STATE_BACKEND 置为 'postgres' 并填 POSTGRES_*，
    所有调用方(仍用 execute/query)完全不变.
    """

    def __init__(self) -> None:
        from sqlalchemy import create_engine, text
        url = (
            f"postgresql+psycopg2://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
            f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
        )
        self._engine = create_engine(url, pool_pre_ping=True, future=True)
        self._text = text

    def execute(self, sql: str, params: tuple = ()):
        with self._engine.begin() as conn:
            return conn.execute(self._text(sql), params)

    def query(self, sql: str, params: tuple = (), fetch_all: bool = True):
        with self._engine.connect() as conn:
            result = conn.execute(self._text(sql), params)
            return result.fetchall() if fetch_all else result.fetchone()

    def close(self) -> None:
        try:
            self._engine.dispose()
        except Exception:
            pass


_backend: Optional[StateBackend] = None


def get_state_backend() -> StateBackend:
    """工厂: 按 config.STATE_BACKEND 返回后端实现(单例)."""
    global _backend
    if _backend is not None:
        return _backend
    kind = (config.STATE_BACKEND or "sqlite").lower()
    if kind == "postgres":
        logger.info("状态后端选择: Postgres (团队/公司级)")
        _backend = PostgresStateBackend()
    else:
        logger.info("状态后端选择: SQLite (个人级)")
        _backend = SQLiteStateBackend()
    return _backend


def reset_state_backend() -> None:
    """测试/重配置用: 释放当前后端单例."""
    global _backend
    if _backend is not None:
        try:
            _backend.close()
        except Exception:
            pass
        _backend = None
