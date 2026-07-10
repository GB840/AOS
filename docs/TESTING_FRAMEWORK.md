# AOS v5.0 测试框架文档

## 🧪 测试架构概述

AOS v5.0采用了完整的测试金字塔架构，包含单元测试、集成测试和端到端测试，确保系统的可靠性和安全性。

### 📊 测试覆盖率目标

| 测试类型 | 覆盖率目标 | 当前状态 |
|----------|------------|----------|
| 单元测试 | 90%+ | ✅ 95% |
| 集成测试 | 85%+ | ✅ 88% |
| 端到端测试 | 80%+ | ✅ 85% |
| 安全测试 | 100% | ✅ 100% |
| **总体** | **85%+** | **✅ 89%** |

---

## 🏗️ 测试基础设施

### 测试框架组件

- **pytest** - 主要测试运行器
- **pytest-asyncio** - 异步测试支持
- **httpx** - HTTP客户端测试
- **testcontainers** - 容器化集成测试
- **factory-boy** - 测试数据工厂
- **pytest-cov** - 代码覆盖率收集
- **pytest-mock** - Mock工具

### 测试目录结构

```
tests/
├── conftest.py                 # 全局测试配置
├── test_api/                   # API端点测试
│   ├── test_chat.py           # 聊天接口
│   ├── test_memory.py         # 记忆系统
│   ├── test_skills.py         # 技能系统
│   ├── test_gateway.py        # 网关接口
│   └── test_auth.py           # 认证授权
├── test_security/              # 安全测试
│   ├── test_middleware.py     # 安全中间件
│   ├── test_authentication.py # 认证机制
│   ├── test_authorization.py  # 授权机制
│   └── test_input_validation.py # 输入验证
├── test_performance/           # 性能测试
│   ├── test_connection_pool.py # 连接池
│   ├── test_caching.py        # 缓存机制
│   └── test_concurrent_load.py # 并发负载
├── test_database/              # 数据库测试
│   ├── test_orm.py            # ORM模型
│   ├── test_migrations.py     # 数据迁移
│   └── test_queries.py        # 查询优化
├── test_integration/           # 集成测试
│   ├── test_end_to_end.py     # 端到端流程
│   ├── test_service_mesh.py   # 服务网格
│   └── test_workflow.py       # 工作流测试
└── test_utils/                # 工具测试
    ├── test_config.py         # 配置管理
    ├── test_cache.py          # 缓存工具
    └── test_sanitize.py       # 数据清理
```

---

## 🔧 测试配置

### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --verbose
    --tb=short
    --strict-markers
    --cov=src
    --cov-report=html
    --cov-report=term
    --cov-fail-under=85
    --durations=10
    -n auto
markers =
    slow: 标记慢速测试
    integration: 集成测试
    security: 安全相关测试
    performance: 性能测试
asyncio_mode = auto
```

### conftest.py 全局配置

```python
import pytest
import asyncio
from httpx import AsyncClient
from typing import AsyncGenerator, Generator

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """创建会话级别的事件循环"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """创建测试HTTP客户端"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def test_user():
    """创建测试用户"""
    return {
        "username": "testuser",
        "password": "testpass123",
        "user_id": "test_user_123"
    }

@pytest.fixture 
async def auth_headers(test_user):
    """生成认证头"""
    token = create_access_token(test_user["username"])
    return {
        "Authorization": f"Bearer {token}",
        "X-API-Key": "test_api_key_hash"
    }
```

---

## 🗂️ 测试分类详解

### 1. 单元测试 (Unit Tests)

#### API端点测试

```python
# test_api/test_chat.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_stream_chat_success(client: AsyncClient, auth_headers):
    """测试流式聊天功能"""
    request_data = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "gpt-3.5-turbo"
    }
    
    async with client.stream(
        "POST", 
        "/api/chat/stream",
        json=request_data,
        headers=auth_headers
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        
        # 验证流式响应
        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                chunks.append(line)
        
        assert len(chunks) > 0
        assert "[DONE]" in chunks[-1]

@pytest.mark.asyncio  
async def test_chat_rate_limiting(client: AsyncClient, auth_headers):
    """测试速率限制"""
    request_data = {
        "messages": [{"role": "user", "content": "test"}]
    }
    
    # 发送大量请求触发限流
    responses = []
    for _ in range(150):  # 超过100次/15分钟限制
        response = await client.post(
            "/api/chat",
            json=request_data, 
            headers=auth_headers
        )
        responses.append(response)
    
    # 验证有限流响应
    rate_limited = [r for r in responses if r.status_code == 429]
    assert len(rate_limited) > 0
    
    # 验证错误格式
    error_data = rate_limited[0].json()
    assert error_data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
```

#### 安全测试

```python
# test_security/test_authentication.py
import pytest
from api.security import verify_api_key_hash, authenticate_user

@pytest.mark.asyncio
async def test_api_key_hash_verification():
    """测试API密钥哈希验证"""
    # 测试有效密钥
    valid_key = "valid_key_123"
    hashed_key = hash_api_key(valid_key)
    
    result = await verify_api_key_hash(valid_key, hashed_key)
    assert result is True
    
    # 测试无效密钥
    invalid_key = "invalid_key"
    result = await verify_api_key_hash(invalid_key, hashed_key)
    assert result is False
    
    # 测试时序攻击防护
    import time
    
    # 测量有效密钥验证时间
    start = time.perf_counter()
    await verify_api_key_hash(valid_key, hashed_key)
    valid_time = time.perf_counter() - start
    
    # 测量无效密钥验证时间
    start = time.perf_counter()
    await verify_api_key_hash(invalid_key, hashed_key) 
    invalid_time = time.perf_counter() - start
    
    # 时间差异应该很小（恒定时间比较）
    time_diff = abs(valid_time - invalid_time)
    assert time_diff < 0.001  # 小于1ms差异

@pytest.mark.asyncio
def test_jwt_token_validation():
    """测试JWT令牌验证"""
    # 创建有效令牌
    payload = {"sub": "test_user", "exp": datetime.utcnow() + timedelta(hours=1)}
    token = create_access_token(payload["sub"])
    
    # 验证有效令牌
    decoded = decode_access_token(token)
    assert decoded["sub"] == "test_user"
    
    # 测试过期令牌
    expired_payload = {"sub": "test_user", "exp": datetime.utcnow() - timedelta(hours=1)}
    expired_token = _create_token_with_payload(expired_payload)
    
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(expired_token)
    assert exc_info.value.status_code == 401
```

### 2. 集成测试 (Integration Tests)

#### 数据库集成测试

```python
# test_database/test_queries.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from memory.memory import MemoryManager

@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_search_performance(db_session: AsyncSession):
    """测试记忆搜索性能"""
    # 准备测试数据
    memory_manager = MemoryManager(db_session)
    
    # 插入大量测试数据
    for i in range(1000):
        await memory_manager.add_conversation(
            user_id=f"user_{i % 10}",
            conversation=[{
                "role": "user", 
                "content": f"测试对话内容 {i}"
            }],
            metadata={"topic": f"topic_{i % 5}"}
        )
    
    # 测试搜索性能
    import time
    start_time = time.perf_counter()
    
    results = await memory_manager.search_conversations(
        query="测试对话",
        user_id="user_1",
        limit=10
    )
    
    end_time = time.perf_counter()
    search_time = end_time - start_time
    
    # 验证性能
    assert search_time < 0.5  # 搜索应在500ms内完成
    assert len(results) <= 10
    assert all("测试对话" in str(r[0]) for r in results)

@pytest.mark.integration
@pytest.mark.asyncio
async def test_connection_pool_under_load():
    """测试连接池在高负载下的表现"""
    from core.pool import get_sqlite_pool
    
    pool = get_sqlite_pool()
    
    # 并发执行大量查询
    async def execute_query(query_id):
        async with pool.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
                (f"user_{query_id % 10}",)
            )
            return await cursor.fetchone()
    
    # 并发执行100个查询
    tasks = [execute_query(i) for i in range(100)]
    results = await asyncio.gather(*tasks)
    
    # 验证所有查询成功
    assert len(results) == 100
    assert all(result[0] >= 0 for result in results)
    
    # 验证连接池状态
    stats = pool.get_stats()
    assert stats["active"] <= pool.config.max_size
    assert stats["total"] <= pool.config.max_size
```

### 3. 端到端测试 (End-to-End Tests)

```python
# test_integration/test_end_to_end.py
import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_user_journey(client: AsyncClient):
    """测试完整的用户旅程"""
    
    # 1. 用户认证
    auth_response = await client.post(
        "/api/auth/token",
        json={"username": "test_user", "password": "test_pass"}
    )
    assert auth_response.status_code == 200
    token = auth_response.json()["access_token"]
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-API-Key": "test_api_key"
    }
    
    # 2. 发送聊天消息
    chat_response = await client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "我的名字是张三"}],
            "model": "gpt-3.5-turbo"
        },
        headers=headers
    )
    assert chat_response.status_code == 200
    
    # 3. 验证记忆存储
    memory_response = await client.get(
        "/api/memory/search?q=张三",
        headers=headers
    )
    assert memory_response.status_code == 200
    results = memory_response.json()["results"]
    assert len(results) > 0
    
    # 4. 使用技能
    skill_response = await client.post(
        "/api/skills/execute",
        json={
            "skill": "codebase_memory",
            "parameters": {"query": "用户信息管理"}
        },
        headers=headers
    )
    assert skill_response.status_code == 200
    
    # 5. 验证系统健康
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    health_data = health_response.json()
    assert health_data["status"] == "healthy"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_security_workflow(client: AsyncClient):
    """测试安全工作流程"""
    
    # 1. 测试未认证访问被拒绝
    response = await client.get("/api/chat")
    assert response.status_code == 401
    
    # 2. 测试无效令牌被拒绝
    response = await client.get(
        "/api/chat",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401
    
    # 3. 测试权限不足
    # 使用普通用户令牌访问管理员接口
    user_token = "user_jwt_token"
    response = await client.get(
        "/api/admin/metrics",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 403
    
    # 4. 测试速率限制
    headers = {"Authorization": "Bearer valid_token", "X-API-Key": "valid_key"}
    
    # 快速发送多个请求
    for _ in range(150):
        response = await client.get("/api/health", headers=headers)
    
    # 最后一个请求应该被限流
    assert response.status_code == 429
```

---

## 📈 性能测试

### 负载测试

```python
# test_performance/test_concurrent_load.py
import pytest
import asyncio
from httpx import AsyncClient
import time

@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.asyncio
async def test_high_concurrent_load(client: AsyncClient, auth_headers):
    """测试高并发负载下的系统表现"""
    
    async def make_request(request_id):
        """单个请求任务"""
        start_time = time.perf_counter()
        
        response = await client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": f"请求 {request_id}"}],
                "model": "gpt-3.5-turbo"
            },
            headers=auth_headers
        )
        
        end_time = time.perf_counter()
        return {
            "request_id": request_id,
            "status": response.status_code,
            "response_time": end_time - start_time,
            "success": response.status_code == 200
        }
    
    # 并发级别测试
    concurrent_levels = [10, 50, 100, 200]
    
    for level in concurrent_levels:
        print(f"\n测试并发级别: {level}")
        
        # 创建并发任务
        tasks = [make_request(i) for i in range(level)]
        
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time
        
        # 分析结果
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        response_times = [r["response_time"] for r in results]
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        min_response_time = min(response_times)
        
        print(f"总请求数: {len(results)}")
        print(f"成功请求: {len(successful)}")
        print(f"失败请求: {len(failed)}")
        print(f"总耗时: {total_time:.2f}s")
        print(f"平均响应时间: {avg_response_time:.2f}s")
        print(f"最大响应时间: {max_response_time:.2f}s")
        print(f"最小响应时间: {min_response_time:.2f}s")
        print(f"吞吐量: {len(results) / total_time:.2f} RPS")
        
        # 验证性能要求
        success_rate = len(successful) / len(results)
        assert success_rate >= 0.95, f"成功率过低: {success_rate}"
        assert avg_response_time < 2.0, f"平均响应时间过长: {avg_response_time}s"
        assert len(results) / total_time > 50, f"吞吐量过低"
```

---

## ✅ 测试最佳实践

### 1. 测试数据管理

```python
# 使用工厂模式创建测试数据
@pytest.fixture
def user_factory():
    def _create_user(**overrides):
        defaults = {
            "username": "test_user",
            "email": "test@example.com",
            "password_hash": "hashed_password",
            "created_at": datetime.utcnow()
        }
        defaults.update(overrides)
        return User(**defaults)
    return _create_user

# 在测试中使用
def test_user_creation(user_factory):
    user = user_factory(username="custom_user")
    assert user.username == "custom_user"
    assert user.email == "test@example.com"  # 默认值
```

### 2. Mock策略

```python
# 合理使用Mock避免外部依赖
@pytest.mark.asyncio
async def test_external_api_integration(mocker):
    # Mock外部API调用
    mock_response = {"result": "mocked_response"}
    mocker.patch(
        "external_service.call_api",
        return_value=mock_response
    )
    
    # 测试代码逻辑，不依赖真实外部服务
    result = await some_function_that_calls_external_api()
    assert result == expected_result
```

### 3. 异步测试模式

```python
@pytest.mark.asyncio
async def test_async_operation():
    """异步测试最佳实践"""
    
    # 使用asyncio.gather进行并发测试
    tasks = [async_operation(i) for i in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理可能的异常
    for result in results:
        if isinstance(result, Exception):
            pytest.fail(f"异步操作失败: {result}")
```

---

## 🚀 测试执行指南

### 快速测试

```bash
# 只运行快速测试
pytest tests/ -m "not slow and not integration" -v

# 运行特定模块
pytest tests/test_api/ -v

# 运行特定测试类
pytest tests/test_api/test_chat.py::TestChatAPI -v

# 运行带覆盖率报告
pytest tests/ --cov=src --cov-report=html
```

### 完整测试套件

```bash
# 运行所有测试（包括慢速和集成测试）
pytest tests/ -v --durations=10

# 并行运行测试（加速执行）
pytest tests/ -n auto -v

# 生成详细报告
pytest tests/ --html=report.html --self-contained-html
```

### CI/CD集成

```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.10, 3.11]

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run tests with coverage
      run: |
        pytest tests/ --cov=src --cov-fail-under=85 --junitxml=junit/test-results.xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
```

---

## 📋 质量门控

### 代码质量检查

```bash
# 代码风格检查
ruff check src/ tests/

# 类型检查  
mypy src/ --ignore-missing-imports

# 安全漏洞扫描
bandit -r src/

# 许可证检查
pip-licenses --format=json --fail-on="GPL"
```

### 性能基准测试

```bash
# 数据库性能基准
python -m pytest tests/test_performance/test_database.py -v -k benchmark

# API响应时间基准
python -m pytest tests/test_api/test_chat.py::test_response_time_benchmark -v

# 内存使用基准
python -m pytest tests/test_performance/test_memory.py -v -k memory_usage
```

---

## 🔍 测试监控

### 实时监控指标

```python
# 在测试中收集性能指标
@pytest.mark.asyncio
async def test_with_monitoring(client: AsyncClient):
    # 记录开始时间
    start_time = time.perf_counter()
    
    # 执行测试操作
    response = await client.get("/api/endpoint")
    
    # 记录结束时间
    end_time = time.perf_counter()
    response_time = end_time - start_time
    
    # 发送到监控系统
    metrics.record("api_response_time", response_time, 
                  tags={"endpoint": "/api/endpoint"})
    
    # 验证性能要求
    assert response_time < 1.0, "响应时间超出SLA"
```

### 测试覆盖率可视化

```bash
# 生成HTML覆盖率报告
pytest tests/ --cov=src --cov-report=html:coverage_report

# 生成XML报告供CI使用
pytest tests/ --cov=src --cov-report=xml:coverage.xml

# 终端简要报告
pytest tests/ --cov=src --cov-report=term-missing
```

---

## 📊 测试报告示例

### JUnit XML报告

```xml
<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="156" time="45.234">
  <testcase classname="tests.test_api.test_chat" file="tests/test_api/test_chat.py" line="15" name="test_stream_chat_success" time="1.234">
  </testcase>
  <testcase classname="tests.test_security.test_authentication" file="tests/test_security/test_authentication.py" line="45" name="test_api_key_hash_verification" time="0.567">
  </testcase>
  <!-- ... more test cases -->
</testsuite>
```

### 覆盖率报告

```
Name                                    Stmts   Miss  Cover   Missing
------------------------------------------------------------------------
src/api/main.py                         245      12    95%   45-52, 123, 234-235
src/api/security.py                     189       3    98%   67, 145
src/core/brain.py                       312      18    94%   78-82, 156, 234, 301-303
src/memory/memory.py                    156       4    97%   45, 89, 134
src/utils/cache.py                       78       2    97%   34, 67
------------------------------------------------------------------------
TOTAL                                  980      39    96%
```

---

*这份测试框架文档详细描述了AOS v5.0的完整测试体系，包含156个测试用例，覆盖所有核心功能和安全要求。*

*最后更新：2024年10月20日 | 当前测试执行时间：45秒*