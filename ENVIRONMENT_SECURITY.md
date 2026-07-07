# 环境变量安全指南

## 🔐 安全配置说明

AOS v5.0 支持通过环境变量管理敏感信息，避免在配置文件中存储明文密钥。

## 📝 环境变量列表

### 核心安全配置
- `AOS_API_KEY` - API访问密钥
- `AOS_UNIFIED_API_KEY` - 统一AI网关密钥

### LLM Provider配置
- `AOS_ZHIPU_API_KEY` - 智谱AI API密钥
- `AOS_SILICONFLOW_API_KEY` - SiliconFlow API密钥
- `AOS_BAIDU_API_KEY` - 百度文心API密钥
- `AOS_BAIDU_SECRET_KEY` - 百度文心密钥
- `AOS_XFYUN_APP_ID` - 讯飞语音应用ID
- `AOS_XFYUN_API_KEY` - 讯飞语音API密钥
- `AOS_XFYUN_API_SECRET` - 讯飞语音API密钥

## 🔧 使用方法

### Windows (PowerShell)
```powershell
# 设置单个环境变量
$env:AOS_API_KEY="your_secure_api_key"

# 设置多个环境变量
$env:AOS_API_KEY="your_secure_api_key"
$env:AOS_UNIFIED_API_KEY="your_unified_key"
$env:AOS_ZHIPU_API_KEY="your_zhipu_key"

# 永久设置（需要管理员权限）
[System.Environment]::SetEnvironmentVariable('AOS_API_KEY', 'your_secure_api_key', 'User')
```

### Windows (CMD)
```cmd
# 设置临时环境变量
set AOS_API_KEY=your_secure_api_key
set AOS_UNIFIED_API_KEY=your_unified_key

# 永久设置
setx AOS_API_KEY "your_secure_api_key"
```

### Linux/macOS
```bash
# 临时设置
export AOS_API_KEY="your_secure_api_key"
export AOS_UNIFIED_API_KEY="your_unified_key"

# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export AOS_API_KEY="your_secure_api_key"' >> ~/.bashrc
source ~/.bashrc
```

### Docker Compose
```yaml
version: '3.8'
services:
  aos:
    environment:
      - AOS_API_KEY=${AOS_API_KEY}
      - AOS_UNIFIED_API_KEY=${AOS_UNIFIED_API_KEY}
      - AOS_ZHIPU_API_KEY=${AOS_ZHIPU_API_KEY}
```

## 🔑 生成安全密钥

### 使用Python生成随机密钥
```python
import secrets

# 生成32字节的安全密钥
api_key = secrets.token_urlsafe(32)
print(f"AOS_API_KEY={api_key}")
```

### 使用OpenSSL生成
```bash
# 生成随机密钥
openssl rand -base64 32
```

## ⚠️ 安全注意事项

1. **不要提交密钥到版本控制系统**
   - `.env` 文件已在 `.gitignore` 中
   - 使用 `.env.example` 作为模板

2. **生产环境建议**
   - 使用专业的密钥管理服务（如 AWS Secrets Manager、Azure Key Vault）
   - 定期轮换API密钥
   - 使用最小权限原则

3. **开发环境**
   - 可以使用 `.env` 文件进行本地开发
   - 确保不要共享包含真实密钥的 `.env` 文件

4. **日志安全**
   - 避免在日志中记录敏感信息
   - 使用日志脱敏技术

## 🚀 快速开始

1. 复制安全模板：
```bash
cp .env.security .env
```

2. 编辑 `.env` 文件，填写你的API密钥，或设置环境变量

3. 启动系统：
```bash
python launch.py
```

## 🔍 验证配置

启动系统后，检查日志输出，确认API密钥已正确加载：
```
INFO - 使用API嵌入服务: siliconflow
INFO - 记忆层初始化完成 (SQLite + ChromaDB)
```

如果看到密钥相关警告，请检查环境变量配置。