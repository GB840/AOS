"""
Pytest configuration and fixtures for AOS v5.0 tests.
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Set test environment variables before any imports
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQLITE_DB_PATH", str(PROJECT_ROOT / "data" / "sqlite" / "test_aos.db"))
os.environ.setdefault("CHROMADB_PERSIST_DIR", str(PROJECT_ROOT / "data" / "chroma_test"))

import pytest


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def src_dir():
    """Return the src directory."""
    return PROJECT_ROOT / "src"


@pytest.fixture(scope="session")
def data_dir():
    """Return the data directory, ensuring it exists."""
    d = PROJECT_ROOT / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="function")
def clean_data_dir(data_dir):
    """Provide a clean data directory for each test."""
    import shutil
    test_dirs = ["sqlite", "chroma_test", "cognee"]
    for d in test_dirs:
        path = data_dir / d
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    yield data_dir
    # Cleanup after test
    for d in test_dirs:
        path = data_dir / d
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mock_config():
    """Provide a mock configuration for testing."""
    from unittest.mock import MagicMock
    cfg = MagicMock()
    cfg.APP_NAME = "AOS Test"
    cfg.APP_VERSION = "5.0.0"
    cfg.DEBUG = False
    cfg.PORT = 8000
    cfg.HOST = "127.0.0.1"
    cfg.API_KEY = "test-api-key"
    cfg.UNIFIED_API_KEY = "test-unified-key"
    cfg.UNIFIED_BASE_URL = "https://api.test.com/v1"
    cfg.ZHIPU_API_KEY = "test-zhipu-key"
    cfg.ZHIPU_BASE_URL = "https://api.test.com"
    cfg.ZHIPU_MODEL = "glm-4-flash"
    cfg.OLLAMA_BASE_URL = "http://localhost:11434"
    cfg.OLLAMA_MODEL = "qwen2.5:7b"
    cfg.SQLITE_DB_PATH = str(PROJECT_ROOT / "data" / "sqlite" / "test_aos.db")
    cfg.CHROMADB_PERSIST_DIR = str(PROJECT_ROOT / "data" / "chroma_test")
    cfg.DATA_DIR = str(PROJECT_ROOT / "data")
    cfg.VECTOR_COLLECTION_NAME = "test_memory"
    cfg.HERMES_SOURCE_PATH = ""
    cfg.DEERFLOW_SOURCE_PATH = ""
    cfg.DEERFLOW_CONFIG_PATH = ""
    return cfg


@pytest.fixture
def sample_messages():
    """Provide sample conversation messages."""
    return [
        {"role": "user", "content": "你好，请介绍一下你自己"},
        {"role": "assistant", "content": "我是 AOS v5.0，一个智能代理操作系统。"},
        {"role": "user", "content": "你能做什么？"},
        {"role": "assistant", "content": "我可以帮你回答问题、编写代码、搜索信息等。"},
    ]


@pytest.fixture
def sample_knowledge():
    """Provide sample knowledge entries."""
    return [
        {"title": "Python 基础", "content": "Python 是一种高级编程语言", "source": "test", "tags": ["python", "编程"]},
        {"title": "FastAPI 入门", "content": "FastAPI 是一个现代 Web 框架", "source": "test", "tags": ["fastapi", "web"]},
    ]


@pytest.fixture
def temp_workspace(tmp_path):
    """Provide a temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def sample_config_yaml(tmp_path):
    """Create a minimal config.yaml for testing."""
    import yaml
    config_data = {
        "config_version": 18,
        "log_level": "info",
        "models": [
            {
                "name": "test-model",
                "display_name": "Test Model",
                "use": "langchain_openai:ChatOpenAI",
                "model": "gpt-3.5-turbo",
                "api_key": "test-key",
                "base_url": "https://api.test.com/v1",
            }
        ],
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)
    return config_path


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level singletons between tests."""
    import src.core.brain as brain_module

    # Save original values
    original_brain = brain_module._brain_instance

    yield

    # Reset
    brain_module._brain_instance = original_brain


# ---- Markers for test categorization ----

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_api: Tests requiring API keys")
    config.addinivalue_line("markers", "requires_deerflow: Tests requiring DeerFlow")
    config.addinivalue_line("markers", "requires_hermes: Tests requiring Hermes Agent")
