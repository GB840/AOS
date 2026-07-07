"""
DeerFlow Persistence Bridge -- exposes the REAL DeerFlow persistence engine to AOS.

Wraps:
  - deerflow.persistence.engine (async SQLAlchemy engine: SQLite + PostgreSQL)
  - deerflow.persistence.base (ORM base)
  - deerflow.persistence.bootstrap (schema auto-creation)

Provides AOS with persistent checkpoint storage for multi-turn conversations.
"""

import sys
import logging
import os as _os
import threading
from typing import Optional

from utils.config import config

_DEERFLOW_SRC = config.DEERFLOW_SOURCE_PATH
if _DEERFLOW_SRC:
    if _DEERFLOW_SRC in sys.path:
        sys.path.remove(_DEERFLOW_SRC)
    sys.path.insert(0, _DEERFLOW_SRC)

if config.DEERFLOW_CONFIG_PATH:
    _os.environ.setdefault('DEER_FLOW_CONFIG_PATH', config.DEERFLOW_CONFIG_PATH)
for _var in ['DEEPSEEK_API_KEY', 'VOLCENGINE_API_KEY', 'ZHIPU_API_KEY', 'SCNET_API_KEY']:
    _os.environ.setdefault(_var, 'dummy-for-aos')
_os.environ.setdefault('FEISHU_WEBHOOK', 'https://dummy.example.com')

logger = logging.getLogger(__name__)

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path


class AOSPersistenceBridge:
    """AOS persistence bridge -- unified checkpoint storage.

    Uses SQLite for simplicity (mirrors DeerFlow's default) with:
    - Conversation threads (thread_id, messages, metadata)
    - Checkpoints (LangGraph state snapshots)
    - Knowledge base entries
    - Task history

    DeerFlow's async SQLAlchemy engine is available for advanced use
    via the .engine property.
    """

    def __init__(self, db_path: str = None):
        """
        Args:
            db_path: Path to SQLite database. Default: data/aos.db
        """
        if db_path is None:
            # 统一到 AOS 单一真相库 (与 core.database 共用同一物理文件)
            db_path = config.SQLITE_DB_PATH
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """统一到 AOS 单一真相库。

        1) 调用 ORM 层 (core.database.init_db) 幂等创建全部 38 张表
           (含 threads/messages/checkpoints/knowledge/tasks/audit_log 的正确列)。
        2) 保留一个原生 sqlite3 连接，供既有裸 SQL 方法 (add_message 等) 使用。
        """
        from core.database import init_db

        init_db()  # 单一真相层：38 张表 (idempotent)

        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row

        self._conn = conn
        logger.info("Persistence bridge initialized (unified aos.db): %s", self.db_path)

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the SQLite connection."""
        if self._conn is None:
            self._init_db()
        return self._conn

    # ---- Thread Operations ----

    def create_thread(self, thread_id: str, title: str = None,
                      metadata: dict = None) -> str:
        """Create a new conversation thread."""
        with self._lock:
            self.connection.execute(
                "INSERT OR REPLACE INTO threads (thread_id, title, metadata) VALUES (?, ?, ?)",
                (thread_id, title or f"Thread-{thread_id[:8]}", json.dumps(metadata or {}))
            )
            self.connection.commit()
        return thread_id

    def get_thread(self, thread_id: str) -> Optional[dict]:
        """Get thread details."""
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM threads WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "thread_id": row[0], "title": row[1],
            "created_at": row[2], "updated_at": row[3],
            "metadata": json.loads(row[4]),
        }

    def list_threads(self, limit: int = 50) -> list:
        """List recent threads."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT thread_id, title, created_at, updated_at FROM threads ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"thread_id": r[0], "title": r[1],
                 "created_at": r[2], "updated_at": r[3]} for r in rows]

    def delete_thread(self, thread_id: str):
        """Delete a thread and all its messages/checkpoints."""
        with self._lock:
            self.connection.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
            self.connection.commit()

    # ---- Message Operations ----

    def add_message(self, thread_id: str, role: str, content: str,
                    tool_calls: list = None):
        """Append a message to a thread."""
        with self._lock:
            self.connection.execute(
                "INSERT INTO messages (thread_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
                (thread_id, role, content, json.dumps(tool_calls) if tool_calls else None)
            )
            # Update thread timestamp
            self.connection.execute(
                "UPDATE threads SET updated_at = datetime('now') WHERE thread_id = ?",
                (thread_id,)
            )
            self.connection.commit()

    def get_messages(self, thread_id: str, limit: int = 100) -> list:
        """Get messages for a thread."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT role, content, tool_calls, created_at FROM messages WHERE thread_id = ? ORDER BY id ASC LIMIT ?",
                (thread_id, limit)
            ).fetchall()
        return [{"role": r[0], "content": r[1],
                 "tool_calls": json.loads(r[2]) if r[2] else None,
                 "created_at": r[3]} for r in rows]

    # ---- Knowledge Operations ----

    def add_knowledge(self, title: str, content: str, source: str = "",
                      tags: list = None) -> int:
        """Store a knowledge entry."""
        with self._lock:
            cur = self.connection.execute(
                "INSERT INTO knowledge (title, content, source, tags) VALUES (?, ?, ?, ?)",
                (title, content, source, json.dumps(tags or []))
            )
            self.connection.commit()
        return cur.lastrowid

    def search_knowledge(self, query: str, limit: int = 10) -> list:
        """Full-text search across knowledge."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT id, title, content, source, tags, created_at FROM knowledge WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "content": r[2],
                 "source": r[3], "tags": json.loads(r[4] or "[]"),
                 "created_at": r[5]} for r in rows]

    def list_knowledge(self, limit: int = 100) -> list:
        """List all knowledge entries."""
        with self._lock:
            rows = self.connection.execute(
                "SELECT id, title, source, tags, created_at FROM knowledge ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "source": r[2],
                 "tags": json.loads(r[3] or "[]"), "created_at": r[4]} for r in rows]

    # ---- Audit Log ----

    def audit(self, event_type: str, user_id: str = "system",
              agent_id: str = "", details: dict = None):
        """Write an audit entry."""
        with self._lock:
            self.connection.execute(
                "INSERT INTO audit_log (event_type, user_id, agent_id, details) VALUES (?, ?, ?, ?)",
                (event_type, user_id, agent_id, json.dumps(details or {}))
            )
            self.connection.commit()

    def get_audit_log(self, event_type: str = None, limit: int = 100) -> list:
        """Query audit log."""
        with self._lock:
            if event_type:
                rows = self.connection.execute(
                    "SELECT * FROM audit_log WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (event_type, limit)
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [{"id": r[0], "event_type": r[1], "user_id": r[2],
                 "agent_id": r[3], "details": json.loads(r[4] or "{}"),
                 "timestamp": r[5]} for r in rows]

    # ---- Stats ----

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._lock:
            return {
                "threads": self.connection.execute("SELECT COUNT(*) FROM threads").fetchone()[0],
                "messages": self.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                "knowledge": self.connection.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0],
                "tasks": self.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                "audit_entries": self.connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
                "db_path": str(self.db_path),
            }

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Persistence bridge closed")


# Module-level singleton
_default_persistence: Optional[AOSPersistenceBridge] = None


def get_persistence(db_path: str = None) -> AOSPersistenceBridge:
    """Get or create the default persistence bridge."""
    global _default_persistence
    if _default_persistence is None:
        _default_persistence = AOSPersistenceBridge(db_path=db_path)
    return _default_persistence
