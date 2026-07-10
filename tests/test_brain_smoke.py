"""Smoke tests for src/core/brain.py -- the central orchestration hub.

These are lightweight smoke tests that verify basic structure and pure-function
methods without requiring real external services (Hermes, DeerFlow gateway, etc.).

Covers:
- DeerFlowGatewayClient: instantiation, pure helper methods
- UnifiedBrain._InertDeerFlow: fallback stub behavior
- UnifiedBrain.health_check: structure validation (with mocked components)
- DeerFlowGatewayClient._extract_answer: answer extraction from state dicts

Run: python -m pytest tests/test_brain_smoke.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Ensure config won't crash during import
for var in ["API_KEY_HASH", "ADMIN_USERNAME", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "AOS_TOKEN_SECRET"]:
    os.environ.setdefault(var, "test-placeholder")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# DeerFlowGatewayClient -- pure methods, no network needed
# ---------------------------------------------------------------------------

class TestDeerFlowGatewayClient:
    """Test DeerFlowGatewayClient without network calls."""

    def test_instantiation(self):
        """DeerFlowGatewayClient should instantiate with default attributes."""
        from core.brain import DeerFlowGatewayClient
        client = DeerFlowGatewayClient(base_url="http://localhost:2026")
        assert client.base_url == "http://localhost:2026"
        assert client.real_deerflow is True
        assert client.api_version == "2.x"
        assert client._session is None  # lazy initialization

    def test_register_handler(self):
        """register_handler should store handlers in the internal dict."""
        from core.brain import DeerFlowGatewayClient
        client = DeerFlowGatewayClient()
        handler = lambda x: x
        client.register_handler("test_tool", handler)
        assert "test_tool" in client._handlers
        assert client._handlers["test_tool"] is handler

    def test_build_run_payload_defaults(self):
        """_build_run_payload should produce a valid DeerFlow 2.x payload."""
        from core.brain import DeerFlowGatewayClient
        client = DeerFlowGatewayClient()
        payload = client._build_run_payload("hello world")
        assert "input" in payload
        assert payload["input"]["messages"][0]["content"] == "hello world"
        assert "config" in payload
        assert "context" in payload
        assert payload["on_disconnect"] == "continue"

    def test_build_run_payload_with_options(self):
        """_build_run_payload should respect optional parameters."""
        from core.brain import DeerFlowGatewayClient
        client = DeerFlowGatewayClient()
        payload = client._build_run_payload(
            "test", thread_id="thread-123", model_name="gpt-4",
            assistant_id="my-agent"
        )
        assert payload["config"]["configurable"]["thread_id"] == "thread-123"
        assert payload["context"]["model_name"] == "gpt-4"
        assert payload["assistant_id"] == "my-agent"

    @staticmethod
    def test_extract_answer_from_messages():
        """_extract_answer should find the last AI message in state."""
        from core.brain import DeerFlowGatewayClient
        state = {
            "messages": [
                {"type": "human", "content": "hello"},
                {"type": "ai", "content": "hi there"},
            ]
        }
        assert DeerFlowGatewayClient._extract_answer(state) == "hi there"

    @staticmethod
    def test_extract_answer_empty_state():
        """_extract_answer should return empty string for empty state."""
        from core.brain import DeerFlowGatewayClient
        assert DeerFlowGatewayClient._extract_answer({}) == ""
        assert DeerFlowGatewayClient._extract_answer(None) == ""

    @staticmethod
    def test_extract_answer_content_blocks():
        """_extract_answer should handle content blocks (list format)."""
        from core.brain import DeerFlowGatewayClient
        state = {
            "messages": [
                {"type": "ai", "content": [{"text": "part1"}, {"text": "part2"}]},
            ]
        }
        result = DeerFlowGatewayClient._extract_answer(state)
        assert "part1" in result
        assert "part2" in result

    @staticmethod
    def test_normalize_subagent_name():
        """_normalize_subagent_name should lowercase and sanitize names."""
        from core.brain import DeerFlowGatewayClient
        assert DeerFlowGatewayClient._normalize_subagent_name("My_Agent") == "my-agent"
        assert DeerFlowGatewayClient._normalize_subagent_name("  hello world  ") == "hello-world"
        assert DeerFlowGatewayClient._normalize_subagent_name("agent_v2.1") == "agent-v2-1"


# ---------------------------------------------------------------------------
# UnifiedBrain._InertDeerFlow -- fallback stub
# ---------------------------------------------------------------------------

class TestInertDeerFlow:
    """Test the inert DeerFlow stub used as last-resort fallback."""

    def test_inert_deerflow_has_register_handler(self):
        """_InertDeerFlow should have a register_handler method (no-op)."""
        from core.brain import UnifiedBrain
        stub = UnifiedBrain._InertDeerFlow()
        # Should not raise
        stub.register_handler("test", lambda: None)

    def test_inert_deerflow_unknown_methods_return_none(self):
        """_InertDeerFlow.__getattr__ should return no-op callables."""
        from core.brain import UnifiedBrain
        stub = UnifiedBrain._InertDeerFlow()
        # Any unknown attribute should return a callable that returns None
        result = stub.some_unknown_method("arg1", "arg2")
        assert result is None

    def test_inert_deerflow_not_real(self):
        """_InertDeerFlow should report real_deerflow=False."""
        from core.brain import UnifiedBrain
        stub = UnifiedBrain._InertDeerFlow()
        assert stub.real_deerflow is False


# ---------------------------------------------------------------------------
# UnifiedBrain -- health check with mocked components
# ---------------------------------------------------------------------------

class TestUnifiedBrainHealthCheck:
    """Test health_check structure with mocked components."""

    def test_health_check_structure(self):
        """health_check should return a dict with expected top-level keys."""
        from core.brain import UnifiedBrain

        # Create a mock brain without running __init__
        brain = object.__new__(UnifiedBrain)
        brain.init_status = {"hermes": "success", "deerflow": "success"}
        brain._initialization_errors = []

        # Mock all components that health_check accesses
        mock_hermes = MagicMock()
        mock_hermes.real_hermes = False
        mock_hermes.get_stats.return_value = {"status": "ok"}
        brain.hermes = mock_hermes

        mock_deerflow = MagicMock()
        mock_deerflow.real_deerflow = False
        mock_deerflow.get_stats.return_value = {"status": "ok"}
        brain.deerflow = mock_deerflow

        mock_memory = MagicMock()
        mock_memory.get_stats.return_value = {"status": "ok"}
        brain.memory = mock_memory

        brain.persistence = MagicMock()
        brain.persistence.get_stats.return_value = {"status": "ok"}
        brain.skill_registry = MagicMock()
        brain.skill_registry._skills = {"skill1": True, "skill2": True}
        brain.subagents = MagicMock()
        brain.subagents.get_stats.return_value = {"count": 3}
        brain.mcp = MagicMock()
        brain.fabric = None
        brain.audit = MagicMock()
        brain.audit.get_stats.return_value = {"count": 10}
        brain.aid_gen = MagicMock()
        brain.aid_gen.get_stats.return_value = {"status": "ok"}
        brain.tracer = MagicMock()
        brain.tracer.get_stats.return_value = {"status": "ok"}
        brain.identity = MagicMock()
        brain.identity.aid = "aos-test-001"

        result = brain.health_check()

        # Verify top-level structure
        assert "status" in result
        assert "timestamp" in result
        assert "components" in result
        assert "init_summary" in result
        assert "aid" in result

        # Verify component keys
        components = result["components"]
        assert "hermes" in components
        assert "deerflow" in components
        assert "memory" in components
        assert "skills" in components
        assert "compliance" in components

        # Verify status
        assert result["status"] == "healthy"  # no failed components
        assert result["aid"] == "aos-test-001"

    def test_health_check_degraded_status(self):
        """health_check should report 'degraded' when components fail."""
        from core.brain import UnifiedBrain

        brain = object.__new__(UnifiedBrain)
        brain.init_status = {"hermes": "success", "deerflow": "error: connection refused"}
        brain._initialization_errors = [("deerflow", "error: connection refused")]

        brain.hermes = MagicMock()
        brain.hermes.real_hermes = False
        brain.hermes.get_stats.return_value = {"status": "ok"}
        brain.deerflow = None
        brain.memory = None
        brain.persistence = None
        brain.skill_registry = MagicMock()
        brain.skill_registry._skills = {}
        brain.subagents = None
        brain.mcp = None
        brain.fabric = None
        brain.audit = None
        brain.aid_gen = None
        brain.tracer = None
        brain.identity = MagicMock()
        brain.identity.aid = "aos-test-002"

        result = brain.health_check()
        assert result["status"] == "degraded"

    def test_get_init_status_structure(self):
        """get_init_status should return a well-structured summary."""
        from core.brain import UnifiedBrain

        brain = object.__new__(UnifiedBrain)
        brain.init_status = {"comp_a": "success", "comp_b": "error: timeout"}
        brain._initialization_errors = [("comp_b", "error: timeout")]

        status = brain.get_init_status()
        assert status["status"] == "completed"
        assert status["total_components"] == 2
        assert status["successful_components"] == 1
        assert status["failed_components"] == 1
        assert len(status["errors"]) == 1

    def test_is_component_ready(self):
        """is_component_ready should check init_status correctly."""
        from core.brain import UnifiedBrain

        brain = object.__new__(UnifiedBrain)
        brain.init_status = {"hermes": "success", "deerflow": "error"}

        assert brain.is_component_ready("hermes") is True
        assert brain.is_component_ready("deerflow") is False
        assert brain.is_component_ready("nonexistent") is False
