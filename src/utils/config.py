from pydantic_settings import BaseSettings
from pydantic import field_validator, Field, model_validator, AliasChoices
from typing import Optional
from pathlib import Path
import os
import logging

_LOG = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Config(BaseSettings):
    model_config = {
        "extra": "allow",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True
    }
    
    def __init__(self, *args, **kwargs):
        """后处理验证：确保关键安全配置存在"""
        super().__init__(*args, **kwargs)
        
        # API密钥验证：生产环境必须配置哈希密钥
        if self.APP_ENV == "production":
            if not self.API_KEY_HASH:
                raise ValueError(
                    "生产环境必须配置API_KEY_HASH环境变量！"
                    "请运行: python -c 'import bcrypt; print(bcrypt.hashpw(b\"your_secret_key\", bcrypt.gensalt()).decode())'"
                )
        elif not self.API_KEY_HASH and not self.API_KEY:
            # 开发环境至少需要一个密钥配置
            logger = __import__('logging').getLogger(__name__)
            logger.warning("未配置API密钥，将在首次访问时自动生成开发密钥...")
            
        # 管理员账户验证
        if not self.ADMIN_USERNAME:
            raise ValueError("必须配置AOS_ADMIN_USERNAME环境变量")
        
        # PostgreSQL生产环境密码验证
        if self.APP_ENV == "production" and self.STATE_BACKEND == "postgres" and not self.POSTGRES_PASSWORD:
            raise ValueError("生产环境PostgreSQL必须配置AOS_POSTGRES_PASSWORD")
    BASE_DIR: str = str(_BASE_DIR)
    APP_NAME: str = "能体操作系统v5.0零成本版"
    APP_VERSION: str = "5.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # API安全 - 支持环境变量 AOS_API_KEY  
    # 安全加固：移除默认值，强制环境变量配置
    API_KEY: Optional[str] = Field(default=None, validation_alias="AOS_API_KEY")
    API_KEY_HASH: Optional[str] = Field(default=None, validation_alias="AOS_API_KEY_HASH")  # 强制哈希验证
    ALLOWED_ORIGINS: str = "http://localhost:8501,http://localhost:8000"
    # Host 头白名单（防 Host 头投毒 / 密码重置链接与缓存投毒）。
    # 开发期默认本机；生产必须显式配置真实域名，"*" 会在 main.py 被拒绝。
    ALLOWED_HOSTS: str = Field(
        default="localhost,127.0.0.1,[::1]",
        validation_alias=AliasChoices("AOS_ALLOWED_HOSTS", "ALLOWED_HOSTS"),
    )
    MAX_REQUESTS_PER_MINUTE: int = 100

    # ===== 团队级认证 (OAuth2/JWT, RS256 非对称) —— 与 API-Key 并存 =====
    # 私钥签名 / 公钥验签；密钥经 utils.keystore 解析 (env -> .secrets/jwt -> 开发期自动生成)。
    # 不再使用 HS256 对称密钥（已知密钥可离线伪造令牌）。
    AUTH_JWT_PRIVATE_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices("AOS_JWT_PRIVATE_KEY", "AUTH_JWT_PRIVATE_KEY"))
    AUTH_JWT_PUBLIC_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices("AOS_JWT_PUBLIC_KEY", "AUTH_JWT_PUBLIC_KEY"))
    AUTH_JWT_ALGORITHM: str = "RS256"
    AUTH_JWT_EXPIRE_MINUTES: int = 480  # 8h
    # 签发方 / 受众：只校验 exp 的令牌可被"另一个也用同一把公钥的服务"签发的
    # 令牌横向复用。补 iss/aud/nbf 后，跨服务令牌串用会被直接拒绝。
    AUTH_JWT_ISSUER: str = Field(
        default="aos", validation_alias=AliasChoices("AOS_JWT_ISSUER", "AUTH_JWT_ISSUER")
    )
    AUTH_JWT_AUDIENCE: str = Field(
        default="aos-api", validation_alias=AliasChoices("AOS_JWT_AUDIENCE", "AUTH_JWT_AUDIENCE")
    )
    # 时钟偏移容忍（秒），避免多机部署因 NTP 漂移误判 nbf/exp。
    AUTH_JWT_LEEWAY_SECONDS: int = 30
    # 安全加固：移除admin用户默认值 
    ADMIN_USERNAME: Optional[str] = Field(default=None, validation_alias="AOS_ADMIN_USERNAME")
    # 不再提供任何默认值；生产环境必须设置，开发环境自动生成强随机口令落盘 .secrets/
    ADMIN_PASSWORD: Optional[str] = Field(default=None, validation_alias="AOS_ADMIN_PASSWORD")

    # 沙箱执行 HTTP API（/api/sandbox/*）默认关闭：该端点经 DeerFlow 本地 provider
    # 在宿主机直接执行任意命令，属高危 RCE 面；仅在受信任环境显式开启
    # （AOS_SANDBOX_API_ENABLED=true 或 SANDBOX_API_ENABLED=true）。
    # 注：本仓库 pydantic 版本中 Field(env=...) 已被忽略，故用 validation_alias 接收两种前缀。
    SANDBOX_API_ENABLED: bool = Field(
        default=False,
        validation_alias=AliasChoices("AOS_SANDBOX_API_ENABLED", "SANDBOX_API_ENABLED"),
    )

    # 安全边界：sandbox exec 端点命令白名单。只有匹配这些前缀的命令才允许执行。
    # 可通过环境变量 AOS_SANDBOX_ALLOWED_COMMANDS 覆盖（JSON 数组字符串）。
    SANDBOX_ALLOWED_COMMANDS: list = Field(
        default=["ls", "cat", "echo", "pwd", "whoami", "date", "head", "tail",
                 "wc", "grep", "find", "file", "stat", "df", "du", "env",
                 "python --version", "python -c", "node --version", "node -e"],
        validation_alias=AliasChoices("AOS_SANDBOX_ALLOWED_COMMANDS", "SANDBOX_ALLOWED_COMMANDS"),
    )

    # 安全边界：是否要求请求体中 confirm=true 才执行命令（防误触/自动化滥用）。
    SANDBOX_REQUIRE_CONFIRM: bool = Field(
        default=True,
        validation_alias=AliasChoices("AOS_SANDBOX_REQUIRE_CONFIRM", "SANDBOX_REQUIRE_CONFIRM"),
    )

    # ===== 状态后端 (团队级可插拔 seam: sqlite(个人) -> postgres(团队/公司)) =====
    STATE_BACKEND: str = Field(default="sqlite", validation_alias=AliasChoices("AOS_STATE_BACKEND", "STATE_BACKEND"))  # sqlite | postgres
    POSTGRES_HOST: str = Field(default="localhost", validation_alias=AliasChoices("AOS_POSTGRES_HOST", "POSTGRES_HOST"))
    POSTGRES_PORT: int = Field(default=5432, validation_alias=AliasChoices("AOS_POSTGRES_PORT", "POSTGRES_PORT"))
    POSTGRES_USER: str = Field(default="aos", validation_alias=AliasChoices("AOS_POSTGRES_USER", "POSTGRES_USER"))
    POSTGRES_PASSWORD: Optional[str] = Field(default=None, validation_alias="AOS_POSTGRES_PASSWORD")  # 安全加固：移除默认空密码
    POSTGRES_DB: str = Field(default="aos", validation_alias=AliasChoices("AOS_POSTGRES_DB", "POSTGRES_DB"))
    # 统一API - 支持环境变量 AOS_UNIFIED_API_KEY
    UNIFIED_API_KEY: str = Field(default="", validation_alias=AliasChoices("AOS_UNIFIED_API_KEY", "UNIFIED_API_KEY"))
    UNIFIED_BASE_URL: str = "https://api.deeproute.com/v1"
    
    CHAT_MODEL_QWEN: str = "qwen-qwen3.6-27b"
    CHAT_MODEL_MINIMAX: str = "minimaxai-minimax-m2.5"
    CHAT_MODEL_DOUBAO: str = "doubao-seed-2-0-lite-260428"
    CHAT_DEFAULT_MODEL: str = "qwen-qwen3.6-27b"
    
    IMAGE_MODEL_SEEDREAM: str = "doubao-seedream-5-0-260128"
    IMAGE_MODEL_TONGYI: str = "tongyi-mai-z-image-turbo"
    IMAGE_DEFAULT_MODEL: str = "doubao-seedream-5-0-260128"
    
    ASR_MODEL: str = "teleai-telespeechasr"

    # 智谱AI - 支持环境变量 AOS_ZHIPU_API_KEY
    ZHIPU_API_KEY: str = Field(default="", validation_alias=AliasChoices("AOS_ZHIPU_API_KEY", "ZHIPU_API_KEY"))
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_MODEL: str = "glm-4-flash"
    ZHIPU_ENABLED: bool = True

    # LiteLLM 推理平面（统一 LLM 路由 / 库模式复用智谱 key）
    # 库模式下 litellm.completion 直接调用；model 用 "provider/model" 形式
    LITELLM_DEFAULT_MODEL: str = "zhipu/glm-4-flash"
    LITELLM_API_KEY_ENV: str = "ZHIPU_API_KEY"  # 从进程环境读取真实 key
    LITELLM_API_BASE: str = "https://open.bigmodel.cn/api/paas/v4"  # 智谱 OpenAI 兼容地址

    # SiliconFlow - 支持环境变量 AOS_SILICONFLOW_API_KEY
    SILICONFLOW_API_KEY: str = Field(default="", validation_alias=AliasChoices("AOS_SILICONFLOW_API_KEY", "SILICONFLOW_API_KEY"))
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_MODEL: str = "deepseek-ai/DeepSeek-V2.5"
    SILICONFLOW_ENABLED: bool = True

    # 百度文心 - 支持环境变量 AOS_BAIDU_API_KEY, AOS_BAIDU_SECRET_KEY
    BAIDU_API_KEY: str = Field(default="", validation_alias=AliasChoices("AOS_BAIDU_API_KEY", "BAIDU_API_KEY"))
    BAIDU_SECRET_KEY: str = Field(default="", validation_alias=AliasChoices("AOS_BAIDU_SECRET_KEY", "BAIDU_SECRET_KEY"))
    BAIDU_BASE_URL: str = "https://aip.baidubce.com"
    BAIDU_MODEL: str = "ernie-speed-128k"
    BAIDU_ENABLED: bool = True

    # 讯飞语音 - 支持环境变量 AOS_XFYUN_APP_ID, AOS_XFYUN_API_KEY, AOS_XFYUN_API_SECRET
    XFYUN_APP_ID: str = Field(default="", validation_alias=AliasChoices("AOS_XFYUN_APP_ID", "XFYUN_APP_ID"))
    XFYUN_API_KEY: str = Field(default="", validation_alias=AliasChoices("AOS_XFYUN_API_KEY", "XFYUN_API_KEY"))
    XFYUN_API_SECRET: str = Field(default="", validation_alias=AliasChoices("AOS_XFYUN_API_SECRET", "XFYUN_API_SECRET"))
    XFYUN_MODEL: str = "lite"
    XFYUN_ENABLED: bool = True

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_ENABLED: bool = True
    # Ollama 在此架构中作为【备选/兜底】本地运行时（MiniCPM 等已导入其中）。

    # ===== MistralRS：主本地推理运行时（原生吃 GGUF / safetensors + 就地量化 ISQ）=====
    # 主用 mistralrs 跑用户下好的三个本地模型；单实例只能绑一个端口，故三模型起三个独立服务。
    #   端口 1234 = MiniCPM5-1B     (轻量全能)   -> GENERAL / HIGH_CONCURRENCY
    #   端口 1235 = Qwen2.5-Coder-3B(写代码)      -> CODING
    #   端口 1236 = DeepSeek-R1-1.5B (推理/逻辑)  -> LONG_CONTEXT / EXPERIMENT
    MISTRALRS_ENABLED: bool = True
    MISTRALRS_HOST: str = "http://localhost"
    MISTRALRS_PORT_GENERAL: int = 1234
    MISTRALRS_PORT_CODING: int = 1235
    MISTRALRS_PORT_REASONING: int = 1236
    # 注意：mistralrs `serve` 会严格校验 model 字段，必须用其 /v1/models 实际报告的 id
    # （即模型目录路径），不能用简短别名，否则返回 500 "model not available"。
    MISTRALRS_MODEL_GENERAL: str = Field(
        default="",
        description="Path to MiniCPM5 model dir. Set via AOS_MISTRALRS_MODEL_GENERAL env var.",
    )
    MISTRALRS_MODEL_CODING: str = Field(
        default="",
        description="Path to Qwen2.5-Coder model dir. Set via AOS_MISTRALRS_MODEL_CODING env var.",
    )
    MISTRALRS_MODEL_REASONING: str = Field(
        default="",
        description="Path to DeepSeek-R1 model dir. Set via AOS_MISTRALRS_MODEL_REASONING env var.",
    )

    # ---- 本地小模型（Ollama 备选，按任务类型自动选型）----
    OLLAMA_MODEL_GENERAL: str = "minicpm5-1b"
    OLLAMA_MODEL_CODING: str = "qwen2.5-coder:3b"
    OLLAMA_MODEL_REASONING: str = "deepseek-r1:1.5b"
    # 优先使用本地模型（True 时同类任务先走本地 MistralRS，Ollama 备选，云端作兜底）
    ROUTER_PREFER_LOCAL: bool = True

    SQLITE_DB_PATH: str = str(_BASE_DIR / "data" / "sqlite" / "aos.db")
    CHROMADB_PERSIST_DIR: str = str(_BASE_DIR / "data" / "chroma")
    DATA_DIR: str = str(_BASE_DIR / "data")
    OUTPUTS_DIR: str = str(_BASE_DIR / "outputs")

    API_BASE_URL: str = "http://localhost:8000"

    # ---- 向量嵌入模型配置 ----
    # 统一的嵌入模型配置，支持多种provider
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"  # 默认嵌入模型
    EMBEDDING_PROVIDER: str = "local"  # provider: local/zhipu/siliconflow/unified
    EMBEDDING_DIMENSION: int = 384  # 向量维度
    EMBEDDING_BATCH_SIZE: int = 32  # 批处理大小
    
    # 向量数据库配置
    VECTOR_COLLECTION_NAME: str = "aos_memory"
    VECTOR_ENABLED: bool = True

    ROUTER_CODING_PRIMARY: str = "mistralrs_coding"
    ROUTER_HIGH_CONCURRENCY_PRIMARY: str = "mistralrs_general"
    ROUTER_LONG_CONTEXT_PRIMARY: str = "mistralrs_reasoning"
    ROUTER_VOICE_PRIMARY: str = "xfyun"
    ROUTER_EXPERIMENT_PRIMARY: str = "mistralrs_reasoning"
    ROUTER_FALLBACK: str = "ollama"

    MCP_ENABLED: bool = True
    MCP_VERSION: str = "2024-11-05"
    MCP_SERVER_PORT: int = 8001

    # ---- 子智能体配置 ----
    OPENCLAW_ENABLED: bool = True
    OPENCLAW_COMMAND: str = "npx"
    OPENCLAW_CWD: str = str(_BASE_DIR / "external" / "jiuwenclaw")
    OPENCLAW_PATH: str = ""

    UITARS_ENABLED: bool = True
    UITARS_USE_MCP: bool = False
    UITARS_MCP_PORT: int = 8090
    UITARS_CWD: str = str(_BASE_DIR / "external" / "UI-TARS-desktop")
    UITARS_PATH: str = ""

    LOBSTER_ENABLED: bool = True
    LOBSTER_MODE: str = "openclaw_bridge"
    LOBSTER_PORT: int = 8091
    LOBSTER_PATH: str = ""

    # ---- 开源框架源码路径 (可选) ----
    # 如不填或路径不存在，则使用 AOS 内置实现
    HERMES_SOURCE_PATH: str = str(_BASE_DIR / "external" / "hermes-agent")
    HERMES_AGENT_PATH: str = str(_BASE_DIR / "external" / "hermes_agent")
    
    DEERFLOW_SOURCE_PATH: str = str(_BASE_DIR / "external" / "deer-flow" / "backend")
    DEERFLOW_CONFIG_PATH: str = str(_BASE_DIR / "external" / "deer-flow" / "config.example.yaml")
    DEERFLOW_HARNESS_PATH: str = str(_BASE_DIR / "external" / "deer-flow" / "backend" / "packages" / "harness")
    # DeerFlow 网关管理员凭证: 从环境变量读取。
    # 不再提供 "aos123456" 弱默认；生产环境必须设置，开发环境自动生成强随机口令。
    DEERFLOW_ADMIN_USER: str = Field(default="admin", validation_alias=AliasChoices("AOS_DEERFLOW_ADMIN_USER", "DEERFLOW_ADMIN_USER"))
    DEERFLOW_ADMIN_PASSWORD: Optional[str] = Field(default=None, validation_alias=AliasChoices("AOS_DEERFLOW_ADMIN_PASSWORD", "DEERFLOW_ADMIN_PASSWORD"))
    MAX_WORKERS: int = 4
    TASK_TIMEOUT: int = 300
    RETRY_ATTEMPTS: int = 2

    # Skills system
    SKILLS_ENABLED: bool = True
    SKILLS_AUTO_EVOLVE: bool = True
    SKILLS_OUTPUT_DIR: str = "outputs/skills"

    COMFYUI_ENABLED: bool = True
    COMFYUI_BASE_URL: str = "http://localhost:8188"
    COMFYUI_WORKFLOWS_DIR: str = "src/skills/workflows"
    COMFYUI_OUTPUT_DIR: str = "outputs/comfyui"

    JINA_API_KEY: str = ""
    JINA_READER_URL: str = "https://r.jina.ai"
    JINA_API_URL: str = "https://api.jina.ai/v1/extract"

    # ---- 开源项目配置 ----
    COGNEE_ENABLED: bool = True
    COGNEE_DATA_DIR: str = "data/cognee"
    COGNEE_LOG_LEVEL: str = "INFO"

    AGENCY_AGENTS_PATH: str = "external/agency-agents"
    AGENCY_AGENTS_ENABLED: bool = True

    OPEN_MONTAGE_PATH: str = "external/open_montage"
    OPEN_MONTAGE_ENABLED: bool = True

    CODEBASE_MEMORY_PATH: str = "external/codebase_memory_mcp"
    CODEBASE_MEMORY_ENABLED: bool = True

    OMNI_ROUTE_PATH: str = "external/omni_route"
    OMNI_ROUTE_ENABLED: bool = True

    DESIGN_MD_PATH: str = "external/design_md"
    DESIGN_MD_ENABLED: bool = True

    LLAMA_CPP_PATH: str = str(_BASE_DIR / "external" / "llama.cpp")

    @field_validator("SQLITE_DB_PATH", "CHROMADB_PERSIST_DIR", "DATA_DIR", "OUTPUTS_DIR", "SKILLS_OUTPUT_DIR", "COGNEE_DATA_DIR")
    @classmethod
    def convert_to_absolute_path(cls, v: str, info) -> str:
        path = Path(v)
        if not path.is_absolute():
            path = _BASE_DIR / path
        return str(path)

    @model_validator(mode="after")
    def _enforce_secret_policy(self):
        """凭据安全策略：生产 fail-fast，开发自动生成强随机值并落盘 .secrets/。

        彻底移除此前代码中的弱默认口令（admin/admin、aos123456、change-me-in-prod、
        空 POSTGRES 密码）与 HS256 对称密钥。生产环境缺失任一敏感凭据即启动失败，
        杜绝"弱默认悄悄上线"；开发环境自动生成并持久化，本地一键启动且不暴露弱口令。
        """
        import logging as _logging
        from utils.keystore import (
            load_jwt_keys,
            generate_strong_password,
            write_secret_file,
        )

        _log = _logging.getLogger(__name__)
        _secrets = Path(self.BASE_DIR) / ".secrets"
        _is_prod = self.APP_ENV == "production"

        # --- JWT 非对称密钥 (RS256) ---
        try:
            load_jwt_keys(base_dir=Path(self.BASE_DIR), app_env=self.APP_ENV)
        except Exception as exc:  # noqa: BLE001
            if _is_prod:
                raise ValueError(
                    "生产环境缺少 JWT 密钥对：请设置 AOS_JWT_PRIVATE_KEY/AOS_JWT_PUBLIC_KEY，"
                    "或在 .secrets/jwt/{private,public}.pem 放置 RSA 密钥。"
                ) from exc
            _log.warning("JWT 密钥自动准备失败（开发环境放宽）: %s", exc)

        # --- 管理员口令 ---
        if not self.ADMIN_PASSWORD:
            if _is_prod:
                raise ValueError("生产环境必须设置 AOS_ADMIN_PASSWORD，禁止弱默认口令。")
            _pw = generate_strong_password(24)
            self.ADMIN_PASSWORD = _pw
            write_secret_file(_secrets / "admin_password", _pw)
            _log.warning(
                "⚠️ 未设置 AOS_ADMIN_PASSWORD，已自动生成随机口令并写入 .secrets/admin_password（请勿提交）。"
            )

        # --- DeerFlow 网关管理员口令 ---
        if not self.DEERFLOW_ADMIN_PASSWORD:
            if _is_prod:
                raise ValueError("生产环境必须设置 AOS_DEERFLOW_ADMIN_PASSWORD，禁止弱默认口令。")
            _pw = generate_strong_password(24)
            self.DEERFLOW_ADMIN_PASSWORD = _pw
            write_secret_file(_secrets / "deerflow_admin_password", _pw)
            _log.warning(
                "⚠️ 未设置 AOS_DEERFLOW_ADMIN_PASSWORD，已自动生成随机口令并写入 "
                ".secrets/deerflow_admin_password。若 DeerFlow 网关开启了鉴权，请将其管理员口令设为此值。"
            )

        # --- Postgres 口令（仅团队/公司级 postgres 后端需要）---
        if self.STATE_BACKEND == "postgres" and not self.POSTGRES_PASSWORD:
            if _is_prod:
                raise ValueError("生产环境使用 postgres 后端必须设置 AOS_POSTGRES_PASSWORD。")
            _pw = generate_strong_password(24)
            self.POSTGRES_PASSWORD = _pw
            write_secret_file(_secrets / "postgres_password", _pw)
            _log.warning(
                "⚠️ 未设置 AOS_POSTGRES_PASSWORD，已自动生成随机口令并写入 .secrets/postgres_password。"
            )

        return self

    # 环境配置已在model_config中设置


# P1-4 配置分裂修复: 启动期把 .env 键值注入 os.environ。
# 双写「无前缀」(ZHIPU_API_KEY) 与「AOS_ 前缀」(AOS_ZHIPU_API_KEY) 两种形式,
# 使 config 字段(env="AOS_xxx") 与下游模块(读无前缀 ZHIPU_API_KEY 等) 都能取到,
# 不再依赖 start_all.sh 单独 export, 换启动方式不再静默降级。
try:
    _env_path = _BASE_DIR / ".env"
    if _env_path.exists():
        with open(_env_path, encoding="utf-8") as _ef:
            for _line in _ef:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _, _v = _line.partition("=")
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if not _k:
                    continue
                os.environ.setdefault(_k, _v)
                if not _k.startswith("AOS_"):
                    os.environ.setdefault("AOS_" + _k, _v)
except Exception as e:
    _LOG.warning(".env 文件解析失败，跳过注入: %s", e)

config = Config()


def _sync_env_from_dotenv() -> None:
    """将 .env 全部键值注入 os.environ (setdefault, 不覆盖已存在变量)。

    解决「配置分裂」根因：下游模块 (mem0/langfuse/gateway) 读的是**无前缀** env 名
    (ZHIPU_API_KEY / LANGFUSE_* / OPENCLAW_GATEWAY_TOKEN / SILICONFLOW_API_KEY …)，
    而 config.py 用 pydantic BaseSettings 只认 **AOS_ 前缀** 的 env 名
    (env="AOS_ZHIPU_API_KEY")，二者不一致。此前全靠 start_all.sh 单独 export 无前缀
    名桥接；一旦换启动方式(直接 uvicorn / 容器 / 调试)，这些变量缺失 → 静默降级
    (mem0/langfuse 不工作、gateway 登录失败)。

    这里在 config 加载后统一把 .env 的键值回填进 os.environ，使**任何启动方式**下
    下游读取行为一致。用 setdefault 保证：start_all.sh 或其它显式 export 的变量优先级更高。
    """
    env_path = _BASE_DIR / ".env"
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger = __import__("logging").getLogger(__name__)
        logger.warning("[config] 读取 .env 失败, 跳过 env 回填: %s", e)
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        # 去引号 (支持 'x' / "x")
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


_sync_env_from_dotenv()

