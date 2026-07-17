"""测试 sandbox 命令白名单与命令注入防护（对真实 FastAPI app）。

核实真实行为（src/api/main.py 的 _is_command_allowed + /api/sandbox/exec）：
- 命令拼接操作符 (; | & && || > >> < ` $( ) 一律拒绝 -> 200 + success=False
- 仅允许首个 token 匹配 SANDBOX_ALLOWED_COMMANDS 前缀的只读命令 -> 200 + success=True
- 缺少 confirm（且 SANDBOX_REQUIRE_CONFIRM=true）-> 200 + success=False（"Confirmation required"）
- 无凭证 -> 中间件返回 401

注意：config 是 pydantic BaseSettings 单例（构造时读 env），测试必须 patch 单例属性，
事后设 os.environ 无效；且必须带真实 API Key，假凭证会被中间件判 401。
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

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
    # patch 单例属性（非 os.environ，后者对单例无效）
    monkeypatch.setattr(app_config, "SANDBOX_API_ENABLED", True)
    monkeypatch.setattr(app_config, "SANDBOX_REQUIRE_CONFIRM", False)
    monkeypatch.setattr(app_config, "API_KEY", TEST_KEY)
    # mock brain，避免端点真执行命令（也避免 26 组件重初始化之外的副作用）
    with patch("src.api.main.brain", MockBrain()):
        from src.api.main import app
        yield TestClient(app)


def test_sandbox_command_injection_attack(client):
    """命令拼接攻击必须在命令校验层被拒绝（200 + success=False）。"""
    headers = {"X-API-Key": TEST_KEY}
    attacks = [
        "ls;rm -rf /", "ls | cat /etc/passwd", "ls && cat flag.txt",
        "cat $(whoami)", "ls`whoami`", "ls $(echo test)",
        "ls > /tmp/test", "ls >> /tmp/test", "ls < /tmp/test",
        "ls || echo test", "ls & echo test",
    ]
    for cmd in attacks:
        r = client.post(
            "/api/sandbox/exec", json={"command": cmd, "confirm": True}, headers=headers,
        )
        assert r.status_code == 200, f"注入命令返回非200: {cmd!r} -> {r.status_code}"
        body = r.json()
        assert body["success"] is False, f"注入未被拦截: {cmd!r} -> {body}"
        assert ("操作符" in body.get("error", "")
                or "allowlist" in body.get("error", "").lower()), \
            f"错误信息未说明拦截原因: {cmd!r} -> {body}"


def test_sandbox_valid_commands(client):
    """白名单内的合法只读命令必须通过（200 + success=True）。"""
    headers = {"X-API-Key": TEST_KEY}
    for cmd in ["ls", "ls -la", "pwd"]:
        r = client.post(
            "/api/sandbox/exec", json={"command": cmd, "confirm": True}, headers=headers,
        )
        assert r.status_code == 200, f"{cmd!r} -> {r.status_code}"
        assert r.json()["success"] is True, f"合法命令被误拦: {cmd!r} -> {r.json()}"


def test_sandbox_confirm_required(client, monkeypatch):
    """缺少 confirm（且 SANDBOX_REQUIRE_CONFIRM=true）时拒绝执行。"""
    from utils.config import config as app_config
    monkeypatch.setattr(app_config, "SANDBOX_REQUIRE_CONFIRM", True)
    headers = {"X-API-Key": TEST_KEY}
    r = client.post("/api/sandbox/exec", json={"command": "ls"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "confirm" in body.get("error", "").lower()


def test_sandbox_exec_no_auth(client):
    """无凭证 -> 中间件返回 401。"""
    r = client.post("/api/sandbox/exec", json={"command": "ls", "confirm": True})
    assert r.status_code == 401
