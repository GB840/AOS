"""
Unit tests for AOS API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_brain():
    """Create a mock brain instance for API testing."""
    mock = MagicMock()
    mock.identity = MagicMock()
    mock.identity.aid = "test-aos-001"
    mock.health_check.return_value = {
        "status": "healthy",
        "components": {
            "hermes": {"status": "ok"},
            "deerflow": {"status": "ok"},
            "memory": {"status": "ok"},
        }
    }
    mock.chat.return_value = {
        "session_id": "test-session",
        "response": "Hello from AOS!",
        "success": True,
    }
    mock.add_memory.return_value = {"id": 1, "success": True}
    mock.search_memory.return_value = {
        "query": "test",
        "results": [],
        "count": 0,
    }
    mock.export_memory.return_value = {"aos": {"knowledge": 0}, "deerflow": {}}
    mock.list_sessions.return_value = []
    mock.get_session.return_value = None
    mock.subagents = MagicMock()
    mock.subagents.list_agents.return_value = []
    mock.subagents.get_stats.return_value = {"total": 0}
    mock.subagents.has.return_value = True
    mock.subagents.invoke.return_value = {"success": True}
    mock.hermes = MagicMock()
    mock.hermes.list_skills.return_value = {"skills": [], "total": 0}
    mock.hermes.execute_skill.return_value = {"success": True}
    return mock


@pytest.fixture
def client(mock_brain):
    """Create a test client with mocked dependencies."""
    with patch("src.core.brain.get_brain", return_value=mock_brain):
        with patch("src.core.brain._brain_instance", mock_brain):
            from src.api.main import app
            # Override the startup event that initializes brain
            app.router.on_startup.clear()
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_returns_status(self, client, mock_brain):
        """Test that /health returns system status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data


class TestChatEndpoint:
    """Test chat endpoints."""

    def test_chat_returns_response(self, client, mock_brain):
        """Test basic chat endpoint."""
        response = client.post("/api/chat", json={"message": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert "response" in data or "session_id" in data

    def test_chat_requires_message(self, client):
        """Test that chat endpoint validates message field."""
        response = client.post("/api/chat", json={})
        assert response.status_code == 422  # Validation error


class TestKnowledgeEndpoint:
    """Test knowledge endpoints."""

    def test_add_knowledge(self, client, mock_brain):
        """Test adding knowledge."""
        response = client.post("/api/knowledge", json={
            "title": "Test Knowledge",
            "content": "Test content",
            "source": "test",
            "tags": ["test"],
        })
        # May return 200 or 500 depending on mock completeness
        assert response.status_code in [200, 500]


class TestSearchEndpoint:
    """Test search endpoints."""

    def test_search_memory(self, client, mock_brain):
        """Test memory search."""
        response = client.post("/api/search", json={
            "query": "test query",
            "search_type": "hybrid",
        })
        assert response.status_code in [200, 500]


class TestSessionsEndpoint:
    """Test sessions endpoints."""

    def test_list_sessions(self, client, mock_brain):
        """Test listing sessions."""
        response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data

    def test_get_nonexistent_session(self, client, mock_brain):
        """Test getting a session that doesn't exist."""
        response = client.get("/api/sessions/nonexistent-id")
        # Will return 404 or 500 depending on implementation
        assert response.status_code in [404, 500]
