"""
数据库连接池管理器

提供SQLite连接池，提高并发性能和资源利用率
"""

import sqlite3
import threading
import logging
from queue import Queue, Empty, Full
from contextlib import contextmanager
from typing import Optional
from pathlib import Path

from utils.config import config

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    SQLite连接池管理器
    
    特性：
    - 连接复用，减少创建开销
    - 自动清理和连接验证
    - 线程安全
    - 支持超时和大小限制
    """
    
    def __init__(
        self, 
        db_path: str, 
        pool_size: int = 5, 
        max_overflow: int = 10,
        timeout: float = 30.0
    ):
        """
        初始化连接池
        
        Args:
            db_path: 数据库文件路径
            pool_size: 基础连接池大小
            max_overflow: 最大额外连接数
            timeout: 获取连接超时时间（秒）
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        
        # 连接池队列
        self._pool = Queue(maxsize=pool_size)
        self._overflow_connections = 0
        self._lock = threading.Lock()
        self._created_connections = 0
        
        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 预创建连接
        self._initialize_pool()
        
        logger.info(f"数据库连接池初始化完成: {pool_size}个基础连接, 最多{max_overflow}个额外连接")
    
    def _initialize_pool(self):
        """预创建连接池"""
        for _ in range(self.pool_size):
            try:
                conn = self._create_connection()
                self._pool.put(conn, block=False)
                self._created_connections += 1
            except Exception as e:
                logger.error(f"创建数据库连接失败: {e}")
                raise
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30,
            isolation_level=None,  # 自动提交模式
            cached_statements=100  # 缓存预处理语句
        )
        
        # 优化PRAGMA设置
        pragmas = [
            "PRAGMA journal_mode=WAL",          # WAL模式，提高并发
            "PRAGMA synchronous=NORMAL",        # 平衡性能和安全
            "PRAGMA cache_size=-64000",         # 64MB缓存
            "PRAGMA temp_store=MEMORY",         # 临时表存储在内存
            "PRAGMA mmap_size=268435456",       # 256MB内存映射
            "PRAGMA page_size=4096",            # 优化页面大小
            "PRAGMA foreign_keys=ON",           # 启用外键约束
            "PRAGMA busy_timeout=30000",        # 30秒超时
        ]
        
        for pragma in pragmas:
            try:
                conn.execute(pragma)
            except Exception as e:
                logger.warning(f"设置PRAGMA失败 {pragma}: {e}")
        
        conn.row_factory = sqlite3.Row  # 返回字典格式
        
        logger.debug(f"创建新数据库连接: {id(conn)}")
        return conn
    
    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）
        
        使用示例：
            with pool.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM table")
                results = cursor.fetchall()
        """
        conn = None
        try:
            conn = self._acquire_connection()
            yield conn
        except Exception as e:
            logger.error(f"数据库操作错误: {e}")
            # 发生错误时关闭连接
            if conn:
                self._close_connection(conn)
                conn = None
            raise
        finally:
            if conn:
                self._release_connection(conn)
    
    def _acquire_connection(self) -> sqlite3.Connection:
        """从连接池获取连接"""
        try:
            # 尝试从基础池获取
            conn = self._pool.get(timeout=self.timeout)
            logger.debug(f"从连接池获取连接: {id(conn)}")
            return conn
            
        except Empty:
            # 基础池为空，尝试创建额外连接
            with self._lock:
                if self._overflow_connections < self.max_overflow:
                    try:
                        conn = self._create_connection()
                        self._overflow_connections += 1
                        self._created_connections += 1
                        logger.info(f"创建额外连接: {id(conn)} (当前额外连接: {self._overflow_connections})")
                        return conn
                    except Exception as e:
                        logger.error(f"创建额外连接失败: {e}")
                        raise
                
                # 无法创建额外连接，等待基础连接
                logger.warning("连接池已满，等待连接释放...")
                conn = self._pool.get(timeout=self.timeout)
                return conn
    
    def _release_connection(self, conn: sqlite3.Connection):
        """释放连接回连接池"""
        try:
            # 验证连接是否有效
            try:
                conn.execute("SELECT 1").fetchone()
                
                # 尝试放回基础池
                try:
                    self._pool.put(conn, block=False)
                    logger.debug(f"连接释放回基础池: {id(conn)}")
                except Full:
                    # 基础池已满，这是额外连接，关闭它
                    with self._lock:
                        self._overflow_connections -= 1
                        self._close_connection(conn)
                        logger.debug(f"关闭额外连接: {id(conn)} (剩余额外连接: {self._overflow_connections})")
                        
            except sqlite3.Error:
                # 连接已失效，关闭并创建新连接替换
                logger.warning("检测到失效连接，重新创建")
                with self._lock:
                    if self._overflow_connections > 0:
                        self._overflow_connections -= 1
                    self._close_connection(conn)
                    
                    # 创建新连接补充池
                    try:
                        new_conn = self._create_connection()
                        self._pool.put(new_conn, block=False)
                        self._created_connections += 1
                    except Exception as e:
                        logger.error(f"创建替换连接失败: {e}")
                        
        except Exception as e:
            logger.error(f"释放连接时出错: {e}")
            self._close_connection(conn)
    
    def _close_connection(self, conn: sqlite3.Connection):
        """关闭数据库连接"""
        try:
            conn.close()
            logger.debug(f"关闭数据库连接: {id(conn)}")
        except Exception as e:
            logger.warning(f"关闭连接时出错: {e}")
    
    def close_all(self):
        """关闭所有连接"""
        logger.info("关闭所有数据库连接...")
        
        # 关闭基础池中的连接
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                self._close_connection(conn)
            except Empty:
                break
        
        # 注意：额外连接会在释放时自动关闭
        logger.info(f"连接池已关闭，总共创建了 {self._created_connections} 个连接")
    
    def get_status(self) -> dict:
        """获取连接池状态"""
        with self._lock:
            return {
                "pool_size": self.pool_size,
                "max_overflow": self.max_overflow,
                "available_connections": self._pool.qsize(),
                "overflow_connections": self._overflow_connections,
                "total_created": self._created_connections,
                "db_path": self.db_path
            }


# 全局连接池实例
_db_pool: Optional[DatabaseConnectionPool] = None
_pool_lock = threading.Lock()


def get_db_pool() -> DatabaseConnectionPool:
    """获取全局数据库连接池实例"""
    global _db_pool
    
    if _db_pool is None:
        with _pool_lock:
            if _db_pool is None:
                _db_pool = DatabaseConnectionPool(
                    db_path=config.SQLITE_DB_PATH,
                    pool_size=5,
                    max_overflow=10
                )
    
    return _db_pool


def close_db_pool():
    """关闭全局数据库连接池"""
    global _db_pool
    
    if _db_pool is not None:
        _db_pool.close_all()
        _db_pool = None
        logger.info("全局数据库连接池已关闭")