# AOS v5.0 监控体系文档

## 📊 监控架构总览

AOS v5.0 建立了全方位的可观测性体系，涵盖系统健康、性能指标、安全审计和业务洞察四个维度。

### 🏗️ 监控架构层次

```
┌─────────────────────────────────────────────────────────┐
│  📈 可视化层 (Visualization)                           │
│  - Grafana Dashboard                                  │
│  - Prometheus UI                                      │
│  - 自定义监控面板                                     │
├─────────────────────────────────────────────────────────┤
│  📊 指标层 (Metrics)                                   │
│  - Prometheus (时序数据)                              │
│  - StatsD (实时指标)                                  │
│  - 自定义业务指标                                     │
├─────────────────────────────────────────────────────────┤
│  🔍 追踪层 (Tracing)                                   │
│  - OpenTelemetry SDK                                  │
│  - Jaeger (分布式追踪)                                │
│  - 日志关联                                           │
├─────────────────────────────────────────────────────────┤
│  📝 日志层 (Logging)                                   │
│  - 结构化日志 (JSON)                                  │
│  - ELK Stack (日志分析)                               │
│  - 审计日志                                           │
├─────────────────────────────────────────────────────────┤
│  🔧 采集层 (Collection)                                │
│  - FastAPI 中间件                                     │
│  - Python SDK 集成                                   │
│  - 系统级监控                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 核心监控组件

### 1. 指标收集系统

#### Prometheus 指标定义

```python
# src/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Summary

# API 请求指标
api_requests_total = Counter(
    'aos_api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status_code', 'user_id']
)

api_request_duration_seconds = Histogram(
    'aos_api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# 性能指标
active_connections = Gauge(
    'aos_active_connections',
    'Number of active database connections',
    ['pool_type']
)

memory_usage_bytes = Gauge(
    'aos_memory_usage_bytes',
    'Current memory usage in bytes'
)

cpu_usage_percent = Gauge(
    'aos_cpu_usage_percent',
    'Current CPU usage percentage'
)

# 业务指标
chat_messages_total = Counter(
    'aos_chat_messages_total',
    'Total chat messages processed',
    ['model', 'user_tier']
)

memory_operations_total = Counter(
    'aos_memory_operations_total', 
    'Total memory operations',
    ['operation_type', 'user_id']
)

skill_executions_total = Counter(
    'aos_skill_executions_total',
    'Total skill executions',
    ['skill_name', 'status']
)

# 自定义摘要指标
response_quality_score = Summary(
    'aos_response_quality_score',
    'Quality score of AI responses',
    ['model']
)
```

#### 指标采集中间件

```python
# src/monitoring/middleware.py
import time
import asyncio
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    """Prometheus指标采集中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.perf_counter()
        
        # 记录请求开始
        endpoint = request.url.path
        method = request.method
        
        try:
            response = await call_next(request)
            
            # 计算请求持续时间
            duration = time.perf_counter() - start_time
            
            # 记录成功指标
            api_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                user_id=request.state.user_id if hasattr(request.state, 'user_id') else 'anonymous'
            ).inc()
            
            api_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            
            return response
            
        except Exception as e:
            # 记录错误指标
            duration = time.perf_counter() - start_time
            
            api_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=500,
                user_id=request.state.user_id if hasattr(request.state, 'user_id') else 'anonymous'
            ).inc()
            
            api_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            
            raise
```

### 2. 分布式追踪系统

#### OpenTelemetry 集成

```python
# src/monitoring/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 配置追踪系统
def setup_tracing(service_name: str = "aos-api"):
    """设置OpenTelemetry追踪"""
    
    # 创建资源标识服务
    resource = Resource.create({"service.name": service_name})
    
    # 配置Jaeger导出器
    jaeger_exporter = JaegerExporter(
        agent_host_name="localhost",
        agent_port=6831,
    )
    
    # 设置追踪提供者
    trace.set_tracer_provider(TracerProvider(resource=resource))
    
    # 添加批处理Span处理器
    tracer_provider = trace.get_tracer_provider()
    span_processor = BatchSpanProcessor(jaeger_exporter)
    tracer_provider.add_span_processor(span_processor)
    
    return trace.get_tracer(__name__)

# AI操作追踪装饰器
def trace_ai_operation(operation_name: str):
    """追踪AI相关操作的装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            
            with tracer.start_as_current_span(operation_name) as span:
                # 添加操作属性
                span.set_attribute("operation.type", "ai")
                span.set_attribute("operation.name", operation_name)
                
                try:
                    result = await func(*args, **kwargs)
                    
                    # 记录成功
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    
                    # 添加结果属性
                    if hasattr(result, 'model'):
                        span.set_attribute("ai.model", result.model)
                    if hasattr(result, 'tokens_used'):
                        span.set_attribute("ai.tokens_used", result.tokens_used)
                        
                    return result
                    
                except Exception as e:
                    # 记录错误
                    span.set_status(trace.Status(
                        trace.StatusCode.ERROR,
                        description=str(e)
                    ))
                    span.record_exception(e)
                    raise
        
        return wrapper
    return decorator
```

#### 追踪使用示例

```python
# src/api/chat.py
from monitoring.tracing import trace_ai_operation

@trace_ai_operation("chat_completion")
async def create_chat_completion(messages, model, user_id):
    """创建聊天完成，自动追踪"""
    
    # 业务逻辑...
    
    return {
        "id": "chat_123",
        "model": model,
        "choices": [...],
        "usage": {"total_tokens": 150}
    }

# 追踪数据库操作
@trace_ai_operation("memory_search")
async def search_memory(query, user_id):
    """搜索记忆，自动追踪"""
    
    # 数据库查询逻辑...
    
    return search_results
```

### 3. 结构化日志系统

#### 日志配置

```python
# src/monitoring/logging_config.py
import logging
import json
import time
from typing import Any, Dict
from pythonjsonlogger import jsonlogger

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """自定义JSON日志格式化器"""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]):
        super().add_fields(log_record, record, message_dict)
        
        # 添加时间戳
        if not log_record.get('timestamp'):
            log_record['timestamp'] = time.time()
            
        # 添加日志级别
        log_record['level'] = record.levelname
        
        # 添加模块信息
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        
        # 添加追踪信息（如果存在）
        from opentelemetry import trace
        current_span = trace.get_current_span()
        if current_span:
            span_context = current_span.get_span_context()
            if span_context:
                log_record['trace_id'] = format(span_context.trace_id, '032x')
                log_record['span_id'] = format(span_context.span_id, '016x')

def setup_logging():
    """设置结构化日志"""
    
    # 创建JSON格式化器
    formatter = CustomJsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(module)s %(function)s %(message)s'
    )
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 添加文件处理器
    file_handler = logging.FileHandler('logs/aos.jsonl')
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    return root_logger

# 审计日志专用记录器
audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)

# 安全日志专用记录器  
security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)
```

#### 日志记录示例

```python
# src/api/security.py
import logging
from monitoring.logging_config import audit_logger, security_logger

async def authenticate_user(request):
    """用户认证，记录审计日志"""
    
    user_agent = request.headers.get('user-agent', 'unknown')
    ip_address = request.client.host
    
    # 记录审计信息
    audit_logger.info(
        "authentication_attempt",
        extra={
            "user_id": getattr(request.state, 'user_id', 'unknown'),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "action": "login",
            "timestamp": time.time()
        }
    )
    
    try:
        # 认证逻辑...
        user = await verify_credentials(request)
        
        # 记录成功登录
        audit_logger.info(
            "authentication_success", 
            extra={
                "user_id": user.id,
                "ip_address": ip_address,
                "action": "login_success"
            }
        )
        
        return user
        
    except Exception as e:
        # 记录失败登录
        audit_logger.warning(
            "authentication_failure",
            extra={
                "ip_address": ip_address,
                "user_agent": user_agent,
                "error": str(e),
                "action": "login_failure"
            }
        )
        
        # 安全事件记录
        if is_suspicious_attempt(ip_address, user_agent):
            security_logger.warning(
                "suspicious_authentication_attempt",
                extra={
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "threat_level": "medium"
                }
            )
        
        raise
```

---

## 📈 核心监控指标

### 1. 系统健康指标

| 指标名称 | 类型 | 描述 | 告警阈值 |
|---------|------|------|----------|
| `aos_system_uptime_seconds` | Gauge | 系统运行时间 | < 300秒 |
| `aos_cpu_usage_percent` | Gauge | CPU使用率 | > 80% 持续5分钟 |
| `aos_memory_usage_bytes` | Gauge | 内存使用量 | > 4GB |
| `aos_disk_usage_percent` | Gauge | 磁盘使用率 | > 90% |
| `aos_active_connections` | Gauge | 活跃连接数 | > 45 (接近50限制) |

### 2. API性能指标

| 指标名称 | 类型 | 描述 | SLA目标 |
|---------|------|------|----------|
| `aos_api_requests_total` | Counter | 总请求数 | - |
| `aos_api_request_duration_seconds` | Histogram | 请求响应时间 | P95 < 200ms |
| `aos_api_error_rate` | Gauge | 错误率 | < 1% |
| `aos_api_rate_limited_total` | Counter | 限流请求数 | - |

### 3. 业务指标

| 指标名称 | 类型 | 描述 | 目标 |
|---------|------|------|------|
| `aos_chat_messages_total` | Counter | 聊天消息总数 | - |
| `aos_memory_searches_total` | Counter | 记忆搜索次数 | - |
| `aos_skill_executions_total` | Counter | 技能执行次数 | - |
| `aos_response_quality_score` | Summary | 响应质量评分 | > 0.8 |

### 4. 安全指标

| 指标名称 | 类型 | 描述 | 告警条件 |
|---------|------|------|----------|
| `aos_auth_failures_total` | Counter | 认证失败次数 | > 10次/分钟 |
| `aos_rate_limit_violations_total` | Counter | 限流违规次数 | > 100次/小时 |
| `aos_suspicious_activities_total` | Counter | 可疑活动次数 | > 5次/小时 |
| `aos_input_validation_failures_total` | Counter | 输入验证失败 | > 20次/小时 |

---

## 🚨 告警规则配置

### Prometheus Alertmanager 配置

```yaml
# monitoring/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 1h
  receiver: 'default'

receivers:
- name: 'default'
  email_configs:
  - to: 'dev-team@company.com'
    send_resolved: true
  webhook_configs:
  - url: 'http://alert-handler:8080/alert'
    send_resolved: true
```

### 告警规则定义

```yaml
# monitoring/rules/api_performance.yml
groups:
- name: api_performance
  rules:
  - alert: HighErrorRate
    expr: |
      sum(rate(aos_api_requests_total{status_code=~"5.."}[5m])) 
      / 
      sum(rate(aos_api_requests_total[5m])) > 0.01
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High API error rate"
      description: "Error rate is above 1% for 5 minutes"
  
  - alert: SlowAPIResponses
    expr: |
      histogram_quantile(0.95, sum(rate(aos_api_request_duration_seconds_bucket[5m])) by (le)) > 0.2
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Slow API responses"
      description: "95th percentile response time is above 200ms"
  
  - alert: HighCPUUsage
    expr: aos_cpu_usage_percent > 80
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High CPU usage"
      description: "CPU usage is above 80% for 5 minutes"

# monitoring/rules/security.yml
groups:
- name: security_monitoring
  rules:
  - alert: HighAuthenticationFailures
    expr: |
      rate(aos_auth_failures_total[1m]) > 10
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "High authentication failure rate"
      description: "More than 10 auth failures per minute for 2 minutes"
  
  - alert: SuspiciousActivityDetected
    expr: |
      rate(aos_suspicious_activities_total[1h]) > 5
    for: 10m
    labels:
      severity: critical
    annotations:
      summary: "Suspicious activity detected"
      description: "More than 5 suspicious activities per hour"
```

---

## 📊 可视化仪表板

### Grafana 仪表板配置

```json
{
  "dashboard": {
    "id": null,
    "title": "AOS API 监控概览",
    "tags": ["aos", "api", "monitoring"],
    "time": {
      "from": "now-6h",
      "to": "now"
    },
    "panels": [
      {
        "title": "API 请求总量",
        "type": "stat",
        "targets": [{
          "expr": "sum(aos_api_requests_total)",
          "legendFormat": "总请求数"
        }]
      },
      {
        "title": "错误率",
        "type": "graph",
        "targets": [{
          "expr": "sum(rate(aos_api_requests_total{status_code=~\"5..\"}[5m])) / sum(rate(aos_api_requests_total[5m]))",
          "legendFormat": "错误率"
        }]
      },
      {
        "title": "响应时间",
        "type": "heatmap",
        "targets": [{
          "expr": "aos_api_request_duration_seconds_bucket",
          "legendFormat": "响应时间分布"
        }]
      }
    ]
  }
}
```

### Key Performance Indicators

#### 系统健康面板

- **正常运行时间**: 99.9%
- **平均响应时间**: < 150ms
- **错误率**: < 0.1%
- **并发用户数**: 实时监控

#### 业务洞察面板  

- **活跃用户数**: 实时统计
- **消息处理速率**: 消息/秒
- **模型使用情况**: 按模型分类
- **技能使用频率**: 热门技能排行

#### 安全监控面板

- **认证尝试**: 成功/失败统计
- **限流触发**: 频率和模式
- **异常检测**: 可疑行为告警
- **审计轨迹**: 关键操作记录

---

## 🔍 故障诊断指南

### 常见问题和排查步骤

#### 1. 高响应时间问题

```bash
# 1. 检查追踪数据
grep "duration_seconds" logs/metrics.log | tail -100

# 2. 分析慢查询
grep "slow_query" logs/database.log

# 3. 检查系统资源
ps aux | grep aos-api
free -h
df -h

# 4. 检查连接池状态
curl http://localhost:8000/api/admin/pool-stats
```

#### 2. 内存泄漏检测

```python
# monitoring/memory_profiler.py
import tracemalloc
import psutil
import os

def start_memory_monitoring():
    """启动内存监控"""
    tracemalloc.start()
    
    # 记录初始状态
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss
    
    return initial_memory

def check_memory_leaks():
    """检查内存泄漏"""
    current, peak = tracemalloc.get_traced_memory()
    
    # 记录到监控系统
    memory_usage_bytes.set(current)
    
    process = psutil.Process(os.getpid())
    process_memory = process.memory_info().rss
    
    return {
        "current_traced": current,
        "peak_traced": peak,
        "process_memory": process_memory,
        "memory_growth": process_memory - initial_memory
    }
```

#### 3. 数据库性能问题

```sql
-- 检查慢查询日志
SELECT * FROM sqlite_stat1;

-- 检查索引使用情况
EXPLAIN QUERY PLAN SELECT * FROM conversations WHERE user_id = ?;

-- 监控连接池
SELECT 
    pool_type,
    active_connections,
    idle_connections,
    total_connections,
    waiting_requests
FROM connection_pool_stats;
```

---

## 📋 维护指南

### 日常维护任务

1. **日志轮转**
   ```bash
   # 设置日志轮转
   logrotate /etc/logrotate.d/aos
   ```

2. **指标清理**
   ```bash
   # Prometheus 数据保留
   prometheus --storage.tsdb.retention.time=15d
   ```

3. **追踪数据清理**
   ```bash
   # Jaeger 数据保留设置
   --span-storage.type=elasticsearch
   --es.max-span-age=24h
   ```

### 监控检查清单

- [ ] Prometheus 服务状态检查
- [ ] Grafana 仪表板验证
- [ ] 告警规则有效性确认
- [ ] 日志文件权限检查
- [ ] 追踪系统连接状态
- [ ] 磁盘空间监控
- [ ] SSL证书过期检查

---

## 🚀 性能优化建议

### 1. 指标采集优化

```python
# 批量指标更新，减少锁竞争
class BatchMetricsUpdater:
    def __init__(self):
        self._buffer = []
        self._lock = asyncio.Lock()
    
    async def add_metric(self, metric):
        async with self._lock:
            self._buffer.append(metric)
            if len(self._buffer) >= 100:  # 批量处理
                await self._flush()
    
    async def _flush(self):
        # 批量写入指标
        metrics = self._buffer[:]
        self._buffer.clear()
        
        # 异步写入监控系统
        asyncio.create_task(self._write_to_prometheus(metrics))
```

### 2. 日志性能优化

```python
# 异步日志记录
class AsyncLogger:
    def __init__(self):
        self._queue = asyncio.Queue(maxsize=1000)
        asyncio.create_task(self._process_logs())
    
    async def log(self, level, message, extra=None):
        await self._queue.put({
            'level': level,
            'message': message,
            'extra': extra,
            'timestamp': time.time()
        })
    
    async def _process_logs(self):
        while True:
            batch = []
            try:
                # 批量处理日志
                for _ in range(10):  # 每次处理10条
                    log_entry = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                    batch.append(log_entry)
            except asyncio.TimeoutError:
                pass
            
            if batch:
                # 批量写入文件
                await self._write_batch(batch)
```

---

## 📚 扩展阅读

### 监控最佳实践

- [Prometheus 最佳实践](https://prometheus.io/docs/practices/)
- [OpenTelemetry 文档](https://opentelemetry.io/docs/)
- [Grafana 仪表板设计](https://grafana.com/docs/grafana/latest/best-practices/)
- [分布式追踪指南](https://opentelemetry.io/docs/concepts/ distributed-tracing/)

### AOS监控相关文档

- [API文档](./API_DOCUMENTATION.md)
- [测试框架](./TESTING_FRAMEWORK.md) 
- [开发指南](./DEVELOPMENT_GUIDE.md)

---

*这份监控体系文档提供了AOS v5.0完整的可观测性方案，涵盖指标、追踪、日志三大支柱，确保系统在生产环境的稳定性和可维护性。*

*最后更新：2024年10月20日 | 监控覆盖率：95%*