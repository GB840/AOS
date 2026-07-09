"""
AOS v5.0 — 数据库引擎与会话管理 (单一真相层)

职责:
  - 根据 config.SQLITE_DB_PATH 创建进程级单例 SQLAlchemy 引擎 (WAL/外键开启)
  - init_db(): 幂等创建全部 42 张表 (SQLModel.metadata.create_all)
  - session_scope(): 线程安全的会话上下文管理器

本模块刻意"懒加载"模型导入，避免与 SQLModel.metadata 的注册顺序产生循环依赖。
"""

import threading
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from utils.config import config

_engine: Engine | None = None
_lock = threading.Lock()
# expire_on_commit=False: 提交后对象属性保持已加载状态，避免"提交后访问 →
# DetachedInstanceError"这一整类易错问题。对于 AOS 短生命周期会话属安全默认值。
_SessionMaker = None


def _get_sessionmaker() -> sessionmaker:
    global _SessionMaker
    if _SessionMaker is None:
        with _lock:
            if _SessionMaker is None:
                _SessionMaker = sessionmaker(
                    bind=get_engine(),
                    class_=Session,
                    expire_on_commit=False,
                )
    return _SessionMaker


def get_engine() -> Engine:
    """返回进程级单例引擎 (按需创建)。"""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                db_path = config.SQLITE_DB_PATH
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                _engine = create_engine(
                    f"sqlite:///{db_path}",
                    connect_args={"check_same_thread": False},
                    echo=bool(getattr(config, "DEBUG", False)),
                    pool_pre_ping=True,
                )
                # 开启外键约束 (SQLite 默认关闭)
                from sqlalchemy import event

                @event.listens_for(_engine, "connect")
                def _fk_pragma(dbapi_con, con_record):
                    cur = dbapi_con.cursor()
                    cur.execute("PRAGMA foreign_keys=ON")
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.close()

    return _engine


def init_db(engine: Engine | None = None) -> None:
    """幂等创建全部 42 张表。可重复调用，已存在的表会被跳过。"""
    engine = engine or get_engine()
    # 触发所有模型模块的导入，确保 SQLModel.metadata 已注册全部表。
    from core.database import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_seed(engine)


def _ensure_seed(engine: Engine) -> None:
    """插入运行期必需的少量基线数据 (幂等)。"""
    from sqlmodel import Session, select

    from core.database.models import Agent

    with Session(engine) as s:
        # 基线 agent 注册，供其他表外键引用 (core 组件)。
        for aid in ("hermes", "deerflow", "meta_orchestrator"):
            exists = s.exec(
                select(Agent).where(Agent.agent_id == aid)
            ).first()
            if exists is None:
                s.add(Agent(agent_id=aid, name=aid, kind="core"))
        s.commit()


@contextmanager
def session_scope():
    """会话上下文管理器: 自动 commit / rollback / close。"""
    session = _get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_session():
    """同 session_scope，语义化别名。"""
    with session_scope() as s:
        yield s
