"""
智能缓存管理器 - 提升性能，减少数据库访问

提供LRU缓存、TTL缓存等策略，减少重复计算和数据库查询
"""

import functools
import threading
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from dataclasses import dataclass
from collections import OrderedDict

T = TypeVar('T')


@dataclass
class CacheConfig:
    """缓存配置"""
    max_size: int = 128
    ttl_seconds: int = 300  # 5分钟
    

class LRUCache:
    """
    LRU缓存实现
    
    特性：
    - 固定大小，自动淘汰最近最少使用项
    - 可选TTL过期时间
    - 线程安全
    """
    
    def __init__(self, max_size: int = 128, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict = {}
        self._lock = threading.RLock()
        
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                return None
                
            # 检查TTL
            if self.ttl_seconds > 0:
                timestamp = self._timestamps[key]
                if time.time() - timestamp > self.ttl_seconds:
                    del self._cache[key]
                    del self._timestamps[key]
                    return None
            
            # 移到末尾（最近使用）
            value = self._cache[key]
            self._cache.move_to_end(key)
            return value
            
    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        with self._lock:
            # 如果键已存在，移动到末尾
            if key in self._cache:
                self._cache.move_to_end(key)
            
            # 添加新项
            self._cache[key] = value
            self._timestamps[key] = time.time()
            
            # 如果超过大小限制，删除最老的项
            while len(self._cache) > self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]
                
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            
    def cleanup_expired(self) -> int:
        """清理过期项，返回删除的数量"""
        if self.ttl_seconds <= 0:
            return 0
            
        count = 0
        current_time = time.time()
        expired_keys = []
        
        with self._lock:
            for key, timestamp in self._timestamps.items():
                if current_time - timestamp > self.ttl_seconds:
                    expired_keys.append(key)
                    
            count = len(expired_keys)
            for key in expired_keys:
                del self._cache[key]
                del self._timestamps[key]
                
        return count


def cached(ttl_seconds: int = 300, max_size: int = 128):
    """
    缓存装饰器
    
    Args:
        ttl_seconds: TTL时间（秒），0表示永不过期
        max_size: 最大缓存项数
    """
    cache = LRUCache(max_size=max_size, ttl_seconds=ttl_seconds)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # 生成缓存键
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = "|".join(key_parts)
            
            # 尝试从缓存获取
            result = cache.get(cache_key)
            if result is not None:
                return result
                
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
            
        # 添加缓存管理方法到包装器
        wrapper.cache_clear = cache.clear
        wrapper.cache_cleanup = cache.cleanup_expired
        wrapper.cache_info = lambda: f"LRUCache(max_size={max_size}, ttl={ttl_seconds}s)"
        
        return cast(Callable[..., T], wrapper)
    
    return decorator


# 全局缓存实例
search_cache = LRUCache(max_size=256, ttl_seconds=600)  # FTS查询缓存
vector_cache = LRUCache(max_size=128, ttl_seconds=900)  # 向量结果缓存


def clear_all_caches():
    """清空所有缓存"""
    search_cache.clear()
    vector_cache.clear()
    
    logger = __import__('logging').getLogger(__name__)
    logger.info("所有缓存已清空")


def get_cache_stats():
    """获取缓存统计信息"""
    return {
        "search_cache": {
            "size": len(search_cache._cache),
            "max_size": search_cache.max_size,
            "ttl": search_cache.ttl_seconds
        },
        "vector_cache": {
            "size": len(vector_cache._cache),
            "max_size": vector_cache.max_size,
            "ttl": vector_cache.ttl_seconds
        }
    }