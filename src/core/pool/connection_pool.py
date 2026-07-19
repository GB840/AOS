"""连接池管理器 - 优化性能和资源使用

管理数据库连接、HTTP连接等资源，防止资源耗尽

DEPRECATED (audit 2026-07-19 / TD-8):
    本模块是一个 async-only 通用连接池，但在当前代码树中**没有任何真实消费者**。
    - `src/kernel/.../memory.py` 显式禁用此池，使用自己的 sqlite 直连；
    - `src/api/main.py` 虽调用 `initialize_pools()`，但运行时无人 acquire/release，
      实际是 no-op。
    类和工厂代码完整，未来若引入真正的高并发 SQLite 路径可重新启用。
    暂保留以避免破坏 import 链；如需清理，搜索 `from core.pool.connection_pool`
    及 `initialize_pools` 即可定位全部调用点。

"""

import asyncio
import threading
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar, Optional, Dict, Any, List
from collections import deque
import aiosqlite
import sqlite3

T = TypeVar('T')

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """连接池配置"""
    max_connections: int = 10
    min_connections: int = 2
    max_idle_time: int = 300  # 5分钟
    acquire_timeout: int = 30   # 30秒
    health_check_interval: int = 60  # 1分钟


class ConnectionFactory(ABC, Generic[T]):
    """连接工厂抽象基类"""
    
    @abstractmethod
    async def create_connection(self) -> T:
        """创建新连接"""
        pass
    
    @abstractmethod
    async def close_connection(self, conn: T) -> None:
        """关闭连接"""
        pass
    
    @abstractmethod
    async def validate_connection(self, conn: T) -> bool:
        """验证连接是否有效"""
        pass


class SQLiteConnectionFactory(ConnectionFactory[sqlite3.Connection]):
    """SQLite连接工厂"""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._lock = threading.Lock()
    
    async def create_connection(self) -> sqlite3.Connection:
        """创建SQLite连接"""
        def _create():
            conn = sqlite3.connect(
                self.database_path, 
                check_same_thread=False,
                timeout=20.0
            )
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=10000')
            conn.execute('PRAGMA temp_store=MEMORY')
            return conn
        
        # 在独立线程中执行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _create)
    
    async def close_connection(self, conn: sqlite3.Connection) -> None:
        """关闭SQLite连接"""
        def _close():
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"关闭SQLite连接失败: {e}")
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _close)
    
    async def validate_connection(self, conn: sqlite3.Connection) -> bool:
        """验证SQLite连接"""
        try:
            def _test():
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result[0] == 1
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _test)
        except Exception as e:
            logger.warning(f"SQLite连接验证失败: {e}")
            return False


class AsyncSQLiteConnectionFactory(ConnectionFactory[aiosqlite.Connection]):
    """异步SQLite连接工厂"""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
    
    async def create_connection(self) -> aiosqlite.Connection:
        """创建异步SQLite连接"""
        conn = await aiosqlite.connect(self.database_path)
        await conn.execute('PRAGMA journal_mode=WAL')
        await conn.execute('PRAGMA synchronous=NORMAL')
        await conn.execute('PRAGMA cache_size=10000')
        await conn.execute('PRAGMA temp_store=MEMORY')
        return conn
    
    async def close_connection(self, conn: aiosqlite.Connection) -> None:
        """关闭异步SQLite连接"""
        try:
            await conn.close()
        except Exception as e:
            logger.warning(f"关闭异步SQLite连接失败: {e}")
    
    async def validate_connection(self, conn: aiosqlite.Connection) -> bool:
        """验证异步SQLite连接"""
        try:
            async with conn.execute("SELECT 1") as cursor:
                result = await cursor.fetchone()
                return result[0] == 1
        except Exception as e:
            logger.warning(f"异步SQLite连接验证失败: {e}")
            return False


@dataclass
class PooledConnection(Generic[T]):
    """池化连接包装器"""
    connection: T
    created_at: float
    last_used_at: float
    in_use: bool = False


class ConnectionPool(Generic[T]):
    """通用连接池"""
    
    def __init__(self, factory: ConnectionFactory[T], config: PoolConfig = None):
        self.factory = factory
        self.config = config or PoolConfig()
        
        # 使用线程安全的队列
        self._available: deque[PooledConnection[T]] = deque()
        self._all_connections: List[PooledConnection[T]] = []
        self._lock = asyncio.Lock()
        
        # 健康检查任务
        self._health_task: Optional[asyncio.Task] = None
        self._closed = False
        
        logger.info(f"连接池初始化完成: max={self.config.max_connections}, min={self.config.min_connections}")
    
    async def initialize(self) -> None:
        """初始化连接池"""
        if self._closed:
            raise RuntimeError("连接池已关闭")
        
        async with self._lock:
            # 创建最小连接数
            for _ in range(self.config.min_connections):
                conn = await self.factory.create_connection()
                pooled_conn = PooledConnection(
                    connection=conn,
                    created_at=time.time(),
                    last_used_at=time.time()
                )
                self._available.append(pooled_conn)
                self._all_connections.append(pooled_conn)
        
        # 启动健康检查
        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"连接池初始化完成，创建了 {self.config.min_connections} 个连接")
    
    async def acquire(self) -> T:
        """获取连接"""
        if self._closed:
            raise RuntimeError("连接池已关闭")
        
        start_time = time.time()
        
        while True:
            if time.time() - start_time > self.config.acquire_timeout:
                raise TimeoutError(f"获取连接超时 ({self.config.acquire_timeout}秒)")
            
            async with self._lock:
                # 尝试从可用队列获取
                if self._available:
                    pooled_conn = self._available.popleft()
                    
                    # 验证连接有效性
                    if await self.factory.validate_connection(pooled_conn.connection):
                        pooled_conn.last_used_at = time.time()
                        pooled_conn.in_use = True
                        return pooled_conn.connection
                    else:
                        # 连接无效，关闭并移除
                        await self.factory.close_connection(pooled_conn.connection)
                        self._all_connections.remove(pooled_conn)
                        logger.warning("发现并移除了无效连接")
                
                # 创建新连接（如果未达上限）
                if len(self._all_connections) < self.config.max_connections:
                    try:
                        conn = await self.factory.create_connection()
                        pooled_conn = PooledConnection(
                            connection=conn,
                            created_at=time.time(),
                            last_used_at=time.time(),
                            in_use=True
                        )
                        self._all_connections.append(pooled_conn)
                        
                        logger.info(f"创建了新连接 (总数: {len(self._all_connections)}/{self.config.max_connections})")
                        return conn
                    except Exception as e:
                        logger.error(f"创建新连接失败: {e}")
                        raise
            
            # 等待一下再重试
            await asyncio.sleep(0.1)
    
    async def release(self, conn: T) -> None:
        """释放连接"""
        if self._closed:
            await self.factory.close_connection(conn)
            return
        
        async with self._lock:
            # 找到对应的池化连接
            pooled_conn = None
            for pc in self._all_connections:
                if pc.connection is conn:
                    pooled_conn = pc
                    break
            
            if not pooled_conn:
                logger.warning("尝试释放未知连接，直接关闭")
                await self.factory.close_connection(conn)
                return
            
            if pooled_conn.in_use:
                pooled_conn.in_use = False
                pooled_conn.last_used_at = time.time()
                
                # 验证连接是否仍然有效
                if await self.factory.validate_connection(conn):
                    self._available.append(pooled_conn)
                else:
                    # 连接无效，关闭并移除
                    await self.factory.close_connection(conn)
                    self._all_connections.remove(pooled_conn)
                    logger.warning("释放时检测到无效连接，已移除")
            else:
                logger.warning("重复释放连接")
    
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查出错: {e}")
    
    async def _perform_health_check(self) -> None:
        """执行健康检查"""
        async with self._lock:
            current_time = time.time()
            
            # 检查空闲连接是否过期
            expired_conns = []
            for pooled_conn in list(self._available):
                if current_time - pooled_conn.last_used_at > self.config.max_idle_time:
                    expired_conns.append(pooled_conn)
            
            # 移除过期连接（但要保持最小连接数）
            min_needed = self.config.min_connections
            available_count = len(self._available)
            
            for pooled_conn in expired_conns:
                if available_count > min_needed:
                    self._available.remove(pooled_conn)
                    self._all_connections.remove(pooled_conn)
                    await self.factory.close_connection(pooled_conn.connection)
                    available_count -= 1
                    logger.info("健康检查移除了过期空闲连接")
            
            # 检查所有连接的有效性
            invalid_conns = []
            for pooled_conn in self._all_connections:
                if not pooled_conn.in_use and not await self.factory.validate_connection(pooled_conn.connection):
                    invalid_conns.append(pooled_conn)
            
            # 移除无效连接
            for pooled_conn in invalid_conns:
                if pooled_conn in self._available:
                    self._available.remove(pooled_conn)
                self._all_connections.remove(pooled_conn)
                await self.factory.close_connection(pooled_conn.connection)
                logger.warning("健康检查移除了无效连接")
    
    async def close(self) -> None:
        """关闭连接池"""
        self._closed = True
        
        # 取消健康检查任务
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有连接
        async with self._lock:
            for pooled_conn in self._all_connections:
                if not pooled_conn.in_use:
                    await self.factory.close_connection(pooled_conn.connection)
            
            # 如果在使用的连接，记录警告
            in_use_count = sum(1 for pc in self._all_connections if pc.in_use)
            if in_use_count > 0:
                logger.warning(f"连接池关闭时有 {in_use_count} 个连接正在使用中")
            
            self._all_connections.clear()
            self._available.clear()
        
        logger.info("连接池已关闭")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        return {
            "total_connections": len(self._all_connections),
            "available_connections": len(self._available),
            "in_use_connections": sum(1 for pc in self._all_connections if pc.in_use),
            "max_connections": self.config.max_connections,
            "min_connections": self.config.min_connections,
            "is_closed": self._closed
        }


# 全局连接池实例
_sqlite_pool: Optional[ConnectionPool[aiosqlite.Connection]] = None
_lock = threading.Lock()


def get_sqlite_pool(database_path: str = None, config: PoolConfig = None) -> ConnectionPool[aiosqlite.Connection]:
    """获取全局SQLite连接池"""
    global _sqlite_pool
    
    with _lock:
        if _sqlite_pool is None:
            db_path = database_path or "data/aos.db"
            factory = AsyncSQLiteConnectionFactory(db_path)
            config = config or PoolConfig(max_connections=15, min_connections=3)
            _sqlite_pool = ConnectionPool(factory, config)
        return _sqlite_pool


async def initialize_pools() -> None:
    """初始化所有连接池"""
    global _sqlite_pool
    
    if _sqlite_pool and not _sqlite_pool._closed:
        await _sqlite_pool.initialize()
        logger.info("所有连接池初始化完成")


async def close_pools() -> None:
    """关闭所有连接池"""
    global _sqlite_pool
    
    if _sqlite_pool and not _sqlite_pool._closed:
        await _sqlite_pool.close()
        _sqlite_pool = None
        logger.info("所有连接池已关闭")
