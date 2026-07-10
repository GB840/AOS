# AOS v5.0 API 文档

## 📚 概述

AOS (Agent Operating System) v5.0 提供了一个统一的API接口，用于访问多个AI引擎和服务。该系统采用了先进的安全架构和性能优化设计。

### 🔗 基础信息

- **API基础URL**: `http://localhost:8000/api`
- **API版本**: v5.0
- **认证方式**: Bearer Token (RS256 JWT) + API Key (bcrypt哈希)
- **文档地址**: 
  - Swagger UI: `http://localhost:8000/docs` (仅开发环境)
  - ReDoc: `http://localhost:8000/redoc` (仅开发环境)

---

## 🔒 认证与授权

### 获取访问令牌

```http
POST /api/auth/token
Content-Type: application/json

{
  "username": "admin",
  "password": "your_password"
}
```

**响应**:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### API Key 认证

所有受保护的API端点需要在请求头中提供有效的API Key：

```http
GET /api/chat
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
X-API-Key: your_api_key
```

### 安全特性

- ✅ **强制HTTPS** (生产环境)
- ✅ **JWT RS256签名** (防离线伪造)
- ✅ **API Key bcrypt哈希验证**
- ✅ **速率限制** (100请求/15分钟/客户端)
- ✅ **CSP安全策略** (防XSS)
- ✅ **输入验证与消毒** (防注入攻击)
- ✅ **恒定时间比较** (防时序攻击)

---

## 💬 核心API端点

### 聊天接口

#### 1. 流式聊天 (SSE)

```http
POST /api/chat/stream
Content-Type: application/json
Authorization: Bearer {token}
X-API-Key: {api_key}

{
  "messages": [
    {
      "role": "user",
      "content": "你好，请帮我分析这个代码"
    }
  ],
  "model": "gpt-3.5-turbo",
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**流式响应** (text/event-stream):
```
data: {"id": "chat_123", "object": "chat.completion.chunk", "created": 1699596897, "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"content": "你好！"}, "finish_reason": null}]}

data: {"id": "chat_123", "object": "chat.completion.chunk", "created": 1699596897, "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"content": "我很乐意帮你分析代码。"}, "finish_reason": null}]}

data: {"id": "chat_123", "object": "chat.completion.chunk", "created": 1699596897, "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}

data: [DONE]
```

#### 2. 普通聊天

```http
POST /api/chat
Content-Type: application/json
Authorization: Bearer {token}
X-API-Key: {api_key}

{
  "messages": [
    {
      "role": "user",
      "content": "请解释Python的装饰器"
    }
  ],
  "model": "gpt-4"
}
```

**响应**:
```json
{
  "id": "chat_456",
  "object": "chat.completion",
  "created": 1699596897,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Python装饰器是一种特殊的函数，它可以修改或增强其他函数的行为..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 142,
    "total_tokens": 157
  }
}
```

### 🧠 记忆管理接口

#### 添加记忆

```http
POST /api/memory/conversation
Content-Type: application/json
Authorization: Bearer {token}
X-API-Key: {api_key}

{
  "user_id": "user_123",
  "conversation": [
    {"role": "user", "content": "我的名字是张三"},
    {"role": "assistant", "content": "你好张三！很高兴认识你。"}
  ],
  "metadata": {
    "topic": "自我介绍",
    "tags": ["personal", "greeting"]
  }
}
```

#### 搜索记忆

```http
GET /api/memory/search?q=张三&limit=10&user_id=user_123
Authorization: Bearer {token}
X-API-Key: {api_key}
```

**响应**:
```json
{
  "results": [
    {
      "id": "conv_789",
      "user_id": "user_123",
      "conversation": [...],
      "similarity": 0.95,
      "metadata": {...},
      "created_at": "2024-10-20T10:30:00Z"
    }
  ],
  "total": 1
}
```

#### 知识库管理

```http
POST /api/memory/knowledge
Content-Type: application/json
Authorization: Bearer {token}
X-API-Key: {api_key}

{
  "title": "Python基础教程",
  "content": "Python是一种解释型、高级、通用编程语言...",
  "tags": ["programming", "python", "tutorial"],
  "source": "official_docs"
}
```

### 🛠️ 技能系统接口

#### 列出可用技能

```http
GET /api/skills
Authorization: Bearer {token}
X-API-Key: {api_key}
```

**响应**:
```json
{
  "skills": [
    {
      "name": "codebase_memory",
      "description": "代码检索与分析",
      "category": "development",
      "parameters": {...},
      "enabled": true
    },
    {
      "name": "lightrag",
      "description": "文档检索与摘要",
      "category": "rag",
      "parameters": {...},
      "enabled": true
    }
  ]
}
```

#### 执行技能

```http
POST /api/skills/execute
Content-Type: application/json
Authorization: Bearer {token}
X-API-Key: {api_key}

{
  "skill": "codebase_memory",
  "parameters": {
    "query": "如何优化数据库查询",
    "file_types": [".py", ".sql"],
    "max_results": 5
  }
}
```

### 🌐 网关接口

#### 上游服务探测

```http
GET /api/gateway/probe
Authorization: Bearer {token}
X-API-Key: {api_key}
```

**响应**:
```json
{
  "upstreams": {
    "openclaw": {
      "status": "healthy",
      "response_time": 45,
      "endpoint": "http://localhost:18789"
    },
    "deerflow": {
      "status": "healthy", 
      "response_time": 23,
      "endpoint": "http://localhost:2026"
    },
    "web": {
      "status": "healthy",
      "response_time": 12,
      "endpoint": "http://localhost:8501"
    }
  }
}
```

#### 模型路由

```http
POST /api/gateway/route
Content-Type: application/json
Authorization: Bearer {token}
X-API-Key: {api_key}

{
  "task": "code_generation",
  "requirements": {
    "language": "python",
    "complexity": "medium",
    "performance_critical": true
  },
  "preferences": {
    "model_tier": "premium",
    "cost_limit": 0.05
  }
}
```

---

## 📊 管理接口

### 健康检查

```http
GET /health
```

**响应**:
```json
{
  "status": "healthy",
  "service": "aos-api",
  "version": "5.0.0",
  "timestamp": "2024-10-20T10:30:00Z",
  "uptime": 3600,
  "dependencies": {
    "database": "healthy",
    "memory_store": "healthy",
    "connection_pool": "healthy"
  }
}
```

### 系统指标

```http
GET /api/admin/metrics
Authorization: Bearer {token}
X-API-Key: {api_key}
```

**响应**:
```json
{
  "requests": {
    "total": 15420,
    "rate": 45.2,
    "errors": 12,
    "error_rate": 0.08
  },
  "performance": {
    "avg_response_time": 125,
    "p95_response_time": 280,
    "p99_response_time": 450
  },
  "resources": {
    "cpu_usage": 23.5,
    "memory_usage": 1024,
    "connection_pool": {
      "active": 15,
      "idle": 35,
      "total": 50
    }
  }
}
```

---

## 🔧 错误处理

### 错误响应格式

```json
{
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "需要有效的访问令牌",
    "details": "请提供有效的Authorization头",
    "timestamp": "2024-10-20T10:30:00Z"
  }
}
```

### 常见错误码

| 状态码 | 错误码 | 描述 |
|--------|--------|------|
| 400 | `INVALID_REQUEST` | 请求格式错误 |
| 401 | `AUTHENTICATION_REQUIRED` | 需要认证 |
| 403 | `INSUFFICIENT_PERMISSIONS` | 权限不足 |
| 429 | `RATE_LIMIT_EXCEEDED` | 请求频率超限 |
| 422 | `VALIDATION_ERROR` | 输入验证失败 |
| 500 | `INTERNAL_SERVER_ERROR` | 服务器内部错误 |

---

## 🚀 性能特性

### 优化措施

- ✅ **连接池管理** - 数据库连接复用，减少开销
- ✅ **LRU缓存** - 查询结果缓存，提高响应速度
- ✅ **异步处理** - 非阻塞I/O操作
- ✅ **批量操作** - 减少数据库往返
- ✅ **查询优化** - N+1查询问题解决
- ✅ **内存管理** - 及时清理过期数据

### SLA指标

- **响应时间**: P95 < 200ms
- **吞吐量**: > 1000 RPS
- **可用性**: 99.9%
- **并发连接**: 支持10000+

---

## 🔍 监控与调试

### 日志级别

- `DEBUG` - 详细调试信息
- `INFO` - 常规操作日志  
- `WARNING` - 潜在问题警告
- `ERROR` - 错误事件
- `CRITICAL` - 严重故障

### 可观测性

- **OpenTelemetry集成** - 分布式追踪
- **指标收集** - Prometheus格式
- **健康检查** - 多维度状态监控
- **审计日志** - 完整操作记录

---

## 📱 SDK与示例

### Python SDK

```python
from aos_sdk import AOSClient

# 初始化客户端
client = AOSClient(
    base_url="http://localhost:8000",
    api_key="your_api_key",
    auth_token="your_jwt_token"
)

# 发送聊天消息
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello!"}],
    model="gpt-3.5-turbo"
)

# 流式聊天
for chunk in client.chat.completions.create_stream(
    messages=[{"role": "user", "content": "Hello!"}],
    model="gpt-3.5-turbo"
):
    print(chunk.choices[0].delta.content)
```

### cURL 示例

```bash
# 获取访问令牌
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# 发送聊天请求
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## 🔄 版本历史

### v5.0.0 (当前)

- 🚀 全新的AOS Kernel架构
- 🔒 全面安全加固 (15项修复)
- ⚡ 连接池性能优化
- 🧠 增强记忆系统
- 📊 完整监控体系

### v4.0.0

- 初始版本发布
- 基础API功能
- 简单认证机制

---

## 📞 支持与反馈

- **GitHub Issues**: https://github.com/your-org/aos/issues
- **文档问题**: docs@aos.dev
- **技术支持**: support@aos.dev
- **安全报告**: security@aos.dev

---

*本API文档最后更新：2024年10月20日 | AOS v5.0*