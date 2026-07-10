"""
缓存管理系统

提供多层缓存支持，优化性能
"""

import hashlib
import json
import logging
import threading
from functools import wraps
from typing import Any, Callable, Optional
from cachetools import TTLCache, LRUCache

logger = logging.getLogger(__name__)


class CacheManager:
    """
    统一缓存管理器
    
    支持多种缓存策略：
    - TTL缓存：带过期时间的缓存
    - LRU缓存：最近最少使用缓存
    - 永久缓存：不过期的缓存
    """
    
    def __init__(self):
        # 向量嵌入缓存（1小时TTL）
        self.embedding_cache = TTLCache(maxsize=2000, ttl=3600)
        self.embedding_cache_lock = threading.Lock()
        
        # 查询结果缓存（5分钟TTL）
        self.query_cache = TTLCache(maxsize=1000, ttl=300)
        self.query_cache_lock = threading.Lock()
        
        # API响应缓存（10分钟TTL）
        self.api_cache = TTLCache(maxsize=500, ttl=600)
        self.api_cache_lock = threading.Lock()
        
        # 模型配置缓存（永久）
        self.config_cache = LRUCache(maxsize=100)
        self.config_cache_lock = threading.Lock()
        
        # 统计信息
        self.stats = {
            "embedding_hits": 0,
            "embedding_misses": 0,
            "query_hits": 0,
            "query_misses": 0,
            "api_hits": 0,
            "api_misses": 0
        }
        
        logger.info("缓存管理器初始化完成")
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """生成缓存键"""
        # 将参数转换为字符串
        key_parts = [prefix]
        
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            else:
                # 对复杂对象使用哈希
                key_parts.append(hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest())
        
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        
        return ":".join(key_parts)
    
    def get_embedding(self, text: str) -> Optional[list]:
        """获取缓存的嵌入向量"""
        cache_key = self._generate_key("embed", text)
        
        with self.embedding_cache_lock:
            if cache_key in self.embedding_cache:
                self.stats["embedding_hits"] += 1
                return self.embedding_cache[cache_key]
            else:
                self.stats["embedding_misses"] += 1
                return None
    
    def set_embedding(self, text: str, embedding: list):
        """设置嵌入向量缓存"""
        cache_key = self._generate_key("embed", text)
        
        with self.embedding_cache_lock:
            self.embedding_cache[cache_key] = embedding
    
    def get_query_result(self, query: str, **params) -> Optional[Any]:
        """获取查询结果缓存"""
        cache_key = self._generate_key("query", query, **params)
        
        with self.query_cache_lock:
            if cache_key in self.query_cache:
                self.stats["query_hits"] += 1
                return self.query_cache[cache_key]
            else:
                self.stats["query_misses"] += 1
                return None
    
    def set_query_result(self, query: str, result: Any, **params):
        """设置查询结果缓存"""
        cache_key = self._generate_key("query", query, **params)
        
        with self.query_cache_lock:
            self.query_cache[cache_key] = result
    
    def get_api_response(self, endpoint: str, **params) -> Optional[Any]:
        """获取API响应缓存"""
        cache_key = self._generate_key("api", endpoint, **params)
        
        with self.api_cache_lock:
            if cache_key in self.api_cache:
                self.stats["api_hits"] += 1
                return self.api_cache[cache_key]
            else:
                self.stats["api_misses"] += 1
                return None
    
    def set_api_response(self, endpoint: str, response: Any, **params):
        """设置API响应缓存"""
        cache_key = self._generate_key("api", endpoint, **params)
        
        with self.api_cache_lock:
            self.api_cache[cache_key] = response
    
    def get_config(self, key: str) -> Optional[Any]:
        """获取配置缓存"""
        with self.config_cache_lock:
            return self.config_cache.get(key)
    
    def set_config(self, key: str, value: Any):
        """设置配置缓存"""
        with self.config_cache_lock:
            self.config_cache[key] = value
    
    def clear_all(self):
        """清空所有缓存"""
        with self.embedding_cache_lock:
            self.embedding_cache.clear()
        
        with self.query_cache_lock:
            self.query_cache.clear()
        
        with self.api_cache_lock:
            self.api_cache.clear()
        
        with self.config_cache_lock:
            self.config_cache.clear()
        
        # 重置统计
        self.stats = {k: 0 for k in self.stats}
        
        logger.info("所有缓存已清空")
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            **self.stats,
            "embedding_cache_size": len(self.embedding_cache),
            "query_cache_size": len(self.query_cache),
            "api_cache_size": len(self.api_cache),
            "config_cache_size": len(self.config_cache),
        }
    
    def optimize_caches(self):
        """优化缓存（清理过期项）"""
        # TTLCache会自动清理过期项，这里主要是触发清理
        with self.embedding_cache_lock:
            # 触发TTL清理
            _ = list(self.embedding_cache.items())
        
        with self.query_cache_lock:
            _ = list(self.query_cache.items())
        
        with self.api_cache_lock:
            _ = list(self.api_cache.items())
        
        logger.info("缓存优化完成")


# 全局缓存管理器实例
_cache_manager: Optional[CacheManager] = None
_cache_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _cache_manager
    
    if _cache_manager is None:
        with _cache_lock:
            if _cache_manager is None:
                _cache_manager = CacheManager()
    
    return _cache_manager


def cached_embedding(cache_manager: Optional[CacheManager] = None):
    """
    嵌入向量缓存装饰器
    
    使用示例：
        @cached_embedding()
        def get_embedding(text: str) -> List[float]:
            # 计算嵌入向量的代码
            pass
    """
    if cache_manager is None:
        cache_manager = get_cache_manager()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 生成缓存键
            if args and isinstance(args[0], str):
                text = args[0]
                cache_key = cache_manager._generate_key("embed", text)
                
                # 尝试从缓存获取
                cached_result = cache_manager.get_embedding(text)
                if cached_result is not None:
                    return cached_result
            
            # 执行原始函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            if args and isinstance(args[0], str):
                text = args[0]
                cache_manager.set_embedding(text, result)
            
            return result
        
        return wrapper
    
    return decorator


def cached_query(ttl: int = 300, cache_manager: Optional[CacheManager] = None):
    """
    查询结果缓存装饰器
    
    使用示例：
        @cached_query(ttl=600)
        def search_database(query: str, params: dict) -> List[dict]:
            # 数据库查询代码
            pass
    """
    if cache_manager is None:
        cache_manager = get_cache_manager()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 生成缓存键
            cache_key = cache_manager._generate_key("query", func.__name__, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_result = cache_manager.get_query_result(func.__name__, **kwargs)
            if cached_result is not None:
                return cached_result
            
            # 执行原始函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            cache_manager.set_query_result(func.__name__, result, **kwargs)
            
            return result
        
        return wrapper
    
    return decorator


def cached_api(ttl: int = 600, cache_manager: Optional[CacheManager] = None):
    """
    API响应缓存装饰器
    
    使用示例：
        @cached_api(ttl=120)
        def call_external_api(endpoint: str, params: dict) -> dict:
            # API调用代码
            pass
    """
    if cache_manager is None:
        cache_manager = get_cache_manager()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 生成缓存键
            cache_key = cache_manager._generate_key("api", func.__name__, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_result = cache_manager.get_api_response(func.__name__, **kwargs)
            if cached_result is not None:
                return cached_result
            
            # 执行原始函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            cache_manager.set_api_response(func.__name__, result, **kwargs)
            
            return result
        
        return wrapper
    
    return decorator