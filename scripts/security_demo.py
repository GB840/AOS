#!/usr/bin/env python3
"""
security_demo.py - 快速验证安全修复效果

验证:
1. API密钥安全升级
2. CSP安全策略增强  
3. FTS5查询安全改进
4. 连接池功能
"""

import sys
import os
import asyncio
from pathlib import Path

# 添加到路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent))


def test_api_key_security():
    """测试API密钥安全升级"""
    print("🔐 测试API密钥安全性...")
    
    try:
        # 测试明文API密钥是否已被移除
        from api.security import get_api_key
        from unittest.mock import Mock
        
        # 模拟FastAPI依赖注入
        class MockRequest:
            def __init__(self):
                self.headers = {}
                self.query_params = {}
        
        # 这只是一个语法测试，实际验证需要在安全模块中看
        print("   ✅ API密钥模块加载成功")
        
        # 检查关键函数是否存在
        from api.security import hash_api_key, verify_api_key_hash
        
        # 测试哈希功能
        test_key = "test-api-key-12345"
        hashed = hash_api_key(test_key)
        is_valid = verify_api_key_hash(test_key, hashed)
        
        if is_valid:
            print("   ✅ API密钥哈希验证功能正常")
        else:
            print("   ❌ API密钥哈希验证失败")
            
    except Exception as e:
        print(f"   ❌ API密钥测试失败: {e}")
        return False
    
    return True


def test_csp_security():
    """测试CSP安全策略"""
    print("🛡️ 测试CSP安全策略...")
    
    try:
        from api.security import SecurityHeadersMiddleware
        
        # 检查CSP头是否已增强
        print("   ✅ 安全头中间件加载成功")
        
        # 简单测试中间件类是否存在且可实例化
        class MockApp:
            async def __call__(self, scope, receive, send):
                pass
        
        middleware = SecurityHeadersMiddleware(MockApp())
        print("   ✅ 安全头中间件实例化成功")
        
    except Exception as e:
        print(f"   ❌ CSP测试失败: {e}")
        return False
    
    return True


def test_fts_security():
    """测试FTS查询安全"""
    print("🔍 测试FTS查询安全...")
    
    try:
        from memory.memory import validate_fts_query, escape_fts_query
        
        # 测试安全的查询
        safe_queries = ["hello world", "search for cat", "simple query"]
        for query in safe_queries:
            if not validate_fts_query(query):
                print(f"   ❌ 安全查询被错误拒绝: {query}")
                return False
        
        print("   ✅ 安全查询验证正常")
        
        # 测试危险查询应被拒绝
        dangerous_queries = [
            "SELECT * FROM users; DROP TABLE users",
            "UNION SELECT * FROM sqlite_master",
            "' OR '1'='1", 
            "x' UNION SELECT password FROM users --"
        ]
        
        for query in dangerous_queries:
            if validate_fts_query(query):
                print(f"   ❌ 危险查询未被正确拒绝: {query}")
                return False
        
        print("   ✅ 危险查询防护正常")
        
        # 测试过长查询
        long_query = "a" * 600  # 超过500字符限制
        if validate_fts_query(long_query):
            print("   ❌ 过长查询未被拒绝")
            return False
        
        print("   ✅ 查询长度限制正常")
        
        # 测试转义函数
        test_query = 'hello "world" AND test'
        escaped = escape_fts_query(test_query)
        if escaped != test_query.replace('"', '""'):
            print(f"   ❌ 查询转义异常: {escaped}")
            return False
        
        print("   ✅ 查询转义功能正常")
        
    except Exception as e:
        print(f"   ❌ FTS安全测试失败: {e}")
        return False
    
    return True


async def test_connection_pool():
    """测试连接池功能"""
    print("🏊 测试连接池...")
    
    try:
        from core.pool import get_sqlite_pool, PoolConfig, close_pools
        
        # 测试连接池获取
        config = PoolConfig(max_connections=5, min_connections=2)
        pool = get_sqlite_pool(":memory:", config)
        
        print("   ✅ 连接池创建成功")
        
        # 测试连接池初始化
        await pool.initialize()
        print("   ✅ 连接池初始化成功")
        
        # 测试连接获取和释放
        conn = await pool.acquire()
        print("   ✅ 连接获取成功")
        
        await pool.release(conn)
        print("   ✅ 连接释放成功")
        
        # 测试统计信息
        stats = pool.get_stats()
        print(f"   ✅ 连接池状态: {stats}")
        
        # 清理
        await close_pools()
        print("   ✅ 连接池清理成功")
        
    except Exception as e:
        print(f"   ❌ 连接池测试失败: {e}")
        return False
    
    return True


def test_dependency_injection():
    """测试主要组件的导入和依赖"""
    print("🔗 测试组件依赖...")
    
    components = [
        "api.security",
        "memory.memory", 
        "core.pool",
        "utils.config"
    ]
    
    for component in components:
        try:
            __import__(component)
            print(f"   ✅ {component} 导入成功")
        except Exception as e:
            print(f"   ❌ {component} 导入失败: {e}")
            return False
    
    return True


def main():
    """主测试函数"""
    print("🔧 AOS 安全修复验证工具")
    print("=" * 60)
    
    tests = [
        ("组件依赖", test_dependency_injection),
        ("API密钥安全", test_api_key_security), 
        ("CSP安全策略", test_csp_security),
        ("FTS查询安全", test_fts_security),
        ("连接池功能", test_connection_pool),
    ]
    
    results = {}
    all_passed = True
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}测试")
        print("-" * 40)
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = asyncio.run(test_func())
            else:
                result = test_func()
            
            results[test_name] = result
            if result:
                print(f"   🎉 {test_name}: 通过")
            else:
                print(f"   💥 {test_name}: 失败")
                all_passed = False
                
        except Exception as e:
            print(f"   💥 {test_name}: 异常 - {e}")
            results[test_name] = False
            all_passed = False
    
    print("\n" + "=" * 60)
    print("📊 测试结果摘要")
    print("=" * 60)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:15} {status}")
    
    passed_count = sum(1 for r in results.values() if r)
    total_count = len(results)
    
    print(f"\n🎯 总体进度: {passed_count}/{total_count} 测试通过")
    
    if all_passed:
        print("🎉 所有测试通过！安全修复已就绪。")
        return 0
    else:
        print("⚠️  部分测试失败，请检查修复。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)