# AOS 代码审查报告

**目标目录**: `D:\AOS\src\kernel`
**审查时间**: 2026-07-11 23:49:54
**使用模型**: deeproute:gpt-4o-mini
**耗时**: 62.08s

## 概览

| 指标 | 数值 |
|------|------|
| 扫描文件 | 31 |
| 已审查 | 31 |
| **总问题数** | **14** |
| 严重 (Critical) | 1 |
| 高危 (High) | 0 |
| 中危 (Medium) | 0 |
| 低危 (Low) | 13 |

## 有问题的文件 (6)

### D:\AOS\src\kernel\wiring.py
**评分**: 65/100 | **问题数**: 7
**总结**: 静态分析发现 7 个潜在问题

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第37行)

- **类别**: style
- **描述**: 第37行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] 跳过 OSS 适配器 {spec}: {e}")
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第58行)

- **类别**: style
- **描述**: 第58行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] mistralrs 网关跳过: {e}")
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第62行)

- **类别**: style
- **描述**: 第62行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] litellm 网关登记失败: {e}")
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第71行)

- **类别**: style
- **描述**: 第71行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] 模型网关组合失败: {e}")
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第78行)

- **类别**: style
- **描述**: 第78行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] litellm 运行时登记失败: {e}")
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第87行)

- **类别**: style
- **描述**: 第87行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] {engine} 运行时登记失败: {e}")
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第93行)

- **类别**: style
- **描述**: 第93行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(f"[wiring] 技能总线登记失败: {e}")
```

### D:\AOS\src\kernel\events.py
**评分**: 85/100 | **问题数**: 3
**总结**: 静态分析发现 3 个潜在问题

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第104行)

- **类别**: style
- **描述**: 第104行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
bus.subscribe(SystemEvent.AGENT_STARTED, lambda e: print(f"started: {e.payload}"))
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第105行)

- **类别**: style
- **描述**: 第105行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
bus.subscribe("agent.*", lambda e: print(f"agent event: {e.event_type}"))
```

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第112行)

- **类别**: style
- **描述**: 第112行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(e.event_type, e.timestamp)
```

### D:\AOS\src\kernel\auth_bridge.py
**评分**: 95/100 | **问题数**: 1
**总结**: 静态分析发现 1 个潜在问题

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第182行)

- **类别**: style
- **描述**: 第182行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
"开发: export AOS_TOKEN_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))') "
```

### D:\AOS\src\kernel\evolution.py
**评分**: 95/100 | **问题数**: 1
**总结**: 静态分析发现 1 个潜在问题

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第202行)

- **类别**: style
- **描述**: 第202行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(ft.score("a1"))  # FitnessScore
```

### D:\AOS\src\kernel\layers\model_gateway_layer.py
**评分**: 95/100 | **问题数**: 1
**总结**: 静态分析发现 1 个潜在问题

#### 🟢 [LOW] 生产代码中使用 print() 而非 logging (第55行)

- **类别**: style
- **描述**: 第55行: 生产代码中使用 print() 而非 logging
- **建议**: 请根据具体问题修复

```python
print(tracker.usage("zhipu/glm-4-flash"))
```

### D:\AOS\src\kernel\plugins\mistralrs_gateway.py
**评分**: 95/100 | **问题数**: 1
**总结**: 静态分析发现 1 个潜在问题

#### 🔴 [CRITICAL] 硬编码 API Key (第72行)

- **类别**: security
- **描述**: 第72行: 硬编码 API Key
- **建议**: 请根据具体问题修复

```python
api_key="mistralrs",
```

## 无问题文件 (25)

- D:\AOS\src\kernel\ecology.py (评分: 100)
- D:\AOS\src\kernel\compliance.py (评分: 100)
- D:\AOS\src\kernel\future.py (评分: 100)
- D:\AOS\src\kernel\interfaces.py (评分: 100)
- D:\AOS\src\kernel\immunity.py (评分: 100)
- D:\AOS\src\kernel\kernel.py (评分: 100)
- D:\AOS\src\kernel\hotswap.py (评分: 100)
- D:\AOS\src\kernel\hippo_scroll.py (评分: 100)
- D:\AOS\src\kernel\live.py (评分: 100)
- D:\AOS\src\kernel\types.py (评分: 100)
- D:\AOS\src\kernel\versioning.py (评分: 100)
- D:\AOS\src\kernel\skills_bridge.py (评分: 100)
- D:\AOS\src\kernel\v5_bridge.py (评分: 100)
- D:\AOS\src\kernel\system.py (评分: 100)
- D:\AOS\src\kernel\layers\mcp_bus_layer.py (评分: 100)
- D:\AOS\src\kernel\layers\agent_runtime_layer.py (评分: 100)
- D:\AOS\src\kernel\layers\model_fallback.py (评分: 100)
- D:\AOS\src\kernel\__init__.py (评分: 100)
- D:\AOS\src\kernel\layers\ui_layer.py (评分: 100)
- D:\AOS\src\kernel\layers\__init__.py (评分: 100)
- D:\AOS\src\kernel\plugins\mcp_skill_bus.py (评分: 100)
- D:\AOS\src\kernel\plugins\fabric_runtime.py (评分: 100)
- D:\AOS\src\kernel\plugins\composite_gateway.py (评分: 100)
- D:\AOS\src\kernel\plugins\__init__.py (评分: 100)
- D:\AOS\src\kernel\plugins\litellm_gateway.py (评分: 100)

## 组件清单

| 组件 | 来源 | 用途 |
|------|------|------|
| LLM 推理 | deeproute:gpt-4o-mini | 代码审查分析 |
| SandboxManager | `src/execution/sandbox.py` | 测试隔离执行 |
| WorkspaceManager | `src/execution/workspace.py` | 文件读写操作 |
| ThreadPoolExecutor | `concurrent.futures` | 多文件并行审查 |
| 审查 Prompt | `src/capabilities/code_review.py` | 审查规则定义 |

---
*由 AOS Code Review Pipeline 生成*