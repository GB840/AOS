"""测试 /api/sandbox/exec 端点的认证网关（对真实 FastAPI app）。

核实真实行为（APISecurityMiddleware + /api/sandbox/exec）：
- 无凭证 -> 中间件返回 401
- 有效静态 API Key（X-API-Key 头）-> 通过中间件，端点返回 200 且含 success 字段
- 有效 JWT（Authorization: Bearer）-> 通过中间件，端点返回 200 且含 success 字段
- 伪造/错误 Key -> 401

注意：config 是 pydantic BaseSettings 单例（构造时读 env），测试必须 patch 单例属性，
事后设 os.environ 无效；且必须带真实凭据，假 JWT/错误 Key 会被中间件判 401。
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from api.security import create_access_token

TEST_KEY = "test-aos-key-unit-000000000000"


class _MockSandbox:
    def acquire(self):
        return "test-sandbox-id"
    def execute_command(self, command):
        return f"executed: {command}"
    def release(self):
        pass

class MockBrain:
    class DeerFlow:
        def create_sandbox(self, thread_id=None):
            return _MockSandbox()
    deerflow = DeerFlow()


@pytest.fixture
def client(monkeypatch):
    from utils.config import config as app_config
    monkeypatch.setattr(app_config, "SANDBOX_API_ENABLED", True)
    monkeypatch.setattr(app_config, "SANDBOX_REQUIRE_CONFIRM", False)
    monkeypatch.setattr(app_config, "API_KEY", TEST_KEY)
    with patch("src.api.main.brain", MockBrain()):
        from src.api.main import app
        yield TestClient(app)


def test_sandbox_exec_no_auth(client):
    """无凭证 -> 中间件返回 401。"""
    r = client.post("/api/sandbox/exec", json={"command": "ls", "confirm": True})
    assert r.status_code == 401


def test_sandbox_exec_auth_with_api_key(client):
    """有效 API Key -> 通过中间件，端点返回 200 且含 success 字段。"""
    r = client.post(
        "/api/sandbox/exec", json={"command": "ls", "confirm": True},
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.status_code == 200
    assert "success" in r.json()


def test_sandbox_exec_auth_with_jwt(client):
    """有效 JWT（Bearer）-> 通过中间件，端点返回 200 且含 success 字段。"""
    token = create_access_token("test-user")
    r = client.post(
        "/api/sandbox/exec", json={"command": "ls", "confirm": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "success" in r.json()


def test_sandbox_exec_invalid_key(client):
    """伪造/错误 Key -> 中间件返回 401。"""
    r = client.post(
        "/api/sandbox/exec", json={"command": "ls", "confirm": True},
        headers={"X-API-Key": "wrong-key"},
    )
    assert r.status_code == 401
