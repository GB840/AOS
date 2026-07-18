import sqlite3
import json
import logging
import os
import re
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
from contextlib import contextmanager

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None

try:
    import zvec
    ZVEC_AVAILABLE = True
except ImportError:
    ZVEC_AVAILABLE = False
    zvec = None

try:
    from core.pool import get_sqlite_pool, initialize_pools, PoolConfig
    CONNECTION_POOL_AVAILABLE = True
except ImportError:
    CONNECTION_POOL_AVAILABLE = False

from utils.config import config

# 记忆生命周期桥接层（理念2：TTL + 分层降级）。opt-in：仅当 AOS_MEMORY_LIFECYCLE=1
# 时启用；关闭时桥接层为 no-op 且不建任何表，零足迹，绝不破坏既有工作记忆。
try:
    from memory.lifecycle import (
        MemoryLifecycleBridge,
        CATEGORY_FAILURE,
        CATEGORY_PREFERENCE,
        CATEGORY_GENERAL,
    )
except ImportError:  # pragma: no cover - 仅在非标准路径布局下触发
    MemoryLifecycleBridge = None
    CATEGORY_FAILURE = CATEGORY_PREFERENCE = CATEGORY_GENERAL = "general"

logger = logging.getLogger(__name__)


def escape_fts_query(query: str) -> str:
    """
    安全的FTS5查询转义函数
    
    FTS5特殊字符需要转义：
    - 双引号 " 需要变为 ""
    - 某些特殊操作符需要小心处理
    
    Args:
        query: 原始查询字符串
        
    Returns:
        转义后的安全查询字符串
    """
    if not query:
        return ""
    
    # 移除或转义危险字符
    # FTS5特殊字符: " ' ( ) [ ] { } * + - = ! < > & | ~
    
    # 转义双引号（SQLite FTS5使用双引号表示短语）
    escaped = query.replace('"', '""')
    
    # 移除其他可能的危险字符，保留基本的搜索功能
    # 保留字母、数字、中文、空格和基本标点
    safe_query = re.sub(r'[^\w\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef.,!?;:]', ' ', escaped)
    
    # 清理多余的空格
    safe_query = ' '.join(safe_query.split())
    
    # 如果查询为空，返回一个通配符
    if not safe_query:
        return "*"
    
    return safe_query


def validate_fts_query(query: str) -> bool:
    """
    验证FTS5查询是否安全
    
    Args:
        query: 查询字符串
        
    Returns:
        是否安全
    """
    if not query:
        return True
    
    # 检查长度限制
    if len(query) > 500:
        logger.warning(f"FTS查询过长被拒绝，长度: {len(query)} > 500")
        return False
        
    # 检查查询复杂度（防止过度复杂的查询导致性能问题）
    fts_operators = ['AND', 'OR', 'NOT', 'NEAR', '*', '"', '(', ')', '[', ']']
    operator_count = sum(1 for op in fts_operators if op in query.upper())
    if operator_count > 8:
        logger.warning(f"FTS查询操作符过多被拒绝，数量: {operator_count}")
        return False
        
    # 检查重复字符（可能的DoS尝试）。
    # 仅对 ASCII 字母数字应用该规则：中文等 CJK 文本天然存在高重复
    # （如「哈哈哈哈」「的的的的」），不应被误杀；而连续 ASCII 重复
    # （如「aaaaa…a」）才是典型 DoS 探活特征。
    from collections import Counter
    ascii_chars = [c for c in query if c.isascii() and c.isalnum()]
    if ascii_chars:
        ac = Counter(ascii_chars)
        mc = ac.most_common(1)[0][1]
        if mc > len(ascii_chars) * 0.8:  # 某个 ASCII 字符占比过高
            logger.warning("FTS查询可能为DoS攻击（ASCII字符重复率过高）")
            return False
    
    # 检查危险模式 - 增强版
    dangerous_patterns = [
        r'DROP\s+TABLE',   # SQL注入
        r'DELETE\s+FROM',  # SQL注入
        r'UPDATE\s+\w+\s+SET',  # SQL注入
        r'INSERT\s+INTO',  # SQL注入
        r'--',             # SQL注释
        r'/\*',            # SQL注释
        r';',              # 语句分隔
        r'\bUNION\b',      # UNION注入
        r'\bOR\b\s+\d+\s*=\s*\d+',  # 布尔注入
        r'\bAND\b\s+\d+\s*=\s*\d+', # 布尔注入
        
        # 新增：更复杂的SQL注入检测
        r'\bSELECT\b.*\bFROM\b',  # 窃取数据尝试
        r'\bCREATE\b.*\bTABLE\b', # 创建表尝试
        r'\bALTER\b.*\bTABLE\b',  # 修改表尝试
        r'\bEXEC\b',       # 执行代码
        r'\bEXECUTE\b',    # 执行代码
        r'information_schema', # 信息泄露
        r'sqlite_',        # SQLite系统表
        
        # 新增：重复杂查询导致的DoS防护
        r'\*.*\*',        # 多个通配符
        r'[(){}\[\]]{5,}', # 过多的嵌套符号
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            logger.warning(f"检测到危险FTS查询模式: {pattern}")
            return False
    
    return True


def safe_fts_match_query(query: str) -> str:
    """
    创建安全的FTS5 MATCH查询
    
    Args:
        query: 原始查询字符串
        
    Returns:
        安全的FTS5查询字符串
    """
    # 验证查询
    if not validate_fts_query(query):
        logger.warning(f"FTS查询验证失败，使用空查询: {query}")
        return "*"
    
    # 转义查询
    escaped_query = escape_fts_query(query)
    
    # 包装为短语搜索以提高准确性
    if not escaped_query or escaped_query == "*":
        return "*"
    
    # 如果包含多个词，使用OR连接
    words = escaped_query.split()
    if len(words) > 1:
        # 使用NEAR操作符提高相关性
        fts_query = ' OR '.join(f'"{word}"' for word in words)
    else:
        fts_query = f'"{escaped_query}"'
    
    return fts_query


class MemoryManager:
    def __init__(self):
        self.db_path = config.SQLITE_DB_PATH
        self.chroma_dir = config.CHROMADB_PERSIST_DIR
        self.zvec_dir = "./zvec_data"
        self.collection_name = config.VECTOR_COLLECTION_NAME
        self.vector_enabled = config.VECTOR_ENABLED
        self.vector_provider = "none"
        
        # 嵌入模型配置
        self._use_api_embedding = False
        self._local_embedding_model = None
        
        # 检查是否可以使用API嵌入
        if config.EMBEDDING_PROVIDER.lower() in ["zhipu", "siliconflow", "unified"]:
            api_key = getattr(config, f"{config.EMBEDDING_PROVIDER.upper()}_API_KEY", "")
            if api_key:
                self._use_api_embedding = True
                logger.info(f"使用API嵌入服务: {config.EMBEDDING_PROVIDER}")
            else:
                logger.warning(f"API嵌入服务 {config.EMBEDDING_PROVIDER} 未配置API密钥，将使用本地模型")
        else:
            logger.info(f"使用本地嵌入模型: {config.EMBEDDING_PROVIDER}")

        Path(os.path.dirname(self.db_path)).mkdir(parents=True, exist_ok=True)
        
        self.chroma_client = None
        self.collection = None
        self.zvec_client = None
        self.zvec_index = None
        
        # 记忆层使用独立 sqlite 连接 (与 core.database 单一真相库共用物理文件)。
        # 统一走单连接模式，避免「连接池/单连接」双路径不一致导致 self.sqlite_conn 未定义
        # (旧实现在连接池可用时从不设置 sqlite_conn，却有许多方法直接 self.sqlite_conn.execute)。
        self.sqlite_conn = self._init_sqlite()
        self._use_connection_pool = False
        self._lock = threading.Lock()  # 串行化所有 sqlite 访问，避免多线程共享单连接竞态

        # 注意：core.pool.ConnectionPool 的 acquire/release 均为 async 协程，
        # 而本类所有数据库操作为同步上下文，无法安全 await。旧实现曾在此尝试启用
        # 连接池并把 _use_connection_pool 置 True，导致 get_connection() 调用
        # 不存在的同步 get_connection() 而抛 AttributeError（见 DEEP_AUDIT 报告 Bug#1）。
        # 统一使用上面的单连接 + 锁模式，不再启用连接池。
        self._use_connection_pool = False

        self._init_vector_store()

        # 记忆生命周期桥接层（理念2）。opt-in：AOS_MEMORY_LIFECYCLE=1 时启用并建 companion 表；
        # 关闭时 MemoryLifecycleBridge.enabled=False，所有钩子为 no-op，零足迹。
        self.lifecycle = (
            MemoryLifecycleBridge.from_env(self.sqlite_conn)
            if MemoryLifecycleBridge is not None
            else None
        )
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（单连接 + 锁，保证线程安全）。

        注：core.pool.ConnectionPool 的 acquire/release 均为 async，无法在同步
        上下文中使用，故 MemoryManager 统一走单连接模式（见 __init__ 说明）。

        直接以 @contextmanager 装饰方法：调用 ``with self.get_connection() as
        conn:`` 即进入已就绪的上下文管理器，不再像旧实现那样先返回内部函数引用、
        再二次调用才生成 CM 对象（反直觉且易误读为返回一个连接对象）。
        """
        with self._lock:
            yield self.sqlite_conn
    
    def close(self):
        """关闭资源"""
        try:
            if hasattr(self, '_pool') and self._use_connection_pool:
                # 连接池由全局管理器负责，不需要在这里关闭
                pass
            elif hasattr(self, 'sqlite_conn'):
                self.sqlite_conn.close()

            # 关闭向量数据库连接
            if self.zvec_client:
                self.zvec_client.close()

            # ChromaDB PersistentClient 持有文件句柄，需要显式释放
            if hasattr(self, 'chroma_client') and self.chroma_client is not None:
                try:
                    # ChromaDB PersistentClient 无显式 close()，通过置 None 让 GC 回收
                    self.chroma_client = None
                    self.collection = None
                except Exception as exc:
                    logger.debug("ChromaDB cleanup failed: %s", exc)

            logger.info("MemoryManager资源已关闭")
        except Exception as e:
            logger.error(f"关闭MemoryManager时出错: {e}")

    def _init_vector_store(self):
        """初始化向量存储，优先使用 Zvec，其次 ChromaDB"""
        if ZVEC_AVAILABLE:
            try:
                Path(self.zvec_dir).mkdir(parents=True, exist_ok=True)
                self.zvec_client = self._init_zvec()
                if self.zvec_client:
                    self.vector_enabled = True
                    self.vector_provider = "zvec"
                    logger.info("记忆层初始化完成 (SQLite + Zvec)")
                    return
            except Exception as e:
                logger.warning(f"Zvec初始化失败，尝试使用ChromaDB: {e}")
        
        if CHROMADB_AVAILABLE:
            try:
                Path(self.chroma_dir).mkdir(parents=True, exist_ok=True)
                self.chroma_client = self._init_chroma()
                self.collection = self._get_or_create_collection()
                self.vector_enabled = True
                self.vector_provider = "chromadb"
                logger.info("记忆层初始化完成 (SQLite + ChromaDB)")
                return
            except Exception as e:
                logger.warning(f"ChromaDB初始化失败，将仅使用SQLite: {e}")
        
        logger.info("向量存储未安装，记忆层初始化完成 (仅SQLite，向量搜索禁用)")

    def _init_sqlite(self) -> sqlite3.Connection:
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception as e:
            logger.warning(f"无法设置WAL模式，使用默认模式: {e}")
        try:
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception as exc:
            logger.warning("PRAGMA foreign_keys=ON failed: %s", exc)
        conn.row_factory = sqlite3.Row

        try:
            self._create_tables(conn)
        except Exception as e:
            logger.warning(f"创建表失败，尝试重新连接: {e}")
            conn.close()
            for ext in ['-wal', '-shm']:
                wal_file = Path(self.db_path + ext)
                if wal_file.exists():
                    try:
                        wal_file.unlink()
                    except Exception as exc:
                        logger.debug("WAL file cleanup failed (%s): %s", wal_file, exc)
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
        return conn

    def _create_tables(self, conn: sqlite3.Connection):
        """记忆层表结构。

        基础表 (conversations / knowledge / tasks) 直接用本连接的 db 文件创建，
        不再委托 core.database.init_db()——后者是进程级引擎单例，其 SQLITE_DB_PATH
        在 monkeypatch 改路径的测试场景下不响应变化，会把表建到错误的库（详见
        DEEP_AUDIT 复核发现的「no such table: main.conversations」问题）。

        schema 与 core.database.models.infra 的 Conversation/Knowledge/Task 模型保持一致。
        """
        # 基础表（字段与 core.database.models.infra 对齐；TimestampMixin 提供 created_at/updated_at）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                input TEXT DEFAULT '{}',
                output TEXT DEFAULT '{}',
                error TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
            CREATE INDEX IF NOT EXISTS idx_knowledge_created ON knowledge(created_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

            CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
                content,
                session_id,
                content='conversations',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
                INSERT INTO conversations_fts(rowid, content, session_id)
                VALUES (new.id, new.content, new.session_id);
            END;

            CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, content, session_id)
                VALUES ('delete', old.id, old.content, old.session_id);
            END;

            CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
                INSERT INTO conversations_fts(conversations_fts, rowid, content, session_id)
                VALUES ('delete', old.id, old.content, old.session_id);
                INSERT INTO conversations_fts(rowid, content, session_id)
                VALUES (new.id, new.content, new.session_id);
            END;

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                title, content, source, tags,
                content='knowledge',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
                INSERT INTO knowledge_fts(rowid, title, content, source, tags)
                VALUES (new.id, new.title, new.content, new.source, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, source, tags)
                VALUES ('delete', old.id, old.title, old.content, old.source, old.tags);
            END;
            """
        )
        conn.commit()

    def _init_zvec(self):
        """初始化 Zvec 向量数据库"""
        if not ZVEC_AVAILABLE:
            return None
        try:
            from zvec import (
                CollectionSchema,
                FieldSchema,
                VectorSchema,
                DataType,
                create_and_open
            )
            
            memory_path = os.path.join(self.zvec_dir, "memory")
            
            schema = CollectionSchema(
                name="memory",
                fields=[
                    FieldSchema(name="id", data_type=DataType.STRING),
                    FieldSchema(name="content", data_type=DataType.STRING),
                    FieldSchema(name="metadata", data_type=DataType.STRING),
                ],
                vectors=[
                    VectorSchema(
                        name="embedding",
                        data_type=DataType.VECTOR_FP32,
                        dimension=384,
                    )
                ],
            )
            
            try:
                self.zvec_index = zvec.open(memory_path)
            except Exception as exc:
                logger.warning("zvec.open() failed, falling back to create_and_open: %s", exc)
                self.zvec_index = create_and_open(
                    path=memory_path,
                    schema=schema,
                )
            
            logger.info("Zvec 索引初始化成功")
            return True
        except Exception as e:
            logger.warning(f"Zvec 索引初始化失败: {e}")
            return None

    def _init_chroma(self):
        if not CHROMADB_AVAILABLE:
            return None
        client = chromadb.PersistentClient(
            path=self.chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        return client

    def _get_or_create_collection(self):
        if not self.vector_enabled or not self.chroma_client:
            return None
        try:
            return self.chroma_client.get_collection(name=self.collection_name)
        except Exception as exc:
            logger.debug("ChromaDB get_collection failed, creating new: %s", exc)
            return self.chroma_client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    def add_conversation(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None, category: str = CATEGORY_GENERAL) -> int:
        """添加对话（批量写入优化，N+1查询防护）

        Args:
            category: 记忆分类（理念2），控制 TTL 与淘汰策略：
                      'failure' 短期故障记忆 / 'preference' 长期环境偏好 / 'general' 通用。
                      仅当桥接层启用(AOS_MEMORY_LIFECYCLE=1)时生效，否则忽略。
        """
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        
        # 使用连接池避免全局锁竞争，提高并发性能
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO conversations (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
                (session_id, role, content, meta_json),
            )
            conn.commit()
            conv_id = cursor.lastrowid

        # 桥接层：记录新增记忆的分类与初始热度（opt-in，失败隔离）
        if self.lifecycle is not None:
            self.lifecycle.record_add("conversations", conv_id, category)

        if self.vector_enabled and self.collection:
            self._add_to_vector_store(
                doc_id=f"conv_{conv_id}",
                content=content,
                metadata={
                    "type": "conversation",
                    "session_id": session_id,
                    "role": role,
                    "created_at": datetime.now().isoformat(),
                },
            )
        return conv_id

    def get_conversation_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self.sqlite_conn.execute(
                "SELECT * FROM conversations WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cursor.fetchall()
        result = []
        for row in reversed(rows):
            result.append(
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]),
                    "created_at": row["created_at"],
                }
            )
        return result

    def _execute_query(self, query: str, params: tuple = (), fetch_all: bool = True):
        """执行数据库查询（支持连接池）"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            if fetch_all:
                return cursor.fetchall()
            else:
                return cursor.fetchone()
    
    def _execute_update(self, query: str, params: tuple = ()):
        """执行数据库更新（支持连接池）"""
        with self.get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def search_conversations(self, query: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索对话历史（使用安全的FTS5查询，连接池优化）"""
        # 使用安全的FTS查询转义
        safe_query = safe_fts_match_query(query)

        # 使用连接池避免全局锁竞争
        with self.get_connection() as conn:
            # 批量查询优化：单次查询获取所有数据
            if session_id:
                sql = """
                SELECT rowid as id, content, session_id 
                FROM conversations_fts
                WHERE conversations_fts MATCH ? AND session_id = ?
                ORDER BY rank LIMIT ?
                """
                params = (safe_query, session_id, limit)
            else:
                sql = """
                SELECT rowid as id, content, session_id
                FROM conversations_fts
                WHERE conversations_fts MATCH ?
                ORDER BY rank LIMIT ?
                """
                params = (safe_query, limit)
            
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        # 桥接层：记录被命中的记忆热度（opt-in，失败隔离）。批量单次事务，降低热路径开销。
        if self.lifecycle is not None and rows:
            self.lifecycle.record_access_many("conversations", [row["id"] for row in rows])

        # 批量构建结果，减少循环开销
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "session_id": row["session_id"],
            }
            for row in rows
        ]

    def add_knowledge(self, title: str, content: str, source: str = "", tags: Optional[List[str]] = None, metadata: Optional[Dict] = None, category: str = CATEGORY_GENERAL) -> int:
        """添加知识库（批量写入优化）

        Args:
            category: 记忆分类（理念2），控制 TTL 与淘汰策略。仅桥接层启用时生效。
        """
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        
        # 使用连接池避免全局锁竞争
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO knowledge (title, content, source, tags, metadata) VALUES (?, ?, ?, ?, ?)",
                (title, content, source, tags_json, meta_json),
            )
            conn.commit()
            knowledge_id = cursor.lastrowid

        # 桥接层：记录新增记忆的分类与初始热度（opt-in，失败隔离）
        if self.lifecycle is not None:
            self.lifecycle.record_add("knowledge", knowledge_id, category)

        # 向量存储异步处理，避免阻塞主流程
        if self.vector_enabled and self.collection:
            try:
                self._add_to_vector_store(
                    doc_id=f"know_{knowledge_id}",
                    content=f"{title}\n{content}",
                    metadata={
                        "type": "knowledge",
                        "title": title,
                        "source": source,
                        "tags": tags_json,
                        "created_at": datetime.now().isoformat(),
                    },
                )
            except Exception as e:
                logger.warning(f"向量存储失败但不影响主要功能: {e}")
        
        return knowledge_id

    def search_knowledge_fulltext(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        # 使用安全的FTS查询转义
        safe_query = safe_fts_match_query(query)
        
        with self._lock:
            cursor = self.sqlite_conn.execute(
                """SELECT rowid as id, title, content, source, tags
                   FROM knowledge_fts
                   WHERE knowledge_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (safe_query, limit),
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "content": row["content"],
                    "source": row["source"],
                    "tags": json.loads(row["tags"] or "[]"),
                }
            )

        # 桥接层：记录被命中的知识热度（opt-in，失败隔离）
        if self.lifecycle is not None and rows:
            self.lifecycle.record_access_many("knowledge", [row["id"] for row in rows])

        return result

    def semantic_search(self, query: str, n_results: int = 5, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.vector_enabled:
            return []
        
        try:
            if self.vector_provider == "zvec" and self.zvec_index:
                return self._semantic_search_zvec(query, n_results, filter_type)
            elif self.vector_provider == "chromadb" and self.collection:
                return self._semantic_search_chromadb(query, n_results, filter_type)
            else:
                return []
        except Exception as e:
            logger.warning(f"向量搜索失败: {e}")
            return []

    def _semantic_search_zvec(self, query: str, n_results: int, filter_type: Optional[str]) -> List[Dict[str, Any]]:
        """使用 Zvec 进行语义搜索"""
        embedding = self._get_embedding(query)
        results = self.zvec_index.search(
            query_vector=embedding,
            vector_name="embedding",
            top_k=n_results,
        )
        
        result = []
        for r in results:
            result.append(
                {
                    "id": str(r.id),
                    "content": "",
                    "metadata": {},
                    "distance": 1 - r.score,
                    "similarity": r.score,
                    "provider": "zvec",
                }
            )
        return result

    def _semantic_search_chromadb(self, query: str, n_results: int, filter_type: Optional[str]) -> List[Dict[str, Any]]:
        """使用 ChromaDB 进行语义搜索"""
        where = {}
        if filter_type:
            where = {"type": filter_type}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        result = []
        for i, doc in enumerate(documents):
            result.append(
                {
                    "id": ids[i],
                    "content": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": distances[i] if i < len(distances) else None,
                    "similarity": 1 - (distances[i] if i < len(distances) else 0),
                    "provider": "chromadb",
                }
            )
        return result

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的向量表示 - 支持多种嵌入模型"""
        try:
            # 优先使用API嵌入模型
            if self._use_api_embedding:
                return self._get_api_embedding(text)
            
            # 降级到本地模型
            return self._get_local_embedding(text)
            
        except Exception as e:
            logger.error(f"嵌入服务完全不可用: {e}")
            logger.warning("使用零向量作为降级方案，请检查嵌入服务配置")
            return [0.0] * config.EMBEDDING_DIMENSION
    
    def _get_api_embedding(self, text: str) -> List[float]:
        """使用API获取嵌入向量"""
        try:
            provider = config.EMBEDDING_PROVIDER.lower()

            # Map provider → (base_url, api_key, model, extra_data)
            provider_config = {
                "zhipu": (config.ZHIPU_BASE_URL, config.ZHIPU_API_KEY, "embedding-2", {}),
                "siliconflow": (config.SILICONFLOW_BASE_URL, config.SILICONFLOW_API_KEY,
                                "BAAI/bge-small-zh-v1.5", {"encoding_format": "float"}),
                "unified": (config.UNIFIED_BASE_URL, config.UNIFIED_API_KEY,
                            config.EMBEDDING_MODEL, {}),
            }

            if provider in provider_config:
                base_url, api_key, model, extra = provider_config[provider]
                if api_key:
                    return self._get_api_embedding_from_provider(text, base_url, api_key, model, extra)

            logger.warning(f"API嵌入provider '{provider}' 不可用，降级到本地模型")
            return self._get_local_embedding(text)

        except Exception as e:
            logger.error(f"API嵌入失败: {e}")
            return self._get_local_embedding(text)

    def _get_api_embedding_from_provider(
        self, text: str, base_url: str, api_key: str,
        model: str, extra_data: Optional[Dict] = None,
    ) -> List[float]:
        """统一的 API 嵌入调用 — 消除 zhipu/siliconflow/unified 三套重复代码。"""
        import httpx

        data = {"model": model, "input": text}
        if extra_data:
            data.update(extra_data)

        response = httpx.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=data,
            timeout=30.0,
        )
        response.raise_for_status()
        embedding = response.json()["data"][0]["embedding"]
        logger.info(f"嵌入成功 ({model}), 维度: {len(embedding)}")
        return embedding
    
    def _get_local_embedding(self, text: str) -> List[float]:
        """使用本地模型获取嵌入"""
        try:
            from sentence_transformers import SentenceTransformer
            
            # 使用缓存避免重复加载模型
            if not hasattr(self, '_local_embedding_model'):
                logger.info(f"加载本地嵌入模型: {config.EMBEDDING_MODEL}")
                self._local_embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
            
            embedding = self._local_embedding_model.encode(text).tolist()
            logger.info(f"本地嵌入成功，维度: {len(embedding)}")
            return embedding
            
        except ImportError:
            logger.warning("sentence-transformers未安装，请运行: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"本地嵌入失败: {e}")
            raise

    def _add_to_vector_store(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        if not self.vector_enabled:
            return
        
        if self.vector_provider == "zvec" and self.zvec_index:
            self._add_to_zvec(doc_id, content, metadata)
        elif self.vector_provider == "chromadb" and self.collection:
            self._add_to_chromadb(doc_id, content, metadata)

    def _add_to_zvec(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """添加到 Zvec 向量存储"""
        try:
            embedding = self._get_embedding(content)
            self.zvec_index.insert(
                docs=[{
                    "id": doc_id,
                    "content": content,
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                }],
                vectors={"embedding": [embedding]},
            )
            self.zvec_index.commit()
        except Exception as e:
            logger.warning(f"Zvec 添加失败 [{doc_id}]: {e}")

    def _add_to_chromadb(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """添加到 ChromaDB 向量存储"""
        for attempt in range(3):
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing and existing["ids"]:
                    self.collection.update(
                        ids=[doc_id],
                        documents=[content],
                        metadatas=[metadata],
                    )
                else:
                    self.collection.add(
                        ids=[doc_id],
                        documents=[content],
                        metadatas=[metadata],
                    )
                return
            except Exception as e:
                if attempt < 2:
                    time.sleep(1)
                else:
                    logger.warning(f"ChromaDB 添加失败 [{doc_id}]: {e}")

    def create_task(self, task_id: str, task_type: str, input_data: Dict) -> str:
        input_json = json.dumps(input_data, ensure_ascii=False)
        with self._lock:
            self.sqlite_conn.execute(
                "INSERT OR REPLACE INTO tasks (id, type, status, input, created_at, updated_at) VALUES (?, ?, 'pending', ?, ?, ?)",
                (task_id, task_type, input_json, datetime.now().isoformat(), datetime.now().isoformat()),
            )
            self.sqlite_conn.commit()
        return task_id

    def update_task_status(self, task_id: str, status: str, output: Optional[Dict] = None, error: str = ""):
        output_json = json.dumps(output or {}, ensure_ascii=False)
        with self._lock:
            self.sqlite_conn.execute(
                "UPDATE tasks SET status = ?, output = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, output_json, error, datetime.now().isoformat(), task_id),
            )
            self.sqlite_conn.commit()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cursor = self.sqlite_conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "input": json.loads(row["input"]),
            "output": json.loads(row["output"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            if status:
                cursor = self.sqlite_conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = self.sqlite_conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "type": row["type"],
                "status": row["status"],
                "error": row["error"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def hybrid_search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        vector_results = self.semantic_search(query, n_results=n_results)
        vector_ids = set(r["id"] for r in vector_results)

        fulltext_convs = self.search_conversations(query, limit=n_results)
        fulltext_knowledge = self.search_knowledge_fulltext(query, limit=n_results)

        all_results = vector_results
        for conv in fulltext_convs:
            doc_id = f"conv_{conv['id']}"
            if doc_id not in vector_ids:
                all_results.append(
                    {
                        "id": doc_id,
                        "content": conv["content"],
                        "metadata": {"type": "conversation", "session_id": conv["session_id"]},
                        "similarity": 0.5,
                        "source": "fulltext",
                    }
                )
        for know in fulltext_knowledge:
            doc_id = f"know_{know['id']}"
            if doc_id not in vector_ids:
                all_results.append(
                    {
                        "id": doc_id,
                        "content": know["content"],
                        "metadata": {"type": "knowledge", "title": know["title"]},
                        "similarity": 0.5,
                        "source": "fulltext",
                    }
                )

        all_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return all_results[:n_results]
