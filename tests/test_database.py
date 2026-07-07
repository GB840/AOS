"""
AOS v5.0 — 数据库单一真相层测试

验证:
  - 38 张 ORM 表全部注册并幂等建表
  - 基线 agent 种子 (hermes / deerflow / meta_orchestrator)
  - ORM 读写 (含 TimestampMixin 的 server_default 对裸 SQL 友好)
  - 既有裸 SQL 模块 (persistence_bridge / memory) 在统一库上可正常工作
"""

import os
import subprocess
import sys
import tempfile

import pytest
from sqlmodel import SQLModel, select

from core.database import init_db, models, session_scope
from core.database.models import (
    Agent,
    AuditLog,
    Conversation,
    EvolutionLog,
    Knowledge,
    Message,
    Skill,
    Task,
    Thread,
)


def test_table_count_is_38():
    init_db()
    assert models.TABLE_COUNT == 38
    # 仅核对 ORM 注册的物理表数 (不含 FTS 影子表)
    assert len(SQLModel.metadata.tables) == 38


def test_init_db_idempotent():
    init_db()
    init_db()  # 重复调用不应抛错
    init_db()
    assert True


def test_seed_core_agents():
    init_db()
    with session_scope() as s:
        agents = s.exec(select(Agent)).all()
        ids = {a.agent_id for a in agents}
    assert {"hermes", "deerflow", "meta_orchestrator"} <= ids


def test_orm_insert_and_query():
    init_db()
    with session_scope() as s:
        s.add(AuditLog(event_type="boot", agent_id="hermes"))
        s.commit()
        row = s.exec(
            select(AuditLog).where(AuditLog.event_type == "boot")
        ).first()
        assert row is not None
        assert row.agent_id == "hermes"


def test_raw_sql_compatible_timestamps():
    """裸 SQL 省略时间戳列时，server_default 不应触发 NOT NULL。"""
    init_db()
    import sqlite3

    from utils.config import config

    con = sqlite3.connect(config.SQLITE_DB_PATH)
    con.execute(
        "INSERT INTO threads (thread_id, title) VALUES ('t_raw', 'raw thread')"
    )
    con.execute(
        "INSERT INTO audit_log (event_type, agent_id) VALUES ('x', 'hermes')"
    )
    con.commit()
    n = con.execute(
        "SELECT count(*) FROM threads WHERE thread_id='t_raw'"
    ).fetchone()[0]
    assert n == 1
    con.close()


def test_persistence_bridge_on_unified_db():
    """persistence_bridge 在统一库上建表 + 基础读写。"""
    init_db()
    from deerflow.persistence_bridge import AOSPersistenceBridge

    pb = AOSPersistenceBridge()
    pb.create_thread("t_pb", "PB thread")
    pb.add_message("t_pb", "user", "hello")
    stats = pb.get_stats()
    pb.close()
    assert stats["threads"] >= 1
    assert stats["messages"] >= 1


def test_memory_on_unified_db():
    """memory 在统一库上基础读写 + FTS 虚拟表存在。"""
    init_db()
    import sqlite3

    from memory import MemoryManager
    from utils.config import config

    mem = MemoryManager()
    mem.add_conversation("s_mem", "user", "hello memory")
    mem.add_knowledge("doc_mem", "body content", "src", ["t"])
    mem.close()

    con = sqlite3.connect(config.SQLITE_DB_PATH)
    fts = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations_fts'"
    ).fetchall()
    assert len(fts) == 1
    con.close()


def test_meta_orchestrator_engine_logs():
    """meta_orchestrator 引擎路由并落库 evolution_log。"""
    init_db()
    from meta_orchestrator.engine import MetaOrchestratorEngine

    e = MetaOrchestratorEngine()
    r = e.route_intent("让系统自我进化并修改策略", user_id="hermes", project_id="p")
    assert r["workflow_id"].startswith("wf_")
    assert isinstance(r["priority"], int)

    with session_scope() as s:
        rows = s.exec(select(EvolutionLog)).all()
    assert len(rows) >= 1
    assert rows[0].layer == "L3.5"


def test_ast_duplicate_detector_detects():
    """AST 检测器应能在同作用域内发现重复方法定义。"""
    src = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 1\n"
        "    def bar(self):\n"
        "        return 2\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        rc = subprocess.run(
            [sys.executable, "scripts/check_ast_duplicates.py", path],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
        )
        assert rc.returncode == 1
        assert "bar" in rc.stdout
    finally:
        os.unlink(path)


def test_ast_duplicate_detector_clean_passes():
    """干净文件应通过 (退出码 0)。"""
    src = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 1\n"
        "    def baz(self):\n"
        "        return 2\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        rc = subprocess.run(
            [sys.executable, "scripts/check_ast_duplicates.py", path],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
        )
        assert rc.returncode == 0
    finally:
        os.unlink(path)
