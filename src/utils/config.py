from pydantic_settings import BaseSettings
from pydantic import field_validator, Field
from typing import Optional
from pathlib import Path
import os

_BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Config(BaseSettings):
    BASE_DIR: str = str(_BASE_DIR)
    APP_NAME: str = "能体操作系统v5.0零成本版"
    APP_VERSION: str = "5.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # API安全 - 支持环境变量 AOS_API_KEY
    API_KEY: str = Field(default="", env="AOS_API_KEY")
    API_KEY_HASH: str = Field(default="", env="AOS_API_KEY_HASH")  # 可选：哈希版本的API密钥
    ALLOWED_ORIGINS: str = "http://localhost:8501,http://localhost:8000"
    MAX_REQUESTS_PER_MINUTE: int = 100

    # 统一API - 支持环境变量 AOS_UNIFIED_API_KEY
    UNIFIED_API_KEY: str = Field(default="", env="AOS_UNIFIED_API_KEY")
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
    ZHIPU_API_KEY: str = Field(default="", env="AOS_ZHIPU_API_KEY")
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_MODEL: str = "glm-4-flash"
    ZHIPU_ENABLED: bool = True

    # SiliconFlow - 支持环境变量 AOS_SILICONFLOW_API_KEY
    SILICONFLOW_API_KEY: str = Field(default="", env="AOS_SILICONFLOW_API_KEY")
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_MODEL: str = "deepseek-ai/DeepSeek-V2.5"
    SILICONFLOW_ENABLED: bool = True

    # 百度文心 - 支持环境变量 AOS_BAIDU_API_KEY, AOS_BAIDU_SECRET_KEY
    BAIDU_API_KEY: str = Field(default="", env="AOS_BAIDU_API_KEY")
    BAIDU_SECRET_KEY: str = Field(default="", env="AOS_BAIDU_SECRET_KEY")
    BAIDU_BASE_URL: str = "https://aip.baidubce.com"
    BAIDU_MODEL: str = "ernie-speed-128k"
    BAIDU_ENABLED: bool = True

    # 讯飞语音 - 支持环境变量 AOS_XFYUN_APP_ID, AOS_XFYUN_API_KEY, AOS_XFYUN_API_SECRET
    XFYUN_APP_ID: str = Field(default="", env="AOS_XFYUN_APP_ID")
    XFYUN_API_KEY: str = Field(default="", env="AOS_XFYUN_API_KEY")
    XFYUN_API_SECRET: str = Field(default="", env="AOS_XFYUN_API_SECRET")
    XFYUN_MODEL: str = "lite"
    XFYUN_ENABLED: bool = True

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_ENABLED: bool = True

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

    ROUTER_CODING_PRIMARY: str = "zhipu"
    ROUTER_HIGH_CONCURRENCY_PRIMARY: str = "baidu"
    ROUTER_LONG_CONTEXT_PRIMARY: str = "zhipu"
    ROUTER_VOICE_PRIMARY: str = "xfyun"
    ROUTER_EXPERIMENT_PRIMARY: str = "siliconflow"
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
    # DeerFlow 网关管理员凭证: 从环境变量读取, 默认保留原本地值(不破坏现有行为)
    DEERFLOW_ADMIN_USER: str = Field(default="admin", env="AOS_DEERFLOW_ADMIN_USER")
    DEERFLOW_ADMIN_PASSWORD: str = Field(default="aos123456", env="AOS_DEERFLOW_ADMIN_PASSWORD")

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

    class Config:
        env_file = str(_BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


config = Config()
