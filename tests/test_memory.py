"""
Unit tests for AOS memory system.
"""

import pytest
import time
from pathlib import Path


class TestMemoryManager:
    """Test MemoryManager class."""

    def test_memory_init(self, clean_data_dir):
        """Test that MemoryManager initializes correctly."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        assert mem.db_path is not None
        assert mem.sqlite_conn is not None

    def test_add_conversation(self, clean_data_dir):
        """Test adding a conversation message."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        conv_id = mem.add_conversation(
            session_id="test-session-1",
            role="user",
            content="Hello, AOS!",
            metadata={"source": "test"}
        )
        assert conv_id > 0

    def test_get_conversation_history(self, clean_data_dir):
        """Test retrieving conversation history."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        session_id = "test-session-2"

        mem.add_conversation(session_id, "user", "First message")
        time.sleep(0.01)
        mem.add_conversation(session_id, "assistant", "Second message")
        time.sleep(0.01)
        mem.add_conversation(session_id, "user", "Third message")

        history = mem.get_conversation_history(session_id, limit=10)
        assert len(history) == 3
        assert history[0]["content"] == "First message"
        assert history[1]["content"] == "Second message"
        assert history[2]["content"] == "Third message"

    def test_add_knowledge(self, clean_data_dir):
        """Test adding knowledge entries."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        kid = mem.add_knowledge(
            title="Test Knowledge",
            content="This is test knowledge content.",
            source="unit_test",
            tags=["test", "unit"]
        )
        assert kid > 0

    def test_search_knowledge_fulltext(self, clean_data_dir):
        """Test full-text search on knowledge."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        mem.add_knowledge("Python Programming", "Python is a great language for AI.", "test")
        mem.add_knowledge("JavaScript", "JavaScript runs in browsers.", "test")
        mem.add_knowledge("Python Web", "FastAPI is a Python web framework.", "test")

        results = mem.search_knowledge_fulltext("Python", limit=10)
        assert len(results) >= 2
        titles = [r["title"] for r in results]
        assert "Python Programming" in titles
        assert "Python Web" in titles

    def test_task_lifecycle(self, clean_data_dir):
        """Test task creation, status update, and retrieval."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        task_id = mem.create_task("task-001", "code_generation", {"prompt": "write hello world"})

        task = mem.get_task(task_id)
        assert task is not None
        assert task["status"] == "pending"
        assert task["type"] == "code_generation"

        mem.update_task_status(task_id, "running", {"started_at": "now"})
        task = mem.get_task(task_id)
        assert task["status"] == "running"

        mem.update_task_status(task_id, "completed", {"output": "hello world"})
        task = mem.get_task(task_id)
        assert task["status"] == "completed"

    def test_list_tasks_filtered(self, clean_data_dir):
        """Test listing tasks with status filter."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        mem.create_task("task-a", "type1", {"data": "a"})
        mem.create_task("task-b", "type2", {"data": "b"})
        mem.create_task("task-c", "type1", {"data": "c"})

        mem.update_task_status("task-a", "completed")
        mem.update_task_status("task-b", "running")

        all_tasks = mem.list_tasks()
        assert len(all_tasks) == 3

        pending = mem.list_tasks(status="pending")
        assert len(pending) == 1
        assert pending[0]["id"] == "task-c"

        completed = mem.list_tasks(status="completed")
        assert len(completed) == 1
        assert completed[0]["id"] == "task-a"

    def test_hybrid_search(self, clean_data_dir):
        """Test hybrid search combining vector and full-text."""
        from src.memory.memory import MemoryManager

        mem = MemoryManager()
        mem.add_conversation("hybrid-test", "user", "How do I install AOS?")
        mem.add_conversation("hybrid-test", "assistant", "Run pip install aos")
        mem.add_knowledge("Installation", "AOS can be installed via pip or from source.", "docs")

        results = mem.hybrid_search("install AOS", n_results=5)
        assert len(results) > 0


class TestConfigLoading:
    """Test configuration loading."""

    def test_config_loads_defaults(self):
        """Test that config loads with defaults."""
        from src.utils.config import Config

        cfg = Config()
        assert cfg.APP_NAME is not None
        assert cfg.APP_VERSION == "5.0.0"
        assert cfg.PORT == 8000
        assert cfg.HOST == "0.0.0.0"

    def test_config_respects_env_vars(self, monkeypatch):
        """Test that config reads from environment variables."""
        monkeypatch.setenv("PORT", "9999")
        monkeypatch.setenv("APP_NAME", "Test AOS")

        # Clear cached config
        import importlib
        import src.utils.config as config_module
        importlib.reload(config_module)

        from src.utils.config import Config
        cfg = Config()
        assert cfg.PORT == 9999
        assert cfg.APP_NAME == "Test AOS"
