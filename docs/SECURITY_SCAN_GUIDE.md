# AOS 安全扫描指南

本文档说明如何使用AOS项目的安全扫描工具。

## 快速开始

### 1. 安装依赖

```bash
pip install bandit safety ruff mypy
```

或者使用uv：

```bash
uv pip install bandit safety ruff mypy
```

### 2. 运行安全扫描

```bash
python scripts/security_scan.py
```

这将运行所有安全扫描工具并生成综合报告。

## 单独运行各工具

### Bandit - Python代码静态分析

```bash
# 扫描src目录
bandit -r src/

# 生成JSON报告
bandit -r src/ -f json -o bandit-report.json

# 查看配置
bandit -r src/ -c pyproject.toml
```

### Safety - 依赖漏洞扫描

```bash
# 检查依赖漏洞
safety check

# 生成JSON报告
safety check --json --output safety-report.json

# 检查特定文件
safety check -r requirements.txt
```

### Ruff - 代码质量和安全检查

```bash
# 检查代码
ruff check src/ tests/

# 自动修复
ruff check --fix src/ tests/

# 格式化代码
ruff format src/ tests/

# 检查格式
ruff format --check src/ tests/
```

### MyPy - 类型检查

```bash
# 类型检查
mypy src/ --ignore-missing-imports

# 严格模式
mypy src/ --strict

# 生成HTML报告
mypy src/ --html-report ./mypy-report
```

## CI/CD集成

GitHub Actions会自动运行安全扫描：

- **触发条件**：push到main/develop分支、Pull Request、每天凌晨2点
- **扫描工具**：Bandit、Safety、Ruff、MyPy
- **报告位置**：GitHub Actions Artifacts

查看扫描结果：
1. 进入GitHub Actions页面
2. 选择"Security Scan"工作流
3. 下载Artifacts中的报告文件

## 配置文件

### pyproject.toml

```toml
[tool.bandit]
exclude_dirs = ["tests", ".git", "__pycache__", ".venv", "venv", "env"]
skips = ["B101", "B601"]
severity_level = "medium"
confidence_level = "medium"

[tool.safety]
ignore = ["70612"]
full-report = true
continue-on-error = true
```

## 报告说明

### 扫描报告文件

- `security-scan-report.json` - JSON格式的综合报告
- `security-scan-report.md` - Markdown格式的综合报告
- `bandit-report.json` - Bandit的详细报告
- `safety-report.json` - Safety的详细报告

### 严重程度分级

| 级别 | Bandit | Safety | 说明 |
|------|--------|--------|------|
| HIGH | HIGH | - | 高危漏洞，必须立即修复 |
| MEDIUM | MEDIUM | - | 中危漏洞，建议尽快修复 |
| LOW | LOW | - | 低危漏洞，建议修复 |
| - | - | Vulnerability | 已知CVE漏洞，必须修复 |

## 常见问题

### Q1: Bandit报错"ImportError"

**原因**: Bandit无法导入某些依赖

**解决**:
```bash
# 安装项目依赖
pip install -e ".[dev]"

# 或者忽略缺失的依赖
bandit -r src/ --skip B101
```

### Q2: Safety报错"No package found"

**原因**: Safety无法找到依赖文件

**解决**:
```bash
# 生成requirements.txt
pip freeze > requirements.txt

# 或者使用pyproject.toml
safety check
```

### Q3: MyPy报错"Cannot find implementation"

**原因**: 类型存根缺失

**解决**:
```bash
# 安装类型存根
pip install types-requests types-PyYAML

# 或者忽略缺失的导入
mypy src/ --ignore-missing-imports
```

### Q4: Ruff报错"Too many files"

**原因**: 文件数量过多

**解决**:
```bash
# 只扫描变更的文件
ruff check $(git diff --name-only --diff-filter=ACM main | grep -E '\.py$')
```

## 最佳实践

### 1. 定期扫描

- **本地开发**: 每次提交前运行`python scripts/security_scan.py`
- **CI/CD**: 每次push和PR自动运行
- **定期审计**: 每周运行一次完整扫描

### 2. 修复优先级

1. **P0 - 严重**: 立即修复（如命令注入、SQL注入）
2. **P1 - 高**: 24小时内修复（如认证绕过、权限提升）
3. **P2 - 中**: 1周内修复（如信息泄露、配置错误）
4. **P3 - 低**: 1个月内修复（如日志泄露、文档错误）

### 3. 预防措施

- **代码审查**: 所有代码变更必须经过审查
- **依赖管理**: 定期更新依赖，监控漏洞公告
- **安全培训**: 定期进行安全培训，提高安全意识
- **应急响应**: 建立安全事件响应机制

### 4. 工具配置

- **Bandit**: 根据项目需求调整`skips`和`exclude_dirs`
- **Safety**: 根据项目需求调整`ignore`列表
- **Ruff**: 根据项目需求调整`select`和`ignore`
- **MyPy**: 根据项目需求调整`strict`模式

## 参考资源

- [Bandit文档](https://bandit.readthedocs.io/)
- [Safety文档](https://pyup.io/safety/)
- [Ruff文档](https://docs.astral.sh/ruff/)
- [MyPy文档](https://mypy.readthedocs.io/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)

## 联系方式

- **安全团队**: security@aos.dev
- **GitHub Security**: https://github.com/aos-dev/aos-kernel/security
- **漏洞报告**: https://github.com/aos-dev/aos-kernel/security/advisories

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**维护者**: AOS Security Team