# AOS 开源贡献指南

## 快速开始

1. **Fork 仓库**：在 GitHub 上 Fork AOS 仓库到你的账户。

2. **克隆代码**：
   ```bash
   git clone https://github.com/<your-username>/AOS.git
   cd AOS
   ```

3. **环境搭建**：
   - 确保已安装 Python 3.14
   - 设置环境变量：`PYTHONPATH=D:/AOS/src`
   - 安装依赖：
     ```bash
     pip install -r requirements.txt
     ```

4. **运行测试**：
   ```bash
   pytest tests/ -q --timeout=60
   ```

5. **创建分支并提交**：
   ```bash
   git checkout -b feature/your-feature-name
   # 进行修改
   git add .
   git commit -m "feat: 添加你的功能描述"
   git push origin feature/your-feature-name
   ```

6. **创建 Pull Request**：在 GitHub 上从你的分支创建 PR 到主仓库。

## 环境要求

- **Python 版本**：3.14（系统 Python，非 venv）
- **PYTHONPATH**：必须设置为 `D:/AOS/src`
- **依赖管理**：使用 `requirements.txt`
- **环境配置**：`.env` 文件包含真实密钥，已加入 `.gitignore`，**绝不提交**

## 代码规范

### 格式检查
```bash
# 代码风格检查
ruff check src/ tests/

# 类型检查
mypy src/ --ignore-missing-imports
```

### 代码风格
- 遵循 PEP 8 规范
- 使用 Google 风格的 docstrings
- 行宽限制：120 字符
- Import 顺序：标准库 → 第三方库 → 本地库

### 命名规范
- 类名：`PascalCase`
- 函数名：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 私有成员：`_leading_underscore`

### 禁止事项
- 禁止使用 `exec()` 或 `eval()` 执行用户输入
- 禁止硬编码密钥或敏感信息
- 禁止在 `async` 函数中调用同步阻塞代码
- 禁止使用 `print()` 代替日志记录
- 禁止使用可变默认参数
- 禁止在 `__init__.py` 中导入 `src` 包

## 新增适配器指南

AOS 使用统一的适配器架构，所有引擎通过 `BaseAgentAdapter` 接口接入。

### 步骤 1：实现适配器
在 `src/core/fabric/adapters/` 目录下创建新的适配器文件：

```python
from src.core.fabric.adapter import BaseAgentAdapter

class YourAdapter(BaseAgentAdapter):
    def advertise_capabilities(self):
        """声明适配器提供的能力"""
        return ["capability1", "capability2"]
    
    def health_check(self):
        """健康检查"""
        return True
    
    def invoke(self, capability, payload):
        """调用引擎"""
        # 实现具体逻辑
        pass
```

### 步骤 2：注册能力
在 `src/core/fabric/capability.py` 中注册新能力：

```python
class Capability:
    YOUR_CAPABILITY = "your.capability"
```

### 步骤 3：注册适配器
在 `src/core/fabric/registry.py` 中注册适配器：

```python
from src.core.fabric.adapters.your_adapter import YourAdapter

registry.register("your-engine", YourAdapter())
```

### 步骤 4：编写测试
为新适配器编写测试，确保覆盖主要功能。

## 新增行业模板指南

AOS 支持行业特定的模板系统。

### 步骤 1：创建模板目录
在 `src/templates/` 下创建新的行业目录：

```bash
mkdir -p src/templates/your-industry
```

### 步骤 2：定义模板文件
创建 YAML 或 JSON 格式的模板文件，定义行业特定的配置和工作流。

### 步骤 3：注册模板
在 `src/templates/manifest.json` 中注册新模板：

```json
{
  "your-industry": {
    "name": "你的行业",
    "description": "行业描述",
    "version": "1.0.0"
  }
}
```

### 步骤 4：编写测试
为模板功能编写测试，确保模板正确加载和使用。

## 测试要求

### 测试框架
- 使用 pytest 作为测试框架
- 测试文件位于 `tests/` 目录

### 测试覆盖
- 新增代码必须包含对应的测试
- 覆盖率基线不得倒退：
  - `kernel/` 模块：≥ 80%
  - `core/fabric/` 模块：≥ 60%
  - 总体覆盖率：≥ 50%

### 运行测试
```bash
# 运行所有测试
pytest tests/ -q --timeout=60

# 运行特定测试文件
pytest tests/test_your_file.py -v

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

### 测试质量
- 测试必须真实可运行，不弄虚作假
- 测试应覆盖正常路径和错误路径
- 测试应独立运行，不依赖外部状态

## PR 规范

### 提交信息格式
使用约定式提交（Conventional Commits）格式：

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 类型（Type）
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式调整（不影响逻辑）
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

### 示例
```
feat(fabric): 新增天气查询适配器

- 实现 WeatherAdapter 类
- 注册 WEATHER_QUERY 能力
- 添加相关测试用例

Closes #123
```

### PR 检查清单
1. 代码通过 `ruff check` 和 `mypy` 检查
2. 测试全部通过
3. 覆盖率基线不倒退
4. 文档已更新（如适用）
5. 提交信息符合约定式提交格式
6. 关联了相关 Issue 或需求

## 核心理念参考

### AOS 九大核心理念
请参考 `agents.md` 中的九大核心理念，这是 AOS 项目的存在理由和设计哲学：

1. **不手配，自闭环** - 系统自动完成配置和执行
2. **失败即训练数据，记忆有生有灭** - 失败经验自动沉淀和遗忘
3. **芯粒隔离** - 故障熔断隔离，非多 Agent 分解
4. **万物为我所用，不为任何一物所绑定** - 多后端级联故障转移
5. **能力即路由，权限即边界** - 按能力调度，按权限控制
6. **诚实比聪明重要，输出自带量化置信** - 不伪造成功，附带原始证据
7. **千人千面** - 贴合本地环境的专属智能
8. **黑盒不可训，白盒才可进化** - 全链路执行 Trace 可观测
9. **可验证即真理** - 所有声明必须可被复核

### Ponytail 七级决策阶梯
在写/改任何东西之前，先运行以下七级决策阶梯，停在第一个成立的台阶：

1. **这东西需要存在吗？** → 不需要就跳过（YAGNI）
2. **代码库里已经有了？** → 复用，不重写
3. **标准库能实现？** → 用它（零依赖优先）
4. **平台原生功能支持？** → 用它
5. **已安装的依赖能用？** → 用它，不新装包
6. **能一行解决？** → 一行搞定
7. **以上都不行** → 才写满足需求的最小实现

> 阶梯在理解问题之后运行，不取代理解。懒，但不渎职（Lazy, not negligent）。

## 质量门（TRUST 5）

每个 PR 自检以下五个维度：

- **T**ested：有真实复现测试，覆盖率基线不倒退
- **R**eadable：命名清晰、ruff 0 error、注释说"为什么"而非"是什么"
- **U**nified：格式/import 顺序/目录结构一致，不顺手"美化"无关代码
- **S**ecured：无硬编码密钥、输入校验、OWASP 常识过关
- **T**rackable：约定式提交、关联需求、结构化日志

## 诚实纪律

1. **不弄虚作假** - 真跑、贴可复核的原始证据
2. **提交必当场核验** - `git commit` 后立刻确认 hash 真进 git
3. **先思考再编码** - 先说假设、亮取舍、给最简方案，再动手
4. **改动最小化** - 只碰该改的，不顺手"美化"无关代码
5. **全盘思维优先** - 修 bug 前先推完整链路

## 获取帮助

- 查看 `agents.md` 了解完整项目规范
- 查看 `STATUS.md` 了解当前项目状态
- 在 GitHub Issues 中提问或报告问题