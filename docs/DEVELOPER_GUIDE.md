# AOS 开发者指南

## 架构概览

AOS 采用四层架构，从底向上：

```
基础设施层 → 能力路由层 → 内核层 → 产品层
```

### 基础设施层

最底层，包含真实开源引擎的适配器实现。每个引擎通过 `BaseAgentAdapter` ABC 接口接入，适配器负责将 AOS 的能力调用翻译成引擎原生 API。适配器本身很薄——不重新实现引擎逻辑，只做协议转换。

### 能力路由层

由 `FabricHub`（`kernel/plugins/fabric_hub.py`）统一持有并调度。所有能力按 `Capability` 枚举标签发现引擎，路由层负责：
- 能力到引擎的解析（`resolve_engine`）
- 高中低三级档位的级联故障转移
- 健康检查与隔离保护

### 内核层

`AOSKernel`（`kernel/kernel.py`）只做三件事，恒定不变：
1. **生命周期管理** — `register_agent` / `list_agents` / `stop_agent`
2. **消息路由** — `send_message`（在 Agent 和运行时插件之间路由）
3. **权限治理** — `check_permission`（验证每个操作的权限，默认拒绝）

内核本身零依赖。本文件只 import 标准库和同包的 `types` / `interfaces`，绝不 import brain / litellm / mcp / fabric——那些是插件，由外部接线层登记进来。

### 产品层

包括 autopilot 自主环、OPC 数字组织内核、单创OS 多租户前端等。产品层通过内核和 FabricHub 的标准接口调用底层能力。

### 依赖倒置

内核只认 ABC 接口（`AgentRuntime`、`ModelGateway`、`SkillBus`），真实引擎都是插件。接线层（`kernel/wiring.py`）负责在启动时把具体实现登记到内核的插件插槽。任一插件导入失败都被单独吞掉，不影响内核存活。

---

## 核心扩展点

### 1. 新增适配器（最常见）

新增一个真实开源引擎接入 AOS 的完整步骤：

**第一步：继承 BaseAgentAdapter**

在 `core/fabric/adapters/` 下新建适配器文件，继承 `BaseAgentAdapter`（`core/fabric/adapter.py`），实现四个抽象方法：

```python
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

class MyEngineAdapter(BaseAgentAdapter):

    @property
    def engine_id(self) -> str:
        return "my_engine"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.WEB_SEARCH]  # 声明该引擎能做的事

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        # 把 AOS 的 capability 调用翻译成引擎原生 API
        try:
            result = self._call_engine(req.payload)
            return InvokeResult(ok=True, data=result, engine_id="my_engine")
        except Exception as e:
            return InvokeResult(ok=False, error=str(e), engine_id="my_engine")

    def health(self) -> bool:
        # 真实连通性探测，不能硬编码
        return self._probe_endpoint()
```

**第二步：注册能力映射**

在 `core/fabric/capability.py` 的 `ENGINE_CAPABILITY_MAP` 字典中添加引擎到能力的映射：

```python
ENGINE_CAPABILITY_MAP["my_engine"] = [Capability.WEB_SEARCH]
```

**第三步：注册档位**

在 `core/fabric/capability.py` 的 `ENGINE_TIER` 字典中声明引擎档位（`TIER_HIGH` / `TIER_MEDIUM` / `TIER_LOW`）：

```python
ENGINE_TIER["my_engine"] = TIER_LOW  # 轻量兜底
```

**第四步：加入 FabricHub 默认注册集合**

在 `kernel/plugins/fabric_hub.py` 的 `_ADAPTERS` 元组中加入适配器类：

```python
from core.fabric.adapters.my_engine_adapter import MyEngineAdapter

_ADAPTERS: tuple[type[BaseAgentAdapter], ...] = tuple(
    a for a in (
        # ... 已有适配器 ...
        MyEngineAdapter,       # 新增：我的引擎适配器
    )
    if a is not None
)
```

**第五步：提供测试文件**

在 `tests/` 下新建 `test_my_engine_adapter.py`，至少覆盖：
- `engine_id` 返回值
- `advertise_capabilities` 声明的能力集合
- `health()` 在引擎不可达时返回 False
- `invoke()` 在成功和失败场景下的返回值

```bash
pytest tests/test_my_engine_adapter.py -v
```

### 2. 新增能力标签

当需要一个新的能力维度（如 `data.query`）：

**第一步：在 Capability 枚举中添加新成员**

在 `core/fabric/capability.py` 的 `Capability` 枚举中添加：

```python
class Capability(str, Enum):
    # ... 已有能力 ...
    MY_NEW_CAPABILITY = "my.new_capability"  # 新增能力标签
```

**第二步：映射到引擎**

在 `ENGINE_CAPABILITY_MAP` 中把新能力分配给能提供它的引擎：

```python
ENGINE_CAPABILITY_MAP["my_engine"] = [Capability.MY_NEW_CAPABILITY]
```

**第三步：映射到策略动作**

在 `kernel/compliance.py` 的 `CAPABILITY_POLICY_ACTION` 中为新能力指定合规策略动作：

```python
CAPABILITY_POLICY_ACTION = {
    # ... 已有映射 ...
    Capability.MY_NEW_CAPABILITY.value: "call:my_new_capability",
}
```

### 3. 新增行业模板

为特定行业（如医疗、教育）创建标准化工作流模板：

**第一步：添加行业类型**

在 `src/kernel/danchuang/templates/__init__.py` 的 `IndustryType` 枚举中添加新成员：

```python
class IndustryType(str, Enum):
    HARDWARE = "hardware"
    ECOMMERCE = "ecommerce"
    CONTENT = "content"
    SERVICE = "service"
    GENERAL = "general"
    HEALTHCARE = "healthcare"  # 新增
```

**第二步：定义行业模板**

在同一文件的 `_init_templates()` 函数中添加 `IndustryTemplate` 实例：

```python
_TEMPLATES[IndustryType.HEALTHCARE] = IndustryTemplate(
    industry=IndustryType.HEALTHCARE,
    name="医疗健康",
    description="医疗健康行业数字化解决方案",
    role_config={...},
    workflow_templates={...},
    knowledge_seeds=[...],
    recommended_tools=[...],
    kpi_examples=[...],
)
```

**第三步：添加 Playbook 模板**

在 `src/kernel/danchuang/engine/playbook_library.py` 的 `PlaybookLibrary` 中注册行业工作流模板：

```python
PlaybookTemplate(
    playbook_id="healthcare_patient_onboarding",
    name="患者入职流程",
    industry=IndustryType.HEALTHCARE,
    steps=[
        PlaybookStep(step_id="s1", name="信息采集", opc_role=OPCRole.CUSTOMER_SERVICE, ...),
        PlaybookStep(step_id="s2", name="方案制定", opc_role=OPCRole.PRODUCT_RD, ...),
    ],
)
```

### 4. 新增 OPC 岗位

OPC 数字组织内核支持 5 大标准岗位。新增岗位的步骤：

**第一步：添加岗位枚举**

在 `src/kernel/danchuang/opc/roles.py` 的 `OPCRole` 枚举中添加：

```python
class OPCRole(Enum):
    PRODUCT_RD = "product_rd"
    MARKET_RESEARCH = "market_research"
    CONTENT_MARKETING = "content_marketing"
    CUSTOMER_SERVICE = "customer_service"
    FINANCE = "finance"
    HR = "hr"  # 新增：人力资源
```

**第二步：定义岗位智能体**

在同一文件中创建岗位智能体类，继承 `OPCAgentRole`：

```python
@dataclass
class HRAgent(OPCAgentRole):
    def __init__(self):
        super().__init__(
            role=OPCRole.HR,
            name="人力资源智能体",
            description="负责人才招聘、绩效管理、员工培训等",
            capabilities=["简历筛选", "面试评估", "培训计划"],
            tools=["web.search", "code.generate"],
            workflow_templates={...},
        )
```

**第三步：注册到岗位映射**

在 `src/kernel/plugins/opc_roles.py`（如存在）或 `roles.py` 底部的工厂函数中注册新岗位。

---

## 调试技巧

### 日志级别控制

设置环境变量调整日志详细度：

```bash
export AOS_LOG_LEVEL=DEBUG
```

### FabricHub 健康检查

快速检查所有适配器的注册和健康状态：

```python
python -c "
from kernel.plugins.fabric_hub import FabricHub
hub = FabricHub()
report = hub.health_report()
for engine, info in report.items():
    print(f'{engine}: live={info[\"live\"]}')
"
```

或通过内核间接检查：

```python
python -c "
from kernel.wiring import build_default_kernel
kernel = build_default_kernel(inject_brain=False)
print(kernel.fabric_health())
"
```

### 测试单个适配器

```bash
pytest tests/test_search_adapter.py -v
```

### 跳过重型测试

默认环境下重型测试（需要外部引擎或 GPU）会被跳过：

```bash
export AOS_RUN_NATIVE_TESTS=0
pytest tests/ -v
```

需要跑重型测试时显式开启：

```bash
export AOS_RUN_NATIVE_TESTS=1
pytest tests/ -v
```

### 排查适配器导入失败

wiring 层对每个插件用 try/except 包裹，缺依赖时跳过而不影响内核。查看跳过原因：

```bash
python -c "from kernel.wiring import build_default_kernel; build_default_kernel(inject_brain=False)"
```

输出中的 `[wiring] 跳过 OSS 适配器 ...` 即为被跳过的适配器及其原因。

---

## 性能优化

### FabricHub 构造开销

`FabricHub` 构造涉及多个适配器的导入和初始化，耗时约分钟级。测试中应使用 module 级 fixture 复用实例：

```python
import pytest
from kernel.plugins.fabric_hub import FabricHub

@pytest.fixture(scope="module")
def hub():
    return FabricHub()
```

### autopilot 统一路由

autopilot 的 dispatch 默认走 FabricHub 统一路由（`AOS_AUTOPILOT_USE_FABRICHUB=1`），确保所有任务经过能力路由层而非直连特定引擎。

### 重型引擎子进程隔离

agnes / ag2 等重型或多模态引擎默认隔离进独立子进程（`kernel/isolation/subprocess_iso.py`）。崩溃不传染内核，可热备切换。在 `kernel/wiring.py` 的 `_ISOLATED_BY_DEFAULT` 字典中管理隔离列表。

### 模型网关回退链

`build_default_kernel` 中的模型网关按优先级级联：

```
Ollama（本地优先） → Agnes（多模态） → mistralrs（本地） → LiteLLM（云端兜底） → Cloud（最后兜底）
```

无 GPU 时默认走云端，本地留作兜底。不配置任何 key 即为纯开源离线运行。

---

## 代码质量门（提交前自检）

每次提交前必须通过以下检查：

```bash
# Linter：0 error
ruff check src/ tests/

# 类型检查：0 error
mypy src/ --ignore-missing-imports

# 相关测试全绿
pytest tests/test_related_file.py -v

# 覆盖率基线不倒退
# kernel/ >= 80%, core/fabric/ >= 60%, 总覆盖率 >= 50%
```

### 覆盖率基线

| 模块 | 最低覆盖率 |
|------|-----------|
| kernel/ | 80% |
| core/fabric/ | 60% |
| 总计 | 50% |

### 已知遗留问题

以下测试为 legacy 债务，已知失败且与新栈无关，不要误修：
- `test_database::test_persistence_bridge_on_unified_db`
- `test_memory`（no such table）

---

## 参考文件索引

| 文件 | 用途 |
|------|------|
| `kernel/kernel.py` | 内核三职责：生命周期 / 路由 / 权限 |
| `kernel/wiring.py` | 接线层：组装默认内核，登记插件 |
| `kernel/plugins/fabric_hub.py` | 能力路由枢纽，适配器注册与路由 |
| `core/fabric/adapter.py` | BaseAgentAdapter ABC 定义 |
| `core/fabric/capability.py` | Capability 枚举 + ENGINE_CAPABILITY_MAP + ENGINE_TIER |
| `kernel/compliance.py` | CAPABILITY_POLICY_ACTION 合规策略 |
| `kernel/danchuang/opc/roles.py` | OPC 岗位智能体定义 |
| `kernel/danchuang/templates/__init__.py` | 行业模板系统 |
| `kernel/danchuang/engine/playbook_library.py` | Playbook 工作流模板库 |
| `kernel/isolation/subprocess_iso.py` | 子进程隔离机制 |
